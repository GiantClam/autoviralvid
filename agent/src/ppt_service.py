"""PPT service: generation, export, enhancement and render lifecycle."""

from __future__ import annotations

import html
import hashlib
import json
import logging
import os
import re
import math
import uuid
import base64
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote as url_quote, urlparse
from urllib import error as urllib_error
from urllib import request as urllib_request

from src.schemas.ppt import (
    ContentRequest,
    ExportRequest,
    OutlineRequest,
    ParsedDocument,
    PresentationOutline,
    RenderJob,
    SlideContent,
    VideoRenderConfig,
)
from src.schemas.ppt_outline import LayoutType, OutlinePlan, OutlinePlanRequest, StickyNote
from src.schemas.ppt_pipeline import (
    PPTPipelineArtifacts,
    PPTPipelineRequest,
    PPTPipelineResult,
    PPTPipelineStageStatus,
)
from src.schemas.ppt_plan import (
    ContentBlock,
    PresentationPlan,
    PresentationPlanRequest,
    SlideContentStrategy,
    SlidePlan,
)
from src.schemas.ppt_research import (
    ResearchContext,
    ResearchEvidence,
    ResearchGap,
    ResearchQuestion,
    ResearchRequest,
)
from src.ppt_planning import (
    build_slide_content_strategy,
    enforce_density_rhythm,
    enforce_layout_diversity,
    enforce_template_family_cohesion,
    density_level_for_layout,
    paginate_content_overflow,
    recommend_layout,
)
from src.ppt_template_catalog import (
    contract_profile as shared_contract_profile,
    quality_profile as shared_quality_profile,
    resolve_template_for_slide,
    template_profiles as shared_template_profiles,
)
from src.ppt_master_design_spec import apply_render_paths, build_design_spec

logger = logging.getLogger("ppt_service")

_supabase = None
_local_render_jobs: Dict[str, Dict[str, Any]] = {}
_dot_env_cache: Optional[Dict[str, str]] = None
_MAX_TEMPLATE_BYTES = 50 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _env_flag(name: str, default: str = "false") -> bool:
    return str(os.getenv(name, default)).strip().lower() not in {"0", "false", "no", "off"}


def _require_direct_skill_runtime() -> bool:
    return _env_flag("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "true")


def _assert_skill_runtime_success(
    *,
    stage: str,
    skill_output: Dict[str, Any],
    requested_skills: List[str],
    slide_id: str = "",
) -> None:
    normalized_requested = {
        str(item or "").strip().lower()
        for item in requested_skills
        if str(item or "").strip()
    }
    results = skill_output.get("results") if isinstance(skill_output.get("results"), list) else []
    fulfilled: set[str] = set()
    error_notes: List[str] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        skill = str(row.get("skill") or "").strip().lower()
        status = str(row.get("status") or "").strip().lower()
        note = str(row.get("note") or "").strip()
        if status in {"applied", "noop"} and skill:
            fulfilled.add(skill)
        if status == "error":
            error_notes.append(f"{skill or 'unknown'}:{note or 'error'}")

    unresolved = sorted(normalized_requested - fulfilled)
    if error_notes or unresolved:
        parts: List[str] = []
        if error_notes:
            parts.append("errors=" + "; ".join(error_notes[:8]))
        if unresolved:
            parts.append("unresolved=" + ",".join(unresolved[:12]))
        location = f" slide={slide_id}" if str(slide_id).strip() else ""
        detail = " | ".join(parts)[:400]
        raise RuntimeError(f"skill_runtime_failed:{stage}{location} {detail}".strip())


def _resolve_export_channel(requested: str | None) -> str:
    configured = str(_env_value("PPT_EXPORT_CHANNEL", "local")).strip().lower()
    if configured not in {"local", "remote", "auto"}:
        configured = "local"
    channel = str(requested or "auto").strip().lower()
    if channel not in {"local", "remote", "auto"}:
        channel = "auto"
    if channel == "auto":
        channel = "local" if configured == "auto" else configured
    if channel not in {"local", "remote"}:
        return "local"
    return channel


def _load_local_env() -> Dict[str, str]:
    global _dot_env_cache
    if _dot_env_cache is not None:
        return _dot_env_cache

    cache: Dict[str, str] = {}
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        try:
            for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and value:
                    cache[key] = value
        except Exception:
            cache = {}
    _dot_env_cache = cache
    return cache


def _env_value(name: str, default: str = "") -> str:
    value = str(os.getenv(name, "")).strip()
    if value:
        return value
    fallback = str(_load_local_env().get(name, "")).strip()
    if fallback:
        os.environ.setdefault(name, fallback)
        return fallback
    return default


async def _download_remote_file_bytes(file_url: str, *, suffix: str = ".bin") -> bytes:
    """Download remote file to temporary path with SSRF/size guards and return bytes."""
    from src.document_parser import _download_file

    local_path = await _download_file(file_url, suffix=suffix)
    try:
        payload = Path(local_path).read_bytes()
        if len(payload) > _MAX_TEMPLATE_BYTES:
            raise ValueError(
                f"template file too large: {len(payload) / 1024 / 1024:.1f}MB > {_MAX_TEMPLATE_BYTES / 1024 / 1024:.0f}MB"
            )
        return payload
    finally:
        try:
            os.unlink(local_path)
        except Exception:
            pass


def _clamp_percent(value: object, default: int = 100) -> int:
    try:
        parsed = int(str(value))
    except Exception:
        parsed = default
    return max(0, min(100, parsed))


def _to_float(value: object, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return default


def _resolve_quality_profile_id(
    requested: str,
    *,
    topic: str = "",
    purpose: str = "",
    audience: str = "",
    total_pages: int = 0,
) -> str:
    raw = str(requested or "").strip().lower()
    if raw and raw != "auto":
        return raw
    text = " ".join(
        [
            str(topic or "").strip().lower(),
            str(purpose or "").strip().lower(),
            str(audience or "").strip().lower(),
        ]
    )
    pages = max(0, int(total_pages or 0))
    if any(token in text for token in ("融资", "路演", "investor", "fundraising", "pitch deck")):
        return "investor_pitch"
    if any(token in text for token in ("周报", "月报", "季报", "汇报", "status", "report", "briefing")):
        return "status_report"
    if any(token in text for token in ("培训", "课程", "教学", "training", "onboarding", "workshop")):
        return "training_deck"
    if any(token in text for token in ("技术评审", "架构评审", "tech review", "architecture review", "engineering")):
        return "tech_review"
    if any(token in text for token in ("营销", "品牌", "发布会", "marketing", "campaign", "launch", "brand")):
        return "marketing_pitch"
    if pages >= 14:
        return "high_density_consulting"
    return "default"


_TEMPLATE_STYLE_MAP: Dict[str, str] = {
    "dashboard_dark": "sharp",
    "hero_dark": "sharp",
    "hero_tech_cover": "sharp",
    "bento_2x2_dark": "sharp",
    "bento_mosaic_dark": "sharp",
    "split_media_dark": "rounded",
    "architecture_dark_panel": "sharp",
    "ecosystem_orange_dark": "rounded",
    "neural_blueprint_light": "soft",
    "ops_lifecycle_light": "soft",
    "consulting_warm_light": "pill",
}


def _derive_style_from_template_family(template_family: str) -> str:
    normalized = str(template_family or "").strip().lower()
    return _TEMPLATE_STYLE_MAP.get(normalized, "soft")


def _dedupe_skill_names(values: List[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw or "").strip().lower()
        if not text:
            continue
        key = re.sub(r"[^a-z0-9-]+", "-", text).strip("-")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _agent_type_for_slide_type(slide_type: str) -> str:
    normalized = str(slide_type or "").strip().lower()
    if normalized == "cover":
        return "cover-page-generator"
    if normalized == "toc":
        return "table-of-contents-generator"
    if normalized in {"divider", "section"}:
        return "section-divider-generator"
    if normalized == "summary":
        return "summary-page-generator"
    return "content-page-generator"


def _requested_skills_for_slide(
    slide: Dict[str, Any],
    idx: int,
    total: int,
    *,
    deck_template_family: str = "",
) -> List[str]:
    slide_type = str(slide.get("slide_type") or "").strip().lower()
    layout_grid = str(slide.get("layout_grid") or "").strip().lower()
    render_path = str(slide.get("render_path") or "").strip().lower()
    template_family = str(slide.get("template_family") or deck_template_family or "").strip().lower()
    block_types = {
        str((block or {}).get("block_type") or (block or {}).get("type") or "").strip().lower()
        for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else [])
        if isinstance(block, dict)
    }

    skills: List[str] = [
        "ppt-orchestra-skill",
        "slide-making-skill",
        "design-style-skill",
    ]
    if idx == 0 or idx == max(0, total - 1) or slide_type in {"cover", "toc", "divider", "summary"}:
        skills.append("color-font-skill")
    if render_path in {"svg", "png_fallback"} or layout_grid == "timeline" or (block_types & {"workflow", "diagram"}):
        skills.append("pptx")
    if template_family and template_family not in {"auto"}:
        skills.append("ppt-editing-skill")
    existing = slide.get("load_skills") if isinstance(slide.get("load_skills"), list) else []
    skills.extend(str(item) for item in existing)
    return _dedupe_skill_names(skills)


def _apply_skill_planning_to_render_payload(render_payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(render_payload or {})
    slides = out.get("slides")
    if not isinstance(slides, list) or not slides:
        return out

    runtime: Dict[str, Any] = {
        "enabled": False,
        "slides": [],
        "reason": "",
        "sources": [
            "minimax:skills/pptx-generator",
            "minimax:plugins/pptx-plugin",
            "anthropic:skills/pptx",
            "ppt-master",
        ],
    }
    try:
        from src.installed_skill_executor import execute_installed_skill_request
    except Exception as exc:
        runtime["reason"] = f"skill_planning_runtime_unavailable:{str(exc)[:180]}"
        out["skill_planning_runtime"] = runtime
        return out

    runtime["enabled"] = True
    total = len(slides)
    deck_ctx = {
        "title": str(out.get("title") or "").strip(),
        "topic": str(out.get("title") or "").strip(),
        "total_slides": total,
        "style": str((out.get("theme") or {}).get("style") if isinstance(out.get("theme"), dict) else ""),
        "palette_key": str((out.get("theme") or {}).get("palette") if isinstance(out.get("theme"), dict) else ""),
        "template_family": str(out.get("template_family") or "").strip().lower(),
    }

    planned_slides: List[Dict[str, Any]] = []
    deck_style_variant = str(out.get("style_variant") or "").strip().lower()
    deck_palette_key = str(out.get("palette_key") or "").strip()
    deck_template_family = str(out.get("template_family") or "").strip().lower()
    deck_skill_profile = str(out.get("skill_profile") or "").strip()
    content_layout_history: List[str] = []
    content_slide_index = 0

    for idx, raw_slide in enumerate(slides):
        slide = dict(raw_slide if isinstance(raw_slide, dict) else {})
        deck_ctx["content_slide_index"] = content_slide_index
        deck_ctx["used_content_layouts"] = list(content_layout_history[-8:])
        requested_skills = _requested_skills_for_slide(
            slide,
            idx,
            total,
            deck_template_family=str(deck_ctx.get("template_family") or ""),
        )
        row_runtime: Dict[str, Any] = {
            "slide_id": str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}"),
            "requested_skills": requested_skills,
            "applied_keys": [],
            "trace": [],
            "reason": "",
        }
        try:
            skill_output = execute_installed_skill_request(
                {
                    "version": 1,
                    "requested_skills": requested_skills,
                    "slide": slide,
                    "deck": deck_ctx,
                }
            )
        except Exception as exc:
            if _require_direct_skill_runtime():
                raise RuntimeError(
                    f"skill_executor_exception:slide={row_runtime['slide_id']}:{str(exc)[:220]}"
                ) from exc
            row_runtime["reason"] = f"skill_executor_exception:{str(exc)[:180]}"
            runtime["slides"].append(row_runtime)
            planned_slides.append(slide)
            continue

        if _require_direct_skill_runtime():
            _assert_skill_runtime_success(
                stage="skill_planning",
                skill_output=skill_output if isinstance(skill_output, dict) else {},
                requested_skills=requested_skills,
                slide_id=row_runtime["slide_id"],
            )

        patch = skill_output.get("patch") if isinstance(skill_output.get("patch"), dict) else {}
        context = skill_output.get("context") if isinstance(skill_output.get("context"), dict) else {}
        trace = skill_output.get("results") if isinstance(skill_output.get("results"), list) else []
        row_runtime["trace"] = trace
        row_runtime["applied_keys"] = sorted(str(key) for key in patch.keys())

        for key in (
            "slide_type",
            "layout_grid",
            "render_path",
            "template_family",
            "skill_profile",
            "style_variant",
            "palette_key",
            "title",
        ):
            value = patch.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            slide[key] = text

        agent_type = str(
            patch.get("agent_type")
            or context.get("agent_type")
            or slide.get("agent_type")
            or _agent_type_for_slide_type(str(slide.get("slide_type") or "content"))
        ).strip()
        slide["agent_type"] = agent_type

        recommended = context.get("recommended_load_skills") if isinstance(context.get("recommended_load_skills"), list) else []
        merged_load_skills = _dedupe_skill_names(
            [
                *(slide.get("load_skills") if isinstance(slide.get("load_skills"), list) else []),
                *requested_skills,
                *recommended,
            ]
        )
        slide["load_skills"] = merged_load_skills
        if isinstance(context.get("page_skill_directives"), list):
            directives = [str(item or "").strip() for item in context.get("page_skill_directives") or [] if str(item or "").strip()]
            if directives:
                slide["skill_directives"] = directives
        if isinstance(context.get("text_constraints"), dict):
            constraints = dict(context.get("text_constraints") or {})
            if constraints:
                slide["text_constraints"] = constraints
        if isinstance(context.get("image_policy"), dict):
            image_policy = dict(context.get("image_policy") or {})
            if image_policy:
                slide["image_policy"] = image_policy
        page_design_intent = str(context.get("page_design_intent") or "").strip()
        if page_design_intent:
            slide["page_design_intent"] = page_design_intent

        style_variant = str(patch.get("style_variant") or context.get("style_variant") or "").strip().lower()
        palette_key = str(patch.get("palette_key") or context.get("palette_key") or "").strip()
        template_family = str(patch.get("template_family") or context.get("template_family") or "").strip().lower()
        skill_profile = str(patch.get("skill_profile") or context.get("skill_profile") or "").strip()
        if not deck_style_variant and style_variant:
            deck_style_variant = style_variant
        if not deck_palette_key and palette_key:
            deck_palette_key = palette_key
        if not deck_template_family and template_family:
            deck_template_family = template_family
        if not deck_skill_profile and skill_profile:
            deck_skill_profile = skill_profile

        slide_type_final = str(slide.get("slide_type") or "").strip().lower()
        layout_final = str(slide.get("layout_grid") or "").strip().lower()
        if slide_type_final == "content":
            content_slide_index += 1
            if layout_final:
                content_layout_history.append(layout_final)

        runtime["slides"].append(row_runtime)
        planned_slides.append(slide)

    out["slides"] = planned_slides
    if deck_style_variant:
        out["style_variant"] = deck_style_variant
    if deck_palette_key:
        out["palette_key"] = deck_palette_key
    if deck_template_family:
        out["template_family"] = deck_template_family
    if deck_skill_profile:
        out["skill_profile"] = deck_skill_profile
    out["skill_planning_runtime"] = runtime
    return out


def _run_layer1_design_skill_chain(
    *,
    deck_title: str,
    slides: List[Dict[str, Any]],
    requested_style_variant: str,
    requested_palette_key: str,
    requested_template_family: str,
    requested_skill_profile: str,
) -> Dict[str, Any]:
    """Run Layer1 design decision skills before orchestration.

    This mirrors the architecture doc intent: call design skills directly in
    the main path, then feed decisions into orchestration/render.
    """
    effective_style = str(requested_style_variant or "auto").strip().lower() or "auto"
    effective_palette = str(requested_palette_key or "auto").strip() or "auto"
    effective_template = str(requested_template_family or "auto").strip().lower() or "auto"
    effective_skill_profile = str(requested_skill_profile or "auto").strip() or "auto"

    requested_skills = [
        "ppt-orchestra-skill",
        "color-font-skill",
        "design-style-skill",
        "pptx",
    ]
    if effective_template and effective_template not in {"auto"}:
        requested_skills.append("ppt-editing-skill")
    first_slide = dict(slides[0]) if slides and isinstance(slides[0], dict) else {}
    skill_input_slide = {
        "title": str(first_slide.get("title") or deck_title or "").strip(),
        "slide_type": str(first_slide.get("slide_type") or "cover").strip().lower(),
        "layout_grid": str(first_slide.get("layout_grid") or "hero_1").strip().lower(),
        "template_family": "" if effective_template == "auto" else effective_template,
        "skill_profile": effective_skill_profile,
        "slide_data": {
            "title": str(first_slide.get("title") or deck_title or "").strip(),
            "template_family": "" if effective_template == "auto" else effective_template,
            "skill_profile": effective_skill_profile,
        },
    }

    runtime: Dict[str, Any] = {
        "enabled": False,
        "requested_skills": requested_skills,
        "results": [],
        "context": {},
        "reason": "",
    }
    try:
        from src.installed_skill_executor import execute_installed_skill_request

        runtime["enabled"] = True
        skill_output = execute_installed_skill_request(
            {
                "version": 1,
                "requested_skills": requested_skills,
                "slide": skill_input_slide,
                "deck": {
                    "title": deck_title,
                    "topic": deck_title,
                    "total_slides": len(slides),
                    "style_variant": effective_style,
                    "palette_key": effective_palette,
                },
            }
        )
        if _require_direct_skill_runtime():
            _assert_skill_runtime_success(
                stage="layer1_design",
                skill_output=skill_output if isinstance(skill_output, dict) else {},
                requested_skills=requested_skills,
                slide_id=str(skill_input_slide.get("slide_id") or ""),
            )
        runtime["results"] = (
            skill_output.get("results")
            if isinstance(skill_output.get("results"), list)
            else []
        )
        runtime["context"] = (
            skill_output.get("context")
            if isinstance(skill_output.get("context"), dict)
            else {}
        )
        patch = skill_output.get("patch") if isinstance(skill_output.get("patch"), dict) else {}
    except Exception as exc:
        if _require_direct_skill_runtime():
            raise RuntimeError(f"layer1_skill_runtime_unavailable:{str(exc)[:180]}") from exc
        runtime["reason"] = f"layer1_skill_runtime_unavailable:{str(exc)[:180]}"
        patch = {}

    runtime_ctx = runtime.get("context") if isinstance(runtime.get("context"), dict) else {}
    suggested_template = str(
        patch.get("template_family") or runtime_ctx.get("template_family") or ""
    ).strip().lower()
    suggested_style = str(
        patch.get("style_variant") or runtime_ctx.get("style_variant") or ""
    ).strip().lower()
    suggested_palette = str(
        patch.get("palette_key") or runtime_ctx.get("palette_key") or ""
    ).strip()
    suggested_profile = str(
        patch.get("skill_profile") or runtime_ctx.get("skill_profile") or ""
    ).strip()

    if effective_template in {"", "auto"} and suggested_template:
        effective_template = suggested_template
    if effective_style in {"", "auto"} and suggested_style:
        effective_style = suggested_style
    if effective_style in {"", "auto"}:
        effective_style = _derive_style_from_template_family(effective_template)
    if effective_palette in {"", "auto"} and suggested_palette:
        effective_palette = suggested_palette
    if effective_palette in {"", "auto"}:
        effective_palette = "auto"
    if effective_skill_profile in {"", "auto"} and suggested_profile:
        effective_skill_profile = suggested_profile
    if effective_skill_profile in {"", "auto"}:
        if "architecture" in effective_template:
            effective_skill_profile = "architecture"
        elif "hero" in effective_template:
            effective_skill_profile = "cover"
        else:
            effective_skill_profile = "general-content"

    return {
        "style_variant": effective_style,
        "palette_key": effective_palette,
        "template_family": effective_template,
        "skill_profile": effective_skill_profile,
        "runtime": runtime,
    }


def _stable_bucket(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _render_status_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": row.get("id"),
        "project_id": row.get("project_id"),
        "status": row.get("status", "unknown"),
        "progress": row.get("progress", 0),
        "lambda_job_id": row.get("lambda_job_id"),
        "output_url": row.get("output_url"),
        "error": row.get("error"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|(?:\d+[.)]))\s+(.+?)\s*$")
_HTML_RE = re.compile(r"<[^>]+>")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TEMPLATE_RENDERER_SKIP_RATIO_WARN = 0.35
_TEMPLATE_RENDERER_SKIP_RATIO_HIGH = 0.55
_TEMPLATE_RENDERER_REASON_CONCENTRATION_HIGH = 0.75
_TEXT_QA_PLACEHOLDER_RATIO_WARN = 0.12
_TEXT_QA_PLACEHOLDER_RATIO_HIGH = 0.28
_TEXT_QA_MISSING_BODY_RATIO_WARN = 0.20
_TEXT_QA_ASSERTION_COVERAGE_WARN = 0.75
_TEXT_QA_EVIDENCE_COVERAGE_WARN = 0.70
_STRICT_QUALITY_PROFILES = {"high_density_consulting", "investor_pitch", "tech_review"}
_STRICT_TEMPLATE_RENDERER_SKIP_RATIO_FAIL = 0.20
_STRICT_TEMPLATE_RENDERER_REASON_RATIO_FAIL = 0.60
_STRICT_MARKITDOWN_PLACEHOLDER_RATIO_FAIL = 0.22


def _strip_md_text(text: str) -> str:
    cleaned = _HTML_RE.sub(" ", text or "")
    cleaned = cleaned.replace("`", " ").replace("*", " ").replace("_", " ").replace("#", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _prefer_zh(*texts: object) -> bool:
    for text in texts:
        if _CJK_RE.search(str(text or "")):
            return True
    return False


def _normalize_constraint_hardness(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"balanced", "strict"}:
        return normalized
    return "minimal"


def _is_strict_quality_mode(
    *,
    constraint_hardness: object,
    hardness_profile: object,
    route_mode: object,
    quality_profile: object,
) -> bool:
    if _normalize_constraint_hardness(constraint_hardness) == "strict":
        return True
    if str(hardness_profile or "").strip().lower() == "strict":
        return True
    normalized_route = str(route_mode or "").strip().lower()
    normalized_profile = str(quality_profile or "").strip().lower()
    return normalized_route == "refine" and normalized_profile in _STRICT_QUALITY_PROFILES


def _collect_strict_quality_blockers(
    *,
    alerts: List[Dict[str, Any]],
    generator_meta: Optional[Dict[str, Any]],
    template_renderer_summary: Optional[Dict[str, Any]],
    text_qa: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    blockers: List[Dict[str, Any]] = []

    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        severity = str(alert.get("severity") or "").strip().lower()
        if severity not in {"high", "critical"}:
            continue
        blockers.append(
            {
                "code": f"strict_alert_{str(alert.get('code') or 'unknown').strip().lower()}",
                "message": str(alert.get("message") or str(alert.get("code") or "high_severity_alert"))[:220],
            }
        )

    meta_obj = generator_meta if isinstance(generator_meta, dict) else {}
    render_each_obj = meta_obj.get("render_each") if isinstance(meta_obj.get("render_each"), dict) else {}
    subagent_runs = (
        render_each_obj.get("subagent_runs")
        if isinstance(render_each_obj.get("subagent_runs"), list)
        else []
    )
    if subagent_runs:
        enabled_runs = [item for item in subagent_runs if isinstance(item, dict) and bool(item.get("enabled"))]
        if enabled_runs:
            skipped_runs = [item for item in enabled_runs if bool(item.get("skipped"))]
            applied_runs = [item for item in enabled_runs if bool(item.get("applied"))]
            if skipped_runs and not applied_runs and len(skipped_runs) == len(enabled_runs):
                reasons = [
                    str(item.get("reason") or "").strip()
                    for item in skipped_runs
                    if str(item.get("reason") or "").strip()
                ]
                reason_preview = reasons[0][:180] if reasons else "unknown"
                blockers.append(
                    {
                        "code": "strict_subagent_all_skipped",
                        "message": (
                            f"subagent_runs_all_skipped={len(skipped_runs)}/{len(enabled_runs)}; "
                            f"reason={reason_preview}"
                        )[:220],
                    }
                )

    renderer_summary = (
        template_renderer_summary if isinstance(template_renderer_summary, dict) else {}
    )
    skipped_ratio = _to_float(renderer_summary.get("skipped_ratio"), None)
    skipped_slides = int(_to_float(renderer_summary.get("skipped_slides"), 0.0) or 0.0)
    evaluated_slides = int(_to_float(renderer_summary.get("evaluated_slides"), 0.0) or 0.0)
    if (
        skipped_ratio is not None
        and skipped_slides > 0
        and evaluated_slides > 0
        and skipped_ratio >= _STRICT_TEMPLATE_RENDERER_SKIP_RATIO_FAIL
    ):
        blockers.append(
            {
                "code": "strict_template_renderer_fallback_ratio_high",
                "message": (
                    f"template_renderer_fallback_ratio={skipped_ratio:.2f} "
                    f"({skipped_slides}/{evaluated_slides})"
                ),
            }
        )
    reason_ratios = (
        renderer_summary.get("reason_ratios")
        if isinstance(renderer_summary.get("reason_ratios"), dict)
        else {}
    )
    dominant_reason = ""
    dominant_ratio: Optional[float] = None
    for reason, ratio_raw in reason_ratios.items():
        ratio = _to_float(ratio_raw, None)
        if ratio is None:
            continue
        if dominant_ratio is None or ratio > dominant_ratio:
            dominant_reason = str(reason or "").strip() or "unknown"
            dominant_ratio = ratio
    if (
        dominant_ratio is not None
        and dominant_ratio >= _STRICT_TEMPLATE_RENDERER_REASON_RATIO_FAIL
        and skipped_slides >= 2
    ):
        blockers.append(
            {
                "code": "strict_template_renderer_reason_concentrated",
                "message": f"template_renderer_reason={dominant_reason}:{dominant_ratio:.2f}",
            }
        )

    text_obj = text_qa if isinstance(text_qa, dict) else {}
    markitdown_obj = text_obj.get("markitdown") if isinstance(text_obj.get("markitdown"), dict) else {}
    if markitdown_obj:
        if not bool(markitdown_obj.get("ok")):
            blockers.append(
                {
                    "code": "strict_markitdown_unavailable",
                    "message": str(markitdown_obj.get("error") or "markitdown_extraction_failed")[:220],
                }
            )
        md_placeholder_ratio = _to_float(markitdown_obj.get("placeholder_ratio"), None)
        if (
            md_placeholder_ratio is not None
            and md_placeholder_ratio >= _STRICT_MARKITDOWN_PLACEHOLDER_RATIO_FAIL
        ):
            blockers.append(
                {
                    "code": "strict_markitdown_placeholder_ratio_high",
                    "message": f"markitdown_placeholder_ratio={md_placeholder_ratio:.2f}",
                }
            )
        md_issue_codes = (
            markitdown_obj.get("issue_codes")
            if isinstance(markitdown_obj.get("issue_codes"), list)
            else []
        )
        if "markitdown_empty_output" in md_issue_codes:
            blockers.append(
                {
                    "code": "strict_markitdown_empty_output",
                    "message": "markitdown output has no extracted text",
                }
            )

    deduped: List[Dict[str, Any]] = []
    seen_codes: set[str] = set()
    for blocker in blockers:
        code = str(blocker.get("code") or "").strip().lower()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        deduped.append(
            {
                "severity": "high",
                "code": code,
                "message": str(blocker.get("message") or code)[:220],
            }
        )
    return deduped


def _looks_like_garbled_input(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    q = s.count("?")
    if q < 3:
        return False
    ratio = q / max(1, len(s))
    if ratio < 0.15:
        return False
    if _CJK_RE.search(s):
        return False
    return True


def _assert_slides_not_garbled(slides: List[Dict[str, Any]]) -> None:
    suspicious: List[str] = []
    for i, slide in enumerate(slides):
        idx = i + 1
        title = str(slide.get("title") or "")
        if _looks_like_garbled_input(title):
            suspicious.append(f"slide[{idx}].title")
        narration = str(slide.get("narration") or "")
        if _looks_like_garbled_input(narration):
            suspicious.append(f"slide[{idx}].narration")
        for j, el in enumerate(slide.get("elements") or []):
            if not isinstance(el, dict):
                continue
            if str(el.get("type") or "").lower() != "text":
                continue
            content = str(el.get("content") or "")
            if _looks_like_garbled_input(content):
                suspicious.append(f"slide[{idx}].elements[{j}].content")
    if suspicious:
        raise ValueError(
            "Input text appears garbled (too many '?'). Ensure UTF-8 payload encoding."
            f" Fields: {', '.join(suspicious[:8])}"
        )


def _extract_title_and_bullets(markdown: str, fallback_title: str) -> tuple[str, List[str]]:
    title = fallback_title
    bullets: List[str] = []
    for raw in (markdown or "").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("<!--"):
            continue
        heading = _HEADING_RE.match(line)
        if heading and title == fallback_title:
            parsed = _strip_md_text(heading.group(1))
            if parsed:
                title = parsed
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            parsed = _strip_md_text(bullet.group(1))
            if parsed:
                bullets.append(parsed)
            continue
        plain = _strip_md_text(line)
        if plain and len(plain) >= 3:
            bullets.append(plain)

    dedup: List[str] = []
    seen = set()
    for item in bullets:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
        if len(dedup) >= 6:
            break
    return title, dedup


def _extract_script_text(slide: Dict[str, Any]) -> str:
    script = slide.get("script")
    if isinstance(script, list):
        lines: List[str] = []
        for item in script:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    lines.append(text)
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    lines.append(text)
        if lines:
            return " ".join(lines).strip()
    narration = str(slide.get("narration") or "").strip()
    if narration:
        return narration
    speaker_notes = str(slide.get("speaker_notes") or "").strip()
    if speaker_notes:
        return speaker_notes
    return ""


def _normalize_slide_for_renderer(slide: Dict[str, Any], index: int) -> Dict[str, Any]:
    # Layout-style slide (already compatible with SlidePresentation)
    if isinstance(slide.get("elements"), list):
        out = dict(slide)
        out.setdefault("id", f"slide-{index + 1}")
        out.setdefault("order", index)
        out.setdefault("title", f"Slide {index + 1}")
        out.setdefault("duration", max(3, int(float(slide.get("duration") or 6))))
        out.setdefault("background", {"type": "solid", "color": "#f8fafc"})
        if "narrationAudioUrl" not in out and slide.get("narration_audio_url"):
            out["narrationAudioUrl"] = slide.get("narration_audio_url")
        if "narration" not in out:
            out["narration"] = _extract_script_text(slide)
        return out

    # Semantic slide (markdown/script/actions): convert into layout text block.
    markdown = str(slide.get("markdown") or "")
    fallback_title = f"Slide {index + 1}"
    title, bullets = _extract_title_and_bullets(markdown, fallback_title)
    if not bullets:
        stripped = _strip_md_text(markdown)
        bullets = [stripped] if stripped else ["Content unavailable"]
    lines_html = "<br/>".join(f"&bull; {html.escape(item)}" for item in bullets[:6])

    narration = _extract_script_text(slide)
    return {
        "id": str(slide.get("id") or f"slide-{index + 1}"),
        "order": index,
        "title": title,
        "elements": [
            {
                "id": f"content-{index + 1}",
                "type": "text",
                "left": 96,
                "top": 210,
                "width": 1728,
                "height": 760,
                "content": lines_html,
                "style": {
                    "fontSize": 52,
                    "lineHeight": 1.35,
                    "color": "#1e293b",
                },
            }
        ],
        "background": {"type": "solid", "color": "#f8fafc"},
        "narration": narration,
        "narrationAudioUrl": slide.get("narration_audio_url") or slide.get("narrationAudioUrl"),
        "duration": max(3, int(float(slide.get("duration") or 6))),
    }


def _is_image_slide(slide: Dict[str, Any]) -> bool:
    if not isinstance(slide, dict):
        return False
    image_url = str(slide.get("imageUrl") or slide.get("image_url") or "").strip()
    return bool(image_url)


def _normalize_image_slide_for_renderer(slide: Dict[str, Any]) -> Dict[str, Any]:
    image_url = str(slide.get("imageUrl") or slide.get("image_url") or "").strip()
    if not image_url:
        raise ValueError("image slide missing imageUrl")
    audio_url = str(slide.get("audioUrl") or slide.get("audio_url") or "").strip()
    duration = max(3.0, float(slide.get("duration") or 6.0))
    out: Dict[str, Any] = {"imageUrl": image_url, "duration": duration}
    if audio_url:
        out["audioUrl"] = audio_url
    return out


def _build_image_video_slides(
    image_urls: List[str],
    slides: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, url in enumerate(image_urls):
        src = slides[idx] if idx < len(slides) else {}
        audio_url = str(src.get("narration_audio_url") or src.get("narrationAudioUrl") or "").strip()
        duration = max(3.0, float(src.get("duration") or 6.0))
        safe_image_url = _presign_r2_get_url_if_needed(url)
        safe_audio_url = _presign_r2_get_url_if_needed(audio_url) if audio_url else ""
        item: Dict[str, Any] = {
            "imageUrl": safe_image_url,
            "duration": duration,
        }
        if safe_audio_url:
            item["audioUrl"] = safe_audio_url
        out.append(item)
    return out


def _presign_r2_get_url_if_needed(url: str, expires: int = 24 * 3600) -> str:
    raw = str(url or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return raw
    if "X-Amz-Signature=" in raw or "x-amz-signature=" in raw.lower():
        return raw

    configured_public = str(os.getenv("R2_PUBLIC_BASE", "")).strip()
    configured_host = urlparse(configured_public).netloc.lower() if configured_public else ""
    configured_hosts = {
        host.strip().lower()
        for host in str(os.getenv("R2_PUBLIC_HOSTS", "")).split(",")
        if host.strip()
    }
    if configured_host:
        configured_hosts.add(configured_host)
    host = parsed.netloc.lower()
    host_allowed = False
    if configured_hosts:
        host_allowed = host in configured_hosts
    else:
        host_allowed = (
            host.endswith(".r2.dev")
            or host.endswith(".autoviralvid.com")
        )
    if not host_allowed:
        return raw

    key = parsed.path.lstrip("/")
    if not key:
        return raw

    try:
        from src.r2 import get_r2_client

        r2 = get_r2_client()
        if not r2:
            return raw
        bucket = os.getenv("R2_BUCKET", "video")
        signed = r2.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires,
        )
        return str(signed or raw)
    except Exception:
        return raw


def _layout_to_slide_type(layout: str) -> str:
    normalized = str(layout or "").strip().lower()
    if normalized == "cover":
        return "cover"
    if normalized == "summary":
        return "summary"
    if normalized in {"toc", "table_of_contents"}:
        return "toc"
    if normalized in {"divider", "section"}:
        return "divider"
    return "content"


def _collect_stage_diagnostics(prefix: str, messages: List[str], limit: int = 10) -> List[str]:
    out: List[str] = []
    for msg in messages[: max(0, limit)]:
        text = str(msg or "").strip()
        if not text:
            continue
        out.append(f"{prefix}: {text}")
    return out


def _extract_plan_slide_title(slide: Dict[str, Any], fallback: str) -> str:
    blocks = slide.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if str(block.get("block_type") or "").strip().lower() != "title":
                continue
            text = str(block.get("content") or "").strip()
            if text:
                return text[:200]
    title = str(slide.get("title") or "").strip()
    if title:
        return title[:200]
    return fallback


def _infer_semantic_page_type(layout_grid: str, blocks: List[Dict[str, Any]]) -> str:
    layout = str(layout_grid or "").strip().lower()
    types = {_as_block_type(block) for block in blocks if isinstance(block, dict)}
    if layout == "timeline" or "timeline" in types:
        return "timeline"
    if "table" in types:
        return "table"
    if any(t in {"chart", "kpi"} for t in types):
        return "data_visualization"
    has_image = "image" in types
    has_textual = bool(types & {"body", "list", "quote", "icon_text", "subtitle", "text"})
    if has_image and has_textual:
        return "mixed_media"
    if has_image:
        return "image_showcase"
    if layout in {"split_2", "asymmetric_2", "grid_2"}:
        return "comparison"
    return "content"


_LAYOUT_CARD_SLOTS: Dict[str, List[str]] = {
    "hero_1": ["main"],
    "split_2": ["left", "right"],
    "asymmetric_2": ["major", "minor"],
    "grid_3": ["c1", "c2", "c3"],
    "grid_4": ["tl", "tr", "bl", "br"],
    "bento_5": ["hero", "s1", "s2", "s3", "s4"],
    "bento_6": ["h1", "h2", "s1", "s2", "s3", "s4"],
    "timeline": ["t1", "t2", "t3", "t4", "t5"],
    "template_canvas": ["title", "body", "list", "visual", "kpi"],
}


def _preferred_slots(layout: str, position: str, block_type: str) -> List[str]:
    layout_key = str(layout or "").strip().lower()
    position_key = str(position or "").strip().lower()
    block_type_key = str(block_type or "").strip().lower()
    if layout_key == "hero_1":
        return ["main"]
    if layout_key == "template_canvas":
        if block_type_key == "title":
            return ["title"]
        if block_type_key in {"body", "subtitle", "quote"}:
            return ["body", "list"]
        if block_type_key in {"list", "icon_text"}:
            return ["list", "body"]
        if block_type_key in {"image", "diagram", "workflow", "chart", "table"}:
            return ["visual", "kpi"]
        if block_type_key == "kpi":
            return ["kpi", "visual"]
        return ["body", "list", "visual", "kpi"]

    lookup: Dict[str, List[str]] = {
        "top": ["tl", "tr", "h1", "h2", "left", "major", "c1", "c2", "s1", "s2", "t1", "t2"],
        "left": ["left", "major", "c1", "tl", "bl", "h1", "s1", "t1", "t2"],
        "right": ["right", "minor", "c3", "tr", "br", "h2", "s3", "t4", "t5"],
        "center": ["main", "hero", "c2", "h1", "h2", "s2", "t3"],
        "bottom": ["bl", "br", "s3", "s4", "t4", "t5"],
        "top_left": ["tl", "left", "major", "h1", "s1", "t1"],
        "top_right": ["tr", "right", "minor", "h2", "s2", "t2"],
        "bottom_left": ["bl", "left", "major", "s3", "t4"],
        "bottom_right": ["br", "right", "minor", "s4", "t5"],
    }
    if block_type_key == "title":
        return ["main", "hero", "left", "major", "c1", "tl", "h1", "t1"]
    return lookup.get(position_key, [])


def _assign_layout_card_ids(layout_grid: str, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    slots = list(_LAYOUT_CARD_SLOTS.get(str(layout_grid or "").strip().lower(), []))
    used: set[str] = set()
    normalized: List[Dict[str, Any]] = []

    for block in blocks:
        out = dict(block)
        card_id = str(out.get("card_id") or "").strip()
        generic_fallback = bool(re.fullmatch(r"card-\d+", card_id))
        if card_id and not generic_fallback and card_id not in used:
            used.add(card_id)
            normalized.append(out)
            continue
        out["card_id"] = ""
        normalized.append(out)

    for idx, block in enumerate(normalized):
        existing = str(block.get("card_id") or "").strip()
        if existing:
            continue
        position = str(block.get("position") or "").strip().lower()
        btype = str(block.get("block_type") or block.get("type") or "").strip().lower()
        if btype == "title":
            chosen = "title"
            if chosen in used:
                chosen = f"title_{idx + 1}"
            block["card_id"] = chosen
            used.add(chosen)
            continue
        preferred = _preferred_slots(layout_grid, position, btype)

        chosen = ""
        for candidate in preferred:
            if candidate in slots and candidate not in used:
                chosen = candidate
                break
        if not chosen:
            for candidate in slots:
                if candidate not in used:
                    chosen = candidate
                    break
        if not chosen:
            chosen = f"card-{idx + 1}"
        block["card_id"] = chosen
        used.add(chosen)

    return normalized


def _presentation_plan_to_render_payload(plan: PresentationPlan) -> Dict[str, Any]:
    slides: List[Dict[str, Any]] = []
    for idx, slide in enumerate(plan.slides):
        raw = slide.model_dump()
        title = _extract_plan_slide_title(raw, fallback=f"Slide {idx + 1}")
        raw_slide_type = str(raw.get("slide_type") or "content").strip().lower()
        layout_grid = str(raw.get("layout_grid") or "split_2")
        normalized_slide_type = (
            raw_slide_type
            if raw_slide_type in {"cover", "summary", "toc", "divider", "content"}
            else "content"
        )
        blocks = raw.get("blocks") if isinstance(raw.get("blocks"), list) else []
        normalized_blocks: List[Dict[str, Any]] = []
        for block_idx, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            normalized = dict(block)
            normalized.setdefault("card_id", f"card-{block_idx + 1}")
            normalized_blocks.append(normalized)
        normalized_blocks = _assign_layout_card_ids(layout_grid, normalized_blocks)
        semantic_page_type = (
            normalized_slide_type
            if normalized_slide_type in {"cover", "summary", "toc", "divider"}
            else _infer_semantic_page_type(layout_grid, normalized_blocks)
        )
        content_strategy = (
            raw.get("content_strategy")
            if isinstance(raw.get("content_strategy"), dict)
            else {}
        )

        payload_slide = {
            "id": f"slide-{idx + 1}",
            "page_number": int(raw.get("page_number") or (idx + 1)),
            "slide_type": normalized_slide_type,
            "page_type": semantic_page_type,
            "subtype": semantic_page_type,
            "layout_grid": layout_grid,
            "bg_style": str(raw.get("bg_style") or "light"),
            "image_keywords": raw.get("image_keywords") or [],
            "title": title,
            "narration": str(raw.get("notes_for_designer") or ""),
            "blocks": normalized_blocks,
        }
        if content_strategy:
            payload_slide["content_strategy"] = content_strategy
        slides.append(payload_slide)

    return {
        "title": plan.title,
        "theme": {"palette": plan.theme, "style": plan.style},
        "slides": slides,
    }


def _pipeline_artifact_dir(run_id: str) -> Path:
    return Path(__file__).resolve().parents[1] / "renders" / "tmp" / "ppt_pipeline" / run_id


def _write_pipeline_artifact(run_id: str, name: str, payload: Dict[str, Any]) -> None:
    def _json_default(value: Any) -> Any:
        if isinstance(value, (bytes, bytearray)):
            return {"__type__": "bytes", "length": len(value)}
        return str(value)

    out_dir = _pipeline_artifact_dir(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.json"
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


_LAYOUT_CARD_COUNTS = {
    "hero_1": 1,
    "split_2": 2,
    "asymmetric_2": 2,
    "grid_3": 3,
    "grid_4": 4,
    "bento_5": 5,
    "bento_6": 6,
    "timeline": 5,
    "template_canvas": 5,
}


def _brand_placeholder_svg_data_uri(title: str = "Brand Visual Placeholder") -> str:
    safe = html.escape(str(title or "Brand Visual Placeholder"), quote=True)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        '<rect width="1200" height="675" rx="28" fill="#0D1630" stroke="#1E335E" stroke-width="3"/>'
        '<rect x="56" y="54" width="8" height="34" rx="4" fill="#2F7BFF"/>'
        f'<text x="80" y="80" fill="#E8F0FF" font-size="36" font-family="Segoe UI, Arial" font-weight="700">{safe}</text>'
        '<text x="80" y="125" fill="#95A8CC" font-size="24" font-family="Segoe UI, Arial">brand visual placeholder</text>'
        '<rect x="80" y="170" width="1040" height="440" rx="22" fill="#121F3D" stroke="#1E335E" stroke-width="2" stroke-dasharray="10 8"/>'
        "</svg>"
    )
    return f"data:image/svg+xml;utf8,{url_quote(svg)}"


_ABSTRACT_IMAGE_INTENT_TOKENS = {
    "strategy",
    "framework",
    "process",
    "workflow",
    "architecture",
    "platform",
    "model",
    "capability",
    "concept",
    "roadmap",
    "策略",
    "框架",
    "流程",
    "架构",
    "模型",
    "机制",
    "能力",
    "平台",
    "路线图",
}

_ICON_BG_TOKEN_MAP: Dict[str, str] = {
    "growth": "↗",
    "trend": "↗",
    "sales": "$",
    "finance": "$",
    "security": "S",
    "cloud": "☁",
    "ai": "✦",
    "automation": "⚙",
    "workflow": "⇄",
    "strategy": "◎",
    "roadmap": "◈",
    "数据": "◍",
    "增长": "↗",
    "流程": "⇄",
    "架构": "◈",
    "安全": "S",
}


def _is_abstract_image_intent(*, keywords: List[str], slide_title: str, block_title: str) -> bool:
    blob = " ".join([*keywords, str(slide_title or ""), str(block_title or "")]).lower()
    return any(token in blob for token in _ABSTRACT_IMAGE_INTENT_TOKENS)


def _resolve_icon_bg_symbol(*, keywords: List[str], slide_title: str, block_title: str) -> str:
    blob = " ".join([*keywords, str(slide_title or ""), str(block_title or "")]).lower()
    for token, symbol in _ICON_BG_TOKEN_MAP.items():
        if token in blob:
            return symbol
    return "◆"


def _ai_svg_visual_data_uri(title: str, subtitle: str = "") -> str:
    heading = html.escape(str(title or "Visual concept"), quote=True)
    sub = html.escape(str(subtitle or "AI generated vector visual"), quote=True)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        "<defs>"
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0%" stop-color="#0A1021"/>'
        '<stop offset="100%" stop-color="#152C57"/>'
        "</linearGradient>"
        '<radialGradient id="orb" cx="50%" cy="50%" r="60%">'
        '<stop offset="0%" stop-color="#18E0D1" stop-opacity="0.9"/>'
        '<stop offset="100%" stop-color="#18E0D1" stop-opacity="0"/>'
        "</radialGradient>"
        "</defs>"
        '<rect width="1200" height="675" rx="28" fill="url(#bg)"/>'
        '<circle cx="920" cy="180" r="180" fill="url(#orb)"/>'
        '<rect x="86" y="126" width="720" height="420" rx="24" fill="#0F1F3E" stroke="#2F7BFF" stroke-width="2"/>'
        '<path d="M160 430 C260 320 360 360 460 290 C540 240 610 260 700 200" stroke="#18E0D1" stroke-width="8" fill="none" stroke-linecap="round"/>'
        '<circle cx="160" cy="430" r="12" fill="#18E0D1"/><circle cx="700" cy="200" r="12" fill="#18E0D1"/>'
        f'<text x="116" y="190" fill="#E8F0FF" font-size="44" font-family="Segoe UI, Arial" font-weight="700">{heading}</text>'
        f'<text x="116" y="236" fill="#95A8CC" font-size="24" font-family="Segoe UI, Arial">{sub}</text>'
        "</svg>"
    )
    return f"data:image/svg+xml;utf8,{url_quote(svg)}"


def _icon_background_svg_data_uri(title: str, symbol: str) -> str:
    heading = html.escape(str(title or "Visual anchor"), quote=True)
    icon = html.escape(str(symbol or "◆"), quote=True)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        '<rect width="1200" height="675" rx="28" fill="#0D1630"/>'
        '<rect x="100" y="90" width="1000" height="495" rx="30" fill="#122448" stroke="#2F7BFF" stroke-width="2"/>'
        '<circle cx="600" cy="300" r="120" fill="#1A335F" stroke="#18E0D1" stroke-width="4"/>'
        f'<text x="600" y="328" text-anchor="middle" fill="#E8F0FF" font-size="110" font-family="Segoe UI Symbol, Segoe UI Emoji, Arial">{icon}</text>'
        f'<text x="600" y="492" text-anchor="middle" fill="#C9D8F0" font-size="38" font-family="Segoe UI, Arial">{heading}</text>'
        "</svg>"
    )
    return f"data:image/svg+xml;utf8,{url_quote(svg)}"


def _build_image_search_query(
    *,
    deck_title: str,
    slide_title: str,
    block_title: str,
    keywords: List[str],
    hl: str,
) -> str:
    parts: List[str] = []
    for item in [slide_title, block_title, *keywords[:3], deck_title]:
        text = str(item or "").strip()
        if not text:
            continue
        if text in parts:
            continue
        parts.append(text)
        if len(parts) >= 4:
            break
    if hl == "zh-cn":
        return " ".join(parts) if parts else "科技 商务 场景 图"
    return " ".join(parts) if parts else "technology business scene image"


def _resolve_template_family(slide: Dict[str, Any]) -> str:
    st = str(
        slide.get("page_type")
        or slide.get("slide_type")
        or slide.get("subtype")
        or "content"
    ).strip().lower()
    layout = str(slide.get("layout_grid") or slide.get("layout") or "split_2").strip().lower()
    requested = ""
    if bool(slide.get("template_lock")):
        requested = str(slide.get("template_family") or slide.get("template_id") or "")
    return resolve_template_for_slide(
        slide=slide if isinstance(slide, dict) else {},
        slide_type=st,
        layout_grid=layout,
        requested_template=requested,
        desired_density=str(slide.get("content_density") or "balanced"),
    )


def _template_profiles(template_family: str) -> Dict[str, str]:
    return shared_template_profiles(template_family)


def _as_block_type(block: Dict[str, Any]) -> str:
    return str(block.get("block_type") or block.get("type") or "").strip().lower()


_SPLIT_TEXT_RE = re.compile(r"[;；,\n，。.!?]+")
_TEXTUAL_BLOCK_TYPES = {
    "title",
    "subtitle",
    "text",
    "body",
    "list",
    "quote",
    "icon_text",
    "comparison",
}
_VISUAL_BLOCK_TYPES = {"image", "chart", "kpi", "table", "workflow", "diagram"}


def _normalize_text_key(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%+.-]", "", lowered)


def _has_image_block(blocks: List[Dict[str, Any]]) -> bool:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if _as_block_type(block) != "image":
            continue
        return True
    return False


def _extract_block_text(block: Dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        parts: List[str] = []
        for key in ("title", "body", "text", "label", "caption", "description"):
            value = str(content.get(key) or "").strip()
            if value:
                parts.append(value)
        if parts:
            return " ".join(parts).strip()
    data = block.get("data")
    if isinstance(data, dict):
        parts = []
        for key in ("title", "label", "description"):
            value = str(data.get(key) or "").strip()
            if value:
                parts.append(value)
        if parts:
            return " ".join(parts).strip()
    return ""


def _sanitize_placeholder_text(text: str, *, prefer_zh: bool) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return cleaned
    # Normalize common masked placeholders such as 400-XXX-XXXX.
    cleaned = re.sub(r"(?<![0-9A-Za-z])X{3,}(?![0-9A-Za-z])", lambda m: "0" * len(m.group(0)), cleaned, flags=re.IGNORECASE)
    replacements = [
        (re.compile(r"\?\?\?"), "待确认" if prefer_zh else "TBC"),
        (re.compile(r"\bxxxx\b", flags=re.IGNORECASE), "0000"),
        (re.compile(r"\btodo\b", flags=re.IGNORECASE), "待确认" if prefer_zh else "TBC"),
        (re.compile(r"\btbd\b", flags=re.IGNORECASE), "待确认" if prefer_zh else "TBC"),
        (re.compile(r"\bplaceholder\b", flags=re.IGNORECASE), "示意信息" if prefer_zh else "reference"),
        (re.compile(r"待补充"), "已补充"),
        (re.compile(r"请填写"), "请联系顾问"),
        (re.compile(r"占位符"), "示意信息"),
    ]
    for pattern, target in replacements:
        cleaned = pattern.sub(target, cleaned)
    return cleaned


def _extract_slide_keypoints(slide: Dict[str, Any], title_text: str) -> List[str]:
    tokens: List[str] = [title_text, str(slide.get("narration") or "").strip()]
    image_keywords = slide.get("image_keywords")
    if isinstance(image_keywords, list):
        tokens.extend(str(item or "").strip() for item in image_keywords)
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        tokens.append(_extract_block_text(block))

    phrases: List[str] = []
    seen = set()
    for token in tokens:
        for part in _SPLIT_TEXT_RE.split(str(token or "")):
            phrase = str(part or "").strip()
            if len(phrase) < 4:
                continue
            key = _normalize_text_key(phrase)
            if not key or key in seen:
                continue
            seen.add(key)
            phrases.append(phrase)
            if len(phrases) >= 8:
                return phrases
    return phrases


def _extract_numeric_values(text: str) -> List[float]:
    values: List[float] = []
    for match in re.finditer(r"-?\d+(?:\.\d+)?", str(text or "")):
        try:
            values.append(float(match.group(0)))
        except Exception:
            continue
    return values


def _contextual_fallback_point(title: str, *, index: int, prefer_zh: bool) -> str:
    topic = re.sub(r"\s+", " ", str(title or "").strip())
    topic = re.sub(r"[：:|丨\-—_]+", " ", topic).strip()
    if not topic:
        topic = "本页主题" if prefer_zh else "This topic"
    topic_short = topic[:18] if prefer_zh else topic[:24]
    if prefer_zh:
        suffixes = ["市场机会", "核心能力", "技术亮点", "实施路径", "商业价值", "合作模式", "落地动作", "风险对策"]
        suffix = suffixes[index % len(suffixes)]
        return f"{topic_short}：{suffix}"
    suffixes = [
        "market opportunity",
        "core capability",
        "technical highlight",
        "execution path",
        "business value",
        "collaboration model",
        "next action",
        "risk control",
    ]
    suffix = suffixes[index % len(suffixes)]
    return f"{topic_short}: {suffix}"


def _chart_data_from_keypoints(
    keypoints: List[str],
    numeric_values: List[float],
    *,
    prefer_zh: bool,
) -> Dict[str, Any]:
    labels: List[str] = []
    for item in keypoints:
        text = str(item or "").strip()
        if not text:
            continue
        label = text[:12]
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= 4:
            break
    if len(labels) < 3:
        labels.extend(
            [
                "方案一" if prefer_zh else "Plan A",
                "方案二" if prefer_zh else "Plan B",
                "方案三" if prefer_zh else "Plan C",
            ][len(labels):]
        )
    labels = labels[:4]

    points: List[float] = []
    for num in numeric_values:
        val = abs(float(num))
        if val < 1e-6:
            continue
        points.append(round(val, 2))
        if len(points) >= len(labels):
            break
    while len(points) < len(labels):
        seed = 58.0 + (len(points) * 11.0)
        points.append(round(seed, 2))

    return {
        "labels": labels,
        "datasets": [
            {
                "label": "关键指标" if prefer_zh else "Key metric",
                "data": points[: len(labels)],
            }
        ],
    }


def _make_visual_contract_block(
    *,
    preferred_types: List[str],
    keypoints: List[str],
    numeric_values: List[float],
    prefer_zh: bool,
    card_id: str,
    position: str,
) -> Dict[str, Any]:
    requested = [str(item or "").strip().lower() for item in preferred_types if str(item or "").strip()]
    requested_set = set(requested)
    label = keypoints[0] if keypoints else ("核心指标" if prefer_zh else "Key metric")

    known_types = {"image", "workflow", "diagram", "kpi", "chart", "table"}
    target_type = next((item for item in requested if item in known_types), "")
    if not target_type:
        if "kpi" in requested_set:
            target_type = "kpi"
        elif "workflow" in requested_set:
            target_type = "workflow"
        elif "diagram" in requested_set:
            target_type = "diagram"
        elif "image" in requested_set:
            target_type = "image"
        else:
            target_type = "chart"

    if target_type == "image":
        image_title = label[:48] if label else ("核心视觉" if prefer_zh else "Visual Focus")
        image_keywords = [item[:24] for item in keypoints[:4] if str(item or "").strip()]
        if not image_keywords and image_title:
            image_keywords = [image_title]
        return {
            "block_type": "image",
            "card_id": card_id,
            "position": position,
            "content": {
                "title": image_title,
                "url": _brand_placeholder_svg_data_uri(image_title or "Brand Visual"),
            },
            "data": {
                "keywords": image_keywords,
                "source_type": "placeholder",
            },
            "emphasis": image_keywords[:2] or [image_title[:14]],
        }

    if target_type == "kpi" and numeric_values:
        base = abs(float(numeric_values[0]))
        trend = 8.0 if len(numeric_values) < 2 else (float(numeric_values[1]) - float(numeric_values[0]))
        if abs(base) < 1e-6:
            base = 68.0
        if abs(trend) < 1e-6:
            trend = 6.0
        return {
            "block_type": "kpi",
            "card_id": card_id,
            "position": position,
            "data": {
                "number": round(base, 2),
                "unit": "%",
                "trend": round(trend, 2),
                "label": label,
            },
            "content": label,
            "emphasis": [str(round(base, 2))],
        }

    if target_type in {"workflow", "diagram"}:
        steps = keypoints[:4]
        if len(steps) < 3:
            steps.extend(
                [
                    "问题识别" if prefer_zh else "Problem",
                    "方案执行" if prefer_zh else "Execution",
                    "结果验证" if prefer_zh else "Validation",
                ][len(steps):]
            )
        text = " -> ".join(steps[:4])
        return {
            "block_type": target_type,
            "card_id": card_id,
            "position": position,
            "content": text,
            "emphasis": steps[:2],
        }

    chart_data = _chart_data_from_keypoints(keypoints, numeric_values, prefer_zh=prefer_zh)
    return {
        "block_type": "chart",
        "card_id": card_id,
        "position": position,
        "data": chart_data,
        "content": chart_data,
        "emphasis": [str(chart_data["datasets"][0]["data"][0])],
    }


def _dedupe_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    visual_types = {"image", "chart", "kpi", "table", "workflow", "diagram"}
    for block in blocks:
        btype = _as_block_type(block) or "text"
        text = _extract_block_text(block)
        text_key = _normalize_text_key(text)
        if btype in visual_types and text_key:
            signature = f"{btype}:{text_key}"
        else:
            signature = (
                f"text:{text_key}"
                if btype != "title" and text_key
                else f"{btype}:{text_key}"
            )
        if signature in seen and signature != f"{btype}:":
            continue
        seen.add(signature)
        out.append(block)
    return out


def _auto_emphasis(block: Dict[str, Any], fallback_keywords: List[str]) -> List[str]:
    current = block.get("emphasis")
    if isinstance(current, list):
        valid = [str(item).strip() for item in current if str(item).strip()]
        if valid:
            return valid[:4]
    text = _extract_block_text(block)
    emphasis: List[str] = []
    numbers = re.findall(r"\d+(?:\.\d+)?%?", text)
    emphasis.extend(numbers[:2])
    for kw in fallback_keywords:
        if kw and kw not in emphasis:
            emphasis.append(kw)
        if len(emphasis) >= 3:
            break
    return emphasis[:3]


def _trim_blocks_to_layout_capacity(
    layout: str,
    blocks: List[Dict[str, Any]],
    *,
    min_text_non_visual: int = 0,
    min_visual: int = 0,
    visual_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Keep blocks within layout capacity while preserving contract feasibility."""
    layout_key = str(layout or "").strip().lower()
    card_capacity = _LAYOUT_CARD_COUNTS.get(layout_key, 0)
    if card_capacity <= 0:
        return blocks

    visual_type_set = {
        str(item or "").strip().lower()
        for item in (visual_types or [])
        if str(item or "").strip()
    }
    if not visual_type_set:
        visual_type_set = set(_VISUAL_BLOCK_TYPES)

    def _is_visual_block(block: Dict[str, Any]) -> bool:
        return _as_block_type(block) in visual_type_set

    def _is_text_non_visual_block(block: Dict[str, Any]) -> bool:
        btype = _as_block_type(block)
        return btype in _TEXTUAL_BLOCK_TYPES and btype != "title" and btype not in visual_type_set

    title_blocks = [b for b in blocks if _as_block_type(b) == "title"]
    non_title_blocks = [b for b in blocks if _as_block_type(b) != "title"]
    if len(non_title_blocks) <= card_capacity and (
        len([b for b in non_title_blocks if _is_text_non_visual_block(b)]) >= max(0, int(min_text_non_visual))
        and len([b for b in non_title_blocks if _is_visual_block(b)]) >= max(0, int(min_visual))
    ):
        return ([title_blocks[0]] if title_blocks else []) + non_title_blocks

    def _same_text(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        return _normalize_text_key(_extract_block_text(a)) == _normalize_text_key(
            _extract_block_text(b)
        )

    selected: List[Dict[str, Any]] = []
    required_text = max(0, int(min_text_non_visual))
    required_visual = max(0, int(min_visual))

    for block in non_title_blocks:
        if len(selected) >= card_capacity:
            break
        if not _is_text_non_visual_block(block):
            continue
        if any(block is cur for cur in selected):
            continue
        if any(_same_text(block, cur) for cur in selected):
            continue
        selected.append(block)
        if len([b for b in selected if _is_text_non_visual_block(b)]) >= required_text:
            break

    for block in non_title_blocks:
        if len(selected) >= card_capacity:
            break
        if not _is_visual_block(block):
            continue
        if any(block is cur for cur in selected):
            continue
        if any(_same_text(block, cur) for cur in selected):
            continue
        selected.append(block)
        if len([b for b in selected if _is_visual_block(b)]) >= required_visual:
            break

    for block in non_title_blocks:
        if len(selected) >= card_capacity:
            break
        if any(block is cur for cur in selected):
            continue
        if any(_same_text(block, cur) for cur in selected):
            continue
        selected.append(block)

    trimmed = ([title_blocks[0]] if title_blocks else []) + selected[:card_capacity]
    return trimmed


def _ensure_content_contract(
    slide: Dict[str, Any],
    *,
    min_content_blocks: int = 2,
    blank_area_max_ratio: float = 0.45,
    require_image_anchor: bool = False,
) -> Dict[str, Any]:
    out = dict(slide)
    if not str(out.get("content_density") or "").strip():
        out["content_density"] = "dense" if int(min_content_blocks or 2) >= 3 else "balanced"
    slide_type = str(out.get("slide_type") or "").strip().lower()
    terminal_slide = slide_type in {"cover", "summary", "toc", "divider", "hero_1"}

    blocks = out.get("blocks")
    if not isinstance(blocks, list):
        blocks = []
    fixed: List[Dict[str, Any]] = [dict(b) for b in blocks if isinstance(b, dict)]
    fixed = _dedupe_blocks(fixed)

    title_text = str(out.get("title") or "Core Insight").strip() or "Core Insight"
    title_key = _normalize_text_key(title_text)
    prefer_zh = _prefer_zh(title_text, out.get("narration"), *(out.get("image_keywords") or []))
    title_text = _sanitize_placeholder_text(title_text, prefer_zh=prefer_zh)
    title_key = _normalize_text_key(title_text)
    out["title"] = title_text
    if str(out.get("narration") or "").strip():
        out["narration"] = _sanitize_placeholder_text(str(out.get("narration") or ""), prefer_zh=prefer_zh)
    if str(out.get("speaker_notes") or "").strip():
        out["speaker_notes"] = _sanitize_placeholder_text(str(out.get("speaker_notes") or ""), prefer_zh=prefer_zh)
    elements = out.get("elements")
    if isinstance(elements, list):
        cleaned_elements: List[Dict[str, Any]] = []
        for element in elements:
            if not isinstance(element, dict):
                continue
            el = dict(element)
            if str(el.get("type") or "").strip().lower() == "text":
                el["content"] = _sanitize_placeholder_text(str(el.get("content") or ""), prefer_zh=prefer_zh)
            cleaned_elements.append(el)
        out["elements"] = cleaned_elements
    cleaned_fixed: List[Dict[str, Any]] = []
    for block in fixed:
        b = dict(block)
        content_obj = b.get("content")
        if isinstance(content_obj, str):
            b["content"] = _sanitize_placeholder_text(content_obj, prefer_zh=prefer_zh)
        elif isinstance(content_obj, dict):
            cc = dict(content_obj)
            for key in ("title", "body", "text", "label", "caption", "description"):
                if key in cc and isinstance(cc.get(key), str):
                    cc[key] = _sanitize_placeholder_text(str(cc.get(key) or ""), prefer_zh=prefer_zh)
            b["content"] = cc
        data_obj = b.get("data")
        if isinstance(data_obj, dict):
            dd = dict(data_obj)
            for key in ("title", "label", "description"):
                if key in dd and isinstance(dd.get(key), str):
                    dd[key] = _sanitize_placeholder_text(str(dd.get(key) or ""), prefer_zh=prefer_zh)
            b["data"] = dd
        cleaned_fixed.append(b)
    fixed = cleaned_fixed
    fixed = _dedupe_blocks(fixed)

    keypoints = [
        point
        for point in _extract_slide_keypoints(out, title_text)
        if _normalize_text_key(point) != title_key
    ]
    numeric_source = " ".join([title_text, str(out.get("narration") or "")] + keypoints)
    numeric_values = _extract_numeric_values(numeric_source)

    if not terminal_slide:
        has_title = any(_as_block_type(block) == "title" for block in fixed)
        has_body_or_list = any(_as_block_type(block) in {"body", "list"} for block in fixed)
        has_anchor = any(_as_block_type(block) in {"image", "chart", "kpi", "workflow", "diagram", "table"} for block in fixed)
        has_image_anchor = _has_image_block(fixed)

        if not has_title:
            fixed.insert(
                0,
                {
                    "block_type": "title",
                    "card_id": "title",
                    "position": "top",
                    "content": title_text,
                    "emphasis": [],
                },
            )

        if not has_body_or_list:
            fallback_points = keypoints[:3]
            if len(fallback_points) < 3:
                fallback_points.extend(
                    [
                        "核心结论" if prefer_zh else "Core insight",
                        "关键论据" if prefer_zh else "Key evidence",
                        "落地动作" if prefer_zh else "Execution action",
                    ][: 3 - len(fallback_points)]
                )
            fixed.append(
                {
                    "block_type": "list",
                    "card_id": "list_main",
                    "position": "left",
                    "content": ";".join(fallback_points[:3]),
                    "emphasis": fallback_points[:2],
                }
            )

        if not has_anchor:
            fixed.append(
                _make_visual_contract_block(
                    preferred_types=["image", "chart", "kpi"] if require_image_anchor else ["chart", "kpi", "image"],
                    keypoints=keypoints,
                    numeric_values=numeric_values,
                    prefer_zh=prefer_zh,
                    card_id="visual_anchor",
                    position="right",
                )
            )
            has_image_anchor = _has_image_block(fixed)

        if require_image_anchor and not has_image_anchor:
            fixed.append(
                _make_visual_contract_block(
                    preferred_types=["image"],
                    keypoints=keypoints,
                    numeric_values=numeric_values,
                    prefer_zh=prefer_zh,
                    card_id="image_anchor",
                    position="right",
                )
            )

        layout = str(out.get("layout_grid") or out.get("layout") or "").strip().lower()
        card_count = _LAYOUT_CARD_COUNTS.get(layout, max(2, len(fixed)))
        min_non_title_blocks = max(2, int((card_count * 0.55) + 0.999))
        non_title_count = len([b for b in fixed if _as_block_type(b) != "title"])
        filler_idx = 0
        while non_title_count < min_non_title_blocks:
            item = keypoints[filler_idx % len(keypoints)] if keypoints else (
                _contextual_fallback_point(title_text, index=filler_idx, prefer_zh=prefer_zh)
            )
            fixed.append(
                {
                    "block_type": "body",
                    "card_id": f"body_fill_{filler_idx + 1}",
                    "position": "center",
                    "content": item,
                    "emphasis": [item[:14]],
                }
            )
            non_title_count += 1
            filler_idx += 1

    contract_min_text = 0
    contract_min_visual = 0
    contract_visual_types: List[str] = []
    required_groups: List[List[str]] = []
    if not terminal_slide:
        resolved_template = _resolve_template_family({**out, "blocks": fixed})
        profiles = _template_profiles(resolved_template)
        contract = shared_contract_profile(str(profiles.get("contract_profile") or "default"))
        contract_min_text = max(0, int(contract.get("min_text_blocks") or 0))
        contract_min_visual = max(0, int(contract.get("min_visual_blocks") or 0))
        contract_visual_types = [
            str(item or "").strip().lower()
            for item in (contract.get("visual_anchor_types") or [])
            if str(item or "").strip()
        ]
        required_groups = [
            [str(item or "").strip().lower() for item in group if str(item or "").strip()]
            for group in (contract.get("required_one_of_groups") or [])
            if isinstance(group, list)
        ]
        visual_union = set(contract_visual_types) | {"chart", "kpi", "workflow", "diagram", "image", "table"}

        def _has_any(types: List[str]) -> bool:
            wanted = {str(item or "").strip().lower() for item in types if str(item or "").strip()}
            if not wanted:
                return False
            return any(_as_block_type(block) in wanted for block in fixed)

        for group_idx, group in enumerate(required_groups):
            if not group or _has_any(group):
                continue
            visual_candidates = [item for item in group if item in visual_union]
            if visual_candidates:
                fixed.append(
                    _make_visual_contract_block(
                        preferred_types=visual_candidates,
                        keypoints=keypoints,
                        numeric_values=numeric_values,
                        prefer_zh=prefer_zh,
                        card_id=f"contract_visual_{group_idx + 1}",
                        position="right" if group_idx % 2 == 0 else "center",
                    )
                )
                continue
            body_text = keypoints[group_idx % len(keypoints)] if keypoints else (
                _contextual_fallback_point(title_text, index=group_idx, prefer_zh=prefer_zh)
            )
            fixed.append(
                {
                    "block_type": "body",
                    "card_id": f"contract_text_{group_idx + 1}",
                    "position": "left",
                    "content": body_text,
                    "emphasis": [body_text[:14]],
                }
            )

        ordered_visual_types: List[str] = []
        for item in (contract_visual_types if contract_visual_types else sorted(_VISUAL_BLOCK_TYPES)):
            normalized = str(item or "").strip().lower()
            if not normalized or normalized in ordered_visual_types:
                continue
            ordered_visual_types.append(normalized)
        if require_image_anchor and "image" not in ordered_visual_types:
            ordered_visual_types.insert(0, "image")
        visual_set = set(ordered_visual_types)
        visual_count = len([b for b in fixed if _as_block_type(b) in visual_set])
        while visual_count < contract_min_visual:
            fixed.append(
                _make_visual_contract_block(
                    preferred_types=ordered_visual_types or ["chart"],
                    keypoints=keypoints,
                    numeric_values=numeric_values,
                    prefer_zh=prefer_zh,
                    card_id=f"contract_visual_fill_{visual_count + 1}",
                    position="right",
                )
            )
            visual_count += 1

        text_non_visual_count = len(
            [
                b
                for b in fixed
                if _as_block_type(b) in _TEXTUAL_BLOCK_TYPES
                and _as_block_type(b) != "title"
                and _as_block_type(b) not in visual_set
            ]
        )
        text_fill_idx = 0
        while text_non_visual_count < contract_min_text:
            text_item = keypoints[text_fill_idx % len(keypoints)] if keypoints else (
                _contextual_fallback_point(title_text, index=text_fill_idx, prefer_zh=prefer_zh)
            )
            fixed.append(
                {
                    "block_type": "body",
                    "card_id": f"contract_text_fill_{text_fill_idx + 1}",
                    "position": "left",
                    "content": text_item,
                    "emphasis": [text_item[:14]],
                }
            )
            text_non_visual_count += 1
            text_fill_idx += 1

    # Replace invalid/placeholder KPI blocks with textual bodies to avoid
    # downstream placeholder_kpi_data failures.
    sanitized: List[Dict[str, Any]] = []
    for block in fixed:
        bt = _as_block_type(block)
        if bt != "kpi":
            sanitized.append(block)
            continue
        payload = block.get("data")
        if not isinstance(payload, dict) and isinstance(block.get("content"), dict):
            payload = block.get("content")
        payload = payload if isinstance(payload, dict) else {}
        number_raw = payload.get("number")
        number = _to_float(number_raw, None)
        if number is None or abs(float(number)) < 1e-6:
            sanitized.append(
                _make_visual_contract_block(
                    preferred_types=["chart"],
                    keypoints=keypoints,
                    numeric_values=numeric_values,
                    prefer_zh=prefer_zh,
                    card_id=str(block.get("card_id") or "kpi_rewrite"),
                    position=str(block.get("position") or "right"),
                )
            )
            continue
        sanitized.append(block)
    fixed = sanitized

    fixed = _dedupe_blocks(fixed)
    layout = str(out.get("layout_grid") or out.get("layout") or "").strip().lower()
    layout_capacity = int(_LAYOUT_CARD_COUNTS.get(layout, 0))
    required_non_title = max(0, contract_min_text) + max(0, contract_min_visual)
    if layout_capacity <= 0 or required_non_title <= layout_capacity:
        fixed = _trim_blocks_to_layout_capacity(
            layout,
            fixed,
            min_text_non_visual=contract_min_text,
            min_visual=contract_min_visual,
            visual_types=contract_visual_types,
        )
    fixed = _assign_layout_card_ids(
        layout,
        fixed,
    )
    fixed = [
        block
        for block in fixed
        if _as_block_type(block) == "title"
        or _normalize_text_key(_extract_block_text(block)) != title_key
    ]
    if not terminal_slide:
        filler_idx = 0
        target_text_non_visual = max(2, int(contract_min_text or 0))
        while True:
            fixed = _dedupe_blocks(fixed)
            text_non_title_count = len(
                [
                    b
                    for b in fixed
                    if _as_block_type(b) in _TEXTUAL_BLOCK_TYPES and _as_block_type(b) != "title"
                ]
            )
            if text_non_title_count >= target_text_non_visual:
                break
            item = keypoints[filler_idx % len(keypoints)] if keypoints else (
                _contextual_fallback_point(title_text, index=filler_idx, prefer_zh=prefer_zh)
            )
            item_key = _normalize_text_key(item)
            existing_keys = {
                _normalize_text_key(_extract_block_text(block))
                for block in fixed
                if _as_block_type(block) != "title"
            }
            if not item_key or item_key in existing_keys or item_key == title_key:
                item = _contextual_fallback_point(title_text, index=filler_idx + 3, prefer_zh=prefer_zh)
            fixed.append(
                {
                    "block_type": "body",
                    "card_id": f"body_recover_{filler_idx + 1}",
                    "position": "center",
                    "content": item,
                    "emphasis": [item[:14]],
                }
            )
            filler_idx += 1
            if filler_idx >= 8:
                break
        layout_capacity = int(_LAYOUT_CARD_COUNTS.get(str(out.get("layout_grid") or "").strip().lower(), 0))
        blank_target_non_title = 0
        if layout_capacity > 0:
            blank_target_non_title = max(
                1,
                int(math.ceil(layout_capacity * max(0.0, 1.0 - float(blank_area_max_ratio or 0.45)))),
            )
        target_non_title = max(
            int(min_content_blocks or 2),
            int(contract_min_text or 0) + int(contract_min_visual or 0),
            int(blank_target_non_title or 0),
            2,
        )
        fill_idx = 0
        while len([b for b in fixed if _as_block_type(b) != "title"]) < target_non_title:
            item = keypoints[fill_idx % len(keypoints)] if keypoints else (
                _contextual_fallback_point(title_text, index=fill_idx, prefer_zh=prefer_zh)
            )
            existing_keys = {
                _normalize_text_key(_extract_block_text(block))
                for block in fixed
                if _as_block_type(block) != "title"
            }
            if _normalize_text_key(item) in existing_keys or _normalize_text_key(item) == title_key:
                item = _contextual_fallback_point(title_text, index=fill_idx + 4, prefer_zh=prefer_zh)
            fixed.append(
                {
                    "block_type": "body",
                    "card_id": f"body_density_{fill_idx + 1}",
                    "position": "center",
                    "content": item,
                    "emphasis": [item[:14]],
                }
            )
            fill_idx += 1
            if fill_idx >= 8:
                break
        fixed = _dedupe_blocks(fixed)
    if not terminal_slide and require_image_anchor and not _has_image_block(fixed):
        injected = _make_visual_contract_block(
            preferred_types=["image"],
            keypoints=keypoints,
            numeric_values=numeric_values,
            prefer_zh=prefer_zh,
            card_id="image_guard",
            position="right",
        )
        layout_capacity = int(_LAYOUT_CARD_COUNTS.get(str(out.get("layout_grid") or "").strip().lower(), 0))
        non_title_indexes = [i for i, block in enumerate(fixed) if _as_block_type(block) != "title"]
        text_non_visual_count = len(
            [
                b
                for b in fixed
                if _as_block_type(b) in _TEXTUAL_BLOCK_TYPES
                and _as_block_type(b) != "title"
                and _as_block_type(b) not in set(contract_visual_types or [])
            ]
        )
        chart_kpi_required = any(
            any(item in {"chart", "kpi"} for item in group)
            for group in (required_groups or [])
        )
        # `require_image_anchor` is a soft orchestration hint. If layout
        # capacity is already full and chart/kpi is a hard contract requirement,
        # skip image injection to avoid breaking hard constraints.
        if (
            layout_capacity > 0
            and len(non_title_indexes) >= layout_capacity
            and chart_kpi_required
            and text_non_visual_count <= int(contract_min_text or 0)
        ):
            injected = {}
        if injected and layout_capacity > 0 and len(non_title_indexes) >= layout_capacity:
            # Preserve text density whenever possible: replace a visual block
            # first, and only fall back to replacing text if unavoidable.
            visual_replace_index = next(
                (
                    i
                    for i in non_title_indexes
                    if _as_block_type(fixed[i]) in {"chart", "kpi", "workflow", "diagram", "table"}
                ),
                None,
            )
            replace_index = next(
                (
                    i
                    for i in non_title_indexes
                    if _as_block_type(fixed[i]) in {"chart", "kpi", "workflow", "diagram", "table", "body", "list", "quote", "icon_text"}
                ),
                non_title_indexes[-1] if non_title_indexes else None,
            )
            if visual_replace_index is not None:
                replace_index = visual_replace_index
            if replace_index is not None:
                old = fixed[replace_index]
                if str(old.get("card_id") or "").strip():
                    injected["card_id"] = str(old.get("card_id") or "")
                if str(old.get("position") or "").strip():
                    injected["position"] = str(old.get("position") or "")
                fixed[replace_index] = injected
            else:
                fixed.append(injected)
        elif injected:
            fixed.append(injected)
        fixed = _dedupe_blocks(fixed)
    if not terminal_slide and contract_min_text > 0:
        visual_type_set = {
            str(item or "").strip().lower()
            for item in (contract_visual_types or [])
            if str(item or "").strip()
        }
        if not visual_type_set:
            visual_type_set = set(_VISUAL_BLOCK_TYPES)
        protected_visual_types = {
            item
            for group in (required_groups or [])
            for item in group
            if item in visual_type_set
        }

        def _count_text_non_visual(items: List[Dict[str, Any]]) -> int:
            return len(
                [
                    b
                    for b in items
                    if _as_block_type(b) in _TEXTUAL_BLOCK_TYPES
                    and _as_block_type(b) != "title"
                    and _as_block_type(b) not in visual_type_set
                ]
            )

        def _count_visual(items: List[Dict[str, Any]]) -> int:
            return len([b for b in items if _as_block_type(b) in visual_type_set])

        recover_idx = 0
        while _count_text_non_visual(fixed) < contract_min_text:
            recover_idx += 1
            replace_done = False
            visual_floor = max(int(contract_min_visual or 0), 1 if require_image_anchor else 0)
            visual_count = _count_visual(fixed)
            if visual_count > visual_floor:
                for i, block in enumerate(fixed):
                    btype = _as_block_type(block)
                    if btype not in visual_type_set or btype == "image":
                        continue
                    if btype in protected_visual_types:
                        continue
                    replacement_text = _extract_block_text(block) or (
                        keypoints[(recover_idx - 1) % len(keypoints)] if keypoints else (
                            _contextual_fallback_point(
                                title_text,
                                index=recover_idx + 2,
                                prefer_zh=prefer_zh,
                            )
                        )
                    )
                    if _normalize_text_key(replacement_text) == title_key:
                        replacement_text = _contextual_fallback_point(
                            title_text,
                            index=recover_idx + 3,
                            prefer_zh=prefer_zh,
                        )
                    fixed[i] = {
                        "block_type": "body",
                        "card_id": str(block.get("card_id") or f"contract_text_recover_{recover_idx}"),
                        "position": str(block.get("position") or "left"),
                        "content": replacement_text,
                        "emphasis": [replacement_text[:14]],
                    }
                    replace_done = True
                    break

            if not replace_done:
                fill_text = keypoints[(recover_idx - 1) % len(keypoints)] if keypoints else (
                    _contextual_fallback_point(title_text, index=recover_idx + 4, prefer_zh=prefer_zh)
                )
                if _normalize_text_key(fill_text) == title_key:
                    fill_text = _contextual_fallback_point(
                        title_text,
                        index=recover_idx + 5,
                        prefer_zh=prefer_zh,
                    )
                fixed.append(
                    {
                        "block_type": "body",
                        "card_id": f"contract_text_recover_{recover_idx}",
                        "position": "left",
                        "content": fill_text,
                        "emphasis": [fill_text[:14]],
                    }
                )

            fixed = _dedupe_blocks(fixed)
            if recover_idx >= 12:
                break
    for idx, block in enumerate(fixed):
        block["block_type"] = _as_block_type(block) or "text"
        if not str(block.get("card_id") or "").strip():
            block["card_id"] = f"card-{idx + 1}"
        if block["block_type"] != "title":
            block["emphasis"] = _auto_emphasis(block, keypoints)

    out["blocks"] = fixed
    out["template_family"] = _resolve_template_family(out)
    out.update(_template_profiles(out["template_family"]))
    out["bg_style"] = (
        "light"
        if out["template_family"] in {"neural_blueprint_light", "ops_lifecycle_light", "consulting_warm_light"}
        else "dark"
    )
    out["svg_mode"] = "on"
    out["enforce_visual_contract"] = True
    return out


def _apply_visual_orchestration(render_payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(render_payload or {})
    slides = out.get("slides")
    if not isinstance(slides, list):
        return out
    quality_id = str(out.get("quality_profile") or "default").strip().lower() or "default"
    quality_cfg = shared_quality_profile(quality_id)
    min_content_blocks = max(1, int(quality_cfg.get("min_content_blocks") or 2))
    orchestration_cfg = (
        quality_cfg.get("orchestration")
        if isinstance(quality_cfg.get("orchestration"), dict)
        else {}
    )
    dense_cfg = orchestration_cfg.get("dense_layout_remap") if isinstance(orchestration_cfg.get("dense_layout_remap"), dict) else {}
    dense_layout_enabled = bool(dense_cfg.get("enabled", min_content_blocks >= 3))
    dense_replace_from = {
        str(item or "").strip().lower()
        for item in (dense_cfg.get("replace_from") or ["split_2", "asymmetric_2"])
        if str(item or "").strip()
    }
    dense_cycle = [
        str(item or "").strip().lower()
        for item in (dense_cfg.get("cycle") or ["grid_3", "grid_4", "bento_5", "timeline", "bento_6"])
        if str(item or "").strip()
    ] or ["grid_3", "grid_4", "bento_5", "timeline", "bento_6"]
    prevent_adjacent_layout_repeat = bool(orchestration_cfg.get("prevent_adjacent_layout_repeat", True))
    family_cfg = (
        orchestration_cfg.get("family_convergence")
        if isinstance(orchestration_cfg.get("family_convergence"), dict)
        else {}
    )
    family_convergence_enabled = bool(family_cfg.get("enabled", False))
    family_auto_only = bool(family_cfg.get("only_when_deck_template_auto", True))
    family_default = str(family_cfg.get("default_family") or "dashboard_dark").strip().lower() or "dashboard_dark"
    family_lock_after = bool(family_cfg.get("lock_after_apply", True))
    family_skip_types = {
        str(item or "").strip().lower()
        for item in (family_cfg.get("skip_slide_types") or ["cover", "summary", "toc", "divider", "hero_1"])
        if str(item or "").strip()
    }
    raw_family_map = family_cfg.get("layout_to_family") if isinstance(family_cfg.get("layout_to_family"), dict) else {}
    family_by_layout = {
        str(key or "").strip().lower(): str(value or "").strip().lower()
        for key, value in raw_family_map.items()
        if str(key or "").strip() and str(value or "").strip()
    }
    require_image_anchor = bool(orchestration_cfg.get("require_image_anchor", min_content_blocks >= 3))
    total_seed_pages = len(slides)
    normalized_seed: List[Dict[str, Any]] = []
    for idx, raw in enumerate(slides):
        slide = dict(raw if isinstance(raw, dict) else {})
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if not slide_type:
            if idx == 0:
                slide_type = "cover"
            elif idx == total_seed_pages - 1:
                slide_type = "summary"
            else:
                slide_type = "content"
        slide["slide_type"] = slide_type
        layout_grid = str(slide.get("layout_grid") or slide.get("layout") or "").strip().lower()
        if not layout_grid:
            layout_grid = "hero_1" if slide_type in {"cover", "summary", "toc", "divider"} else "split_2"
        slide["layout_grid"] = layout_grid
        normalized_seed.append(slide)

    out["slides"] = [
        _ensure_content_contract(
            slide,
            min_content_blocks=min_content_blocks,
            blank_area_max_ratio=float(quality_cfg.get("blank_area_max_ratio") or 0.45),
            require_image_anchor=require_image_anchor,
        )
        for slide in normalized_seed
    ]
    original_slide_count = len(out["slides"])
    out["slides"] = paginate_content_overflow(
        out["slides"],
        max_bullets_per_slide=int(quality_cfg.get("pagination_max_bullets_per_slide") or 6),
        max_chars_per_slide=int(quality_cfg.get("pagination_max_chars_per_slide") or 360),
        max_continuation_pages=int(quality_cfg.get("pagination_max_continuation_pages") or 3),
    )
    if len(out["slides"]) > original_slide_count:
        out["pagination"] = {
            "expanded": True,
            "source_slide_count": original_slide_count,
            "expanded_slide_count": len(out["slides"]),
        }
    total_pages = len(out["slides"])
    for idx, slide in enumerate(out["slides"]):
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if not slide_type:
            if idx == 0:
                slide_type = "cover"
            elif idx == total_pages - 1:
                slide_type = "summary"
            else:
                slide_type = "content"
            slide["slide_type"] = slide_type
        layout_grid = str(slide.get("layout_grid") or slide.get("layout") or "").strip().lower()
        if not layout_grid:
            slide["layout_grid"] = "hero_1" if slide_type in {"cover", "summary", "toc", "divider"} else "split_2"
        else:
            slide["layout_grid"] = layout_grid

    # Config-driven dense remap: for strict profiles, upgrade narrow layouts to
    # denser grids before diversity balancing.
    if dense_layout_enabled:
        dense_idx = 0
        for slide in out["slides"]:
            if not isinstance(slide, dict):
                continue
            slide_type = str(slide.get("slide_type") or "").strip().lower()
            if slide_type in family_skip_types:
                continue
            layout_grid = str(slide.get("layout_grid") or "").strip().lower()
            if layout_grid in dense_replace_from:
                slide["layout_grid"] = dense_cycle[dense_idx % len(dense_cycle)]
                dense_idx += 1

    layout_sequence = [
        str((slide or {}).get("layout_grid") or "split_2").strip().lower()
        if isinstance(slide, dict)
        else "split_2"
        for slide in out["slides"]
    ]
    diversified_layouts = enforce_layout_diversity(
        layout_sequence,
        max_type_ratio=float(quality_cfg.get("layout_max_type_ratio") or 0.45),
        max_top2_ratio=float(quality_cfg.get("layout_max_top2_ratio") or 0.65),
        abab_max_run=int(quality_cfg.get("layout_abab_max_run") or 4),
        min_layout_variety_for_long=int(quality_cfg.get("layout_min_variety_long_deck") or 4),
    )
    diversified_layouts = enforce_density_rhythm(
        diversified_layouts,
        max_consecutive_high=int(quality_cfg.get("density_max_consecutive_high") or 2),
        window_size=int(quality_cfg.get("density_window_size") or 5),
        require_low_or_breathing_per_window=int(
            quality_cfg.get("density_require_low_or_breathing_per_window") or 1
        ),
    )
    for idx, layout in enumerate(diversified_layouts):
        if idx >= len(out["slides"]):
            break
        slide = out["slides"][idx]
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type in {"cover", "summary", "toc", "divider"}:
            slide["layout_grid"] = "hero_1"
            continue
        slide["layout_grid"] = str(layout or "split_2").strip().lower() or "split_2"

    if dense_layout_enabled:
        dense_idx = 0
        for slide in out["slides"]:
            if not isinstance(slide, dict):
                continue
            slide_type = str(slide.get("slide_type") or "").strip().lower()
            if slide_type in family_skip_types:
                continue
            layout_grid = str(slide.get("layout_grid") or "").strip().lower()
            if layout_grid in dense_replace_from:
                slide["layout_grid"] = dense_cycle[dense_idx % len(dense_cycle)]
                dense_idx += 1

    # Deterministic adjacency guard from orchestration policy.
    if prevent_adjacent_layout_repeat:
        layout_cycle = list(dense_cycle)
        for idx in range(1, len(out["slides"])):
            current = out["slides"][idx]
            previous = out["slides"][idx - 1]
            if not isinstance(current, dict) or not isinstance(previous, dict):
                continue
            current_type = str(current.get("slide_type") or "").strip().lower()
            previous_type = str(previous.get("slide_type") or "").strip().lower()
            if current_type in family_skip_types:
                continue
            if previous_type in family_skip_types:
                continue
            current_layout = str(current.get("layout_grid") or "").strip().lower()
            previous_layout = str(previous.get("layout_grid") or "").strip().lower()
            if not current_layout or current_layout != previous_layout:
                continue
            next_layout = ""
            if idx + 1 < len(out["slides"]) and isinstance(out["slides"][idx + 1], dict):
                next_layout = str((out["slides"][idx + 1] or {}).get("layout_grid") or "").strip().lower()
            for candidate in layout_cycle:
                if candidate != previous_layout and candidate != next_layout:
                    current["layout_grid"] = candidate
                    break

    # Pagination may create continuation slides with only one textual block
    # (e.g., title + list). Re-apply the contract fixer to keep downstream
    # render-contract constraints (min_text_blocks, emphasis) satisfied.
    out["slides"] = [
        _ensure_content_contract(
            slide if isinstance(slide, dict) else {},
            min_content_blocks=min_content_blocks,
            blank_area_max_ratio=float(quality_cfg.get("blank_area_max_ratio") or 0.45),
            require_image_anchor=require_image_anchor,
        )
        for slide in out["slides"]
    ]
    blank_limit = float(quality_cfg.get("blank_area_max_ratio") or 0.45)
    for idx, slide in enumerate(out["slides"]):
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type in {"cover", "summary", "toc", "divider", "hero_1"}:
            continue
        layout_grid = str(slide.get("layout_grid") or "").strip().lower()
        card_count = int(_LAYOUT_CARD_COUNTS.get(layout_grid, 0))
        if card_count <= 0:
            continue
        target_non_title = max(1, int(math.ceil(card_count * max(0.0, 1.0 - blank_limit))))
        blocks = slide.get("blocks")
        if not isinstance(blocks, list):
            blocks = []
        fixed_blocks = [dict(block) for block in blocks if isinstance(block, dict)]
        fill_idx = 0
        while len([b for b in fixed_blocks if _as_block_type(b) != "title"]) < target_non_title:
            existing_keys = {
                _normalize_text_key(_extract_block_text(block))
                for block in fixed_blocks
                if _as_block_type(block) != "title"
            }
            candidate_no = fill_idx + 1
            slide_title = str(slide.get("title") or "本页主题")
            fill_text = _contextual_fallback_point(
                slide_title,
                index=candidate_no,
                prefer_zh=_prefer_zh(slide_title, slide.get("narration"), slide.get("speaker_notes")),
            )
            while _normalize_text_key(fill_text) in existing_keys:
                candidate_no += 1
                fill_text = _contextual_fallback_point(
                    slide_title,
                    index=candidate_no,
                    prefer_zh=_prefer_zh(slide_title, slide.get("narration"), slide.get("speaker_notes")),
                )
            fixed_blocks.append(
                {
                    "block_type": "body",
                    "card_id": f"blank_fill_{idx + 1}_{candidate_no}",
                    "position": "center",
                    "content": fill_text,
                    "emphasis": [fill_text],
                }
            )
            fill_idx = candidate_no
            if fill_idx >= 8:
                break
        slide["blocks"] = _assign_layout_card_ids(layout_grid, _dedupe_blocks(fixed_blocks))
    family_sequence: List[str] = []
    family_locked_mask: List[bool] = []
    for slide in out["slides"]:
        family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
        if not family:
            family = _resolve_template_family(slide)
        family_sequence.append(family)
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        implicit_lock = slide_type in {"cover", "summary", "hero_1"}
        family_locked_mask.append(bool(slide.get("template_lock")) or implicit_lock)
    cohesive_families = enforce_template_family_cohesion(
        family_sequence,
        locked_mask=family_locked_mask,
        max_type_ratio=float(quality_cfg.get("template_family_max_type_ratio") or 0.55),
        max_top2_ratio=float(quality_cfg.get("template_family_max_top2_ratio") or 0.8),
        max_switch_ratio=float(quality_cfg.get("template_family_max_switch_ratio") or 0.75),
        abab_max_run=int(quality_cfg.get("template_family_abab_max_run") or 6),
    )
    for idx, family in enumerate(cohesive_families):
        if idx >= len(out["slides"]):
            break
        slide = out["slides"][idx]
        if not isinstance(slide, dict):
            continue
        normalized = str(family or "").strip().lower()
        if not normalized:
            continue
        slide["template_family"] = normalized
        slide.update(_template_profiles(normalized))
        slide["bg_style"] = (
            "light"
            if normalized in {"neural_blueprint_light", "ops_lifecycle_light", "consulting_warm_light"}
            else "dark"
        )
    deck_template_mode = str(out.get("template_family") or "").strip().lower()
    should_apply_family_convergence = family_convergence_enabled and (
        (not family_auto_only) or deck_template_mode in {"", "auto"}
    )
    if should_apply_family_convergence and family_by_layout:
        for slide in out["slides"]:
            if not isinstance(slide, dict):
                continue
            slide_type = str(slide.get("slide_type") or "").strip().lower()
            if slide_type in family_skip_types:
                continue
            if bool(slide.get("template_lock")):
                # Respect explicitly locked families from upstream inputs.
                continue
            layout_grid = str(slide.get("layout_grid") or "").strip().lower() or "split_2"
            target_family = family_by_layout.get(layout_grid, family_default)
            if not target_family:
                continue
            current_family = str(slide.get("template_family") or "").strip().lower()
            if current_family == target_family:
                continue
            slide["template_family"] = target_family
            slide.update(_template_profiles(target_family))
            slide["bg_style"] = (
                "light"
                if target_family in {"neural_blueprint_light", "ops_lifecycle_light", "consulting_warm_light"}
                else "dark"
            )

    # Re-smooth family sequence after layout-based convergence to satisfy
    # template-family switch constraints under strict quality profiles.
    family_sequence = []
    family_locked_mask = []
    for slide in out["slides"]:
        if not isinstance(slide, dict):
            continue
        family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
        if not family:
            family = _resolve_template_family(slide)
        family_sequence.append(family)
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        implicit_lock = slide_type in {"cover", "summary", "hero_1"}
        family_locked_mask.append(bool(slide.get("template_lock")) or implicit_lock)

    cohesive_families = enforce_template_family_cohesion(
        family_sequence,
        locked_mask=family_locked_mask,
        max_type_ratio=float(quality_cfg.get("template_family_max_type_ratio") or 0.55),
        max_top2_ratio=float(quality_cfg.get("template_family_max_top2_ratio") or 0.8),
        max_switch_ratio=float(quality_cfg.get("template_family_max_switch_ratio") or 0.75),
        abab_max_run=int(quality_cfg.get("template_family_abab_max_run") or 6),
    )
    for idx, family in enumerate(cohesive_families):
        if idx >= len(out["slides"]):
            break
        slide = out["slides"][idx]
        if not isinstance(slide, dict):
            continue
        normalized = str(family or "").strip().lower()
        if not normalized:
            continue
        slide["template_family"] = normalized
        slide.update(_template_profiles(normalized))
        slide["bg_style"] = (
            "light"
            if normalized in {"neural_blueprint_light", "ops_lifecycle_light", "consulting_warm_light"}
            else "dark"
        )

    # Keep per-slide family/profile stable across Node-side normalization.
    for slide in out["slides"]:
        if not isinstance(slide, dict):
            continue
        slide["template_lock"] = True if family_lock_after else bool(slide.get("template_lock"))

    svg_mode = str(out.get("svg_mode") or "on").strip().lower()
    if svg_mode not in {"on", "off"}:
        svg_mode = "on"
    out["svg_mode"] = svg_mode
    out["slides"] = apply_render_paths(
        [slide for slide in out.get("slides") or [] if isinstance(slide, dict)],
        svg_mode=svg_mode,
    )
    theme_obj = out.get("theme") if isinstance(out.get("theme"), dict) else {}
    out["design_spec"] = build_design_spec(
        theme=theme_obj,
        template_family=str(out.get("template_family") or ""),
        style_variant=str(theme_obj.get("style") or out.get("minimax_style_variant") or "soft"),
        visual_preset=str(out.get("visual_preset") or "auto"),
        visual_density=str(out.get("visual_density") or "balanced"),
        visual_priority=bool(out.get("visual_priority", True)),
        topic=str(out.get("title") or ""),
    )
    out["enforce_visual_contract"] = True
    if not str(out.get("template_family") or "").strip():
        out["template_family"] = "auto"
    deck_template = str(out.get("template_family") or "dashboard_dark").strip().lower()
    if deck_template == "auto":
        first = out["slides"][0] if out["slides"] else {}
        deck_template = str(first.get("template_family") or "dashboard_dark").strip().lower()
    resolved_profiles = _template_profiles(deck_template)
    for key, value in resolved_profiles.items():
        existing = str(out.get(key) or "").strip()
        if existing and existing.lower() != "auto":
            out[key] = existing
        else:
            out[key] = value
    theme = out.get("theme")
    if isinstance(theme, dict):
        if not str(theme.get("style") or "").strip() or str(theme.get("style")).strip().lower() == "auto":
            theme["style"] = "pill"
        out["theme"] = theme
    return out


_SCHEMA_SLIDE_RE = re.compile(r"slides\[(\d+)\]", flags=re.IGNORECASE)


def _extract_slide_targets_from_schema_error(detail: str, slides: List[Dict[str, Any]]) -> List[str]:
    indexes = sorted({int(m.group(1)) for m in _SCHEMA_SLIDE_RE.finditer(str(detail or ""))})
    targets: List[str] = []
    for idx in indexes:
        if idx < 0 or idx >= len(slides):
            continue
        slide = slides[idx] if isinstance(slides[idx], dict) else {}
        candidate = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}").strip()
        if candidate and candidate not in targets:
            targets.append(candidate)
    return targets


def _search_serper_sync(
    *,
    query: str,
    api_key: str,
    num: int = 5,
    gl: str = "us",
    hl: str = "zh-cn",
) -> List[Dict[str, str]]:
    base_url = str(_env_value("SERPER_API_URL", "https://google.serper.dev/search")).strip()
    payload = json.dumps(
        {
            "q": query,
            "num": max(1, min(10, int(num))),
            "gl": gl,
            "hl": hl,
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        base_url,
        data=payload,
        method="POST",
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=12) as resp:  # nosec B310
            raw = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, json.JSONDecodeError):
        return []

    organic = parsed.get("organic") if isinstance(parsed, dict) else []
    if not isinstance(organic, list):
        return []

    items: List[Dict[str, str]] = []
    for row in organic:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        url = str(row.get("link") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        if not title or not url:
            continue
        items.append({"title": title, "url": url, "snippet": snippet})
        if len(items) >= max(3, min(10, int(num))):
            break
    return items


async def _search_serper_web(
    *,
    query: str,
    api_key: str,
    num: int = 5,
    gl: str = "us",
    hl: str = "zh-cn",
) -> List[Dict[str, str]]:
    import asyncio

    return await asyncio.to_thread(
        _search_serper_sync,
        query=query,
        api_key=api_key,
        num=num,
        gl=gl,
        hl=hl,
    )


_GENERIC_AUDIENCE = {"general", "all", "public", "everyone", "大众", "通用", "全部人群"}
_GENERIC_PURPOSE = {"presentation", "general", "汇报", "演示", "展示"}
_GENERIC_STYLE = {"professional", "default", "normal", "商务", "专业", "常规"}


def _is_generic_slot(value: str, generic: set[str]) -> bool:
    text = str(value or "").strip().lower()
    return not text or text in generic


def _dedup_strings(items: List[str], *, limit: int) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _build_research_gaps(req: ResearchRequest, *, is_zh: bool) -> List[ResearchGap]:
    gaps: List[ResearchGap] = []
    if _is_generic_slot(req.audience, _GENERIC_AUDIENCE):
        gaps.append(
            ResearchGap(
                code="audience",
                severity="high",
                message="受众描述过于泛化，缺少明确角色与决策层级。"
                if is_zh
                else "Audience definition is too generic; role and decision level are missing.",
                query_hint=f"{req.topic} 目标受众 分层" if is_zh else f"{req.topic} target audience segmentation",
            )
        )
    if _is_generic_slot(req.purpose, _GENERIC_PURPOSE):
        gaps.append(
            ResearchGap(
                code="purpose",
                severity="medium",
                message="演示目标不够明确，难以确定叙事重点。"
                if is_zh
                else "Presentation objective is not specific enough for clear narrative focus.",
                query_hint=f"{req.topic} 商业目标 KPI" if is_zh else f"{req.topic} business objective KPI",
            )
        )
    if _is_generic_slot(req.style_preference, _GENERIC_STYLE):
        gaps.append(
            ResearchGap(
                code="style",
                severity="low",
                message="视觉风格偏好不明确，建议补充调性或品牌约束。"
                if is_zh
                else "Visual style preference is vague; add tone or brand constraints.",
                query_hint=f"{req.topic} 品牌视觉 风格" if is_zh else f"{req.topic} brand visual style",
            )
        )
    if not req.required_facts:
        gaps.append(
            ResearchGap(
                code="required_facts",
                severity="high",
                message="缺少必须展示的数据点，图表选型依据不足。"
                if is_zh
                else "Missing must-have facts, limiting chart and evidence selection.",
                query_hint=f"{req.topic} 核心指标 数据" if is_zh else f"{req.topic} core metrics data",
            )
        )
    if not str(req.time_range or "").strip():
        gaps.append(
            ResearchGap(
                code="time_range",
                severity="medium",
                message="缺少时间范围，趋势数据无法限定口径。"
                if is_zh
                else "Time range is missing, making trend framing ambiguous.",
                query_hint=f"{req.topic} 近3年 趋势" if is_zh else f"{req.topic} last 3 years trend",
            )
        )
    if not str(req.geography or "").strip():
        gaps.append(
            ResearchGap(
                code="geography",
                severity="low",
                message="缺少地域范围，市场数据可能口径不一致。"
                if is_zh
                else "Geographic scope is missing; market figures may be inconsistent.",
                query_hint=f"{req.topic} 中国 市场" if is_zh else f"{req.topic} regional market",
            )
        )
    return gaps


def _build_research_queries(
    req: ResearchRequest,
    *,
    is_zh: bool,
    gaps: List[ResearchGap],
) -> List[str]:
    extras = " ".join(
        part
        for part in [
            str(req.time_range or "").strip(),
            str(req.geography or "").strip(),
            " ".join(req.domain_terms[:2]),
        ]
        if part
    ).strip()

    queries: List[str] = []
    if req.required_facts:
        for fact in req.required_facts:
            q = " ".join(part for part in [req.topic, fact, extras] if part).strip()
            if q:
                queries.append(q)
    for gap in gaps:
        if gap.query_hint:
            q = " ".join(part for part in [req.topic, gap.query_hint, extras] if part).strip()
            queries.append(q)

    if not queries:
        default_queries = (
            [
                f"{req.topic} 市场规模 增长",
                f"{req.topic} 行业报告 数据",
                f"{req.topic} 最新统计 指标",
            ]
            if is_zh
            else [
                f"{req.topic} market size trend",
                f"{req.topic} benchmark report data",
                f"{req.topic} latest statistics metrics",
            ]
        )
        queries.extend(default_queries)

    return _dedup_strings(queries, limit=max(1, req.max_web_queries))


def _score_evidence_confidence(url: str, snippet: str) -> float:
    host = str(urlparse(url).netloc or "").lower()
    score = 0.58
    if host.endswith(".gov") or host.endswith(".edu"):
        score = 0.84
    elif any(token in host for token in ("research", "report", "data", "stat")):
        score = 0.74
    if len(str(snippet or "").strip()) >= 120:
        score += 0.08
    elif len(str(snippet or "").strip()) >= 60:
        score += 0.04
    return max(0.35, min(0.93, round(score, 2)))


def _score_research_completeness(
    req: ResearchRequest,
    *,
    key_data_points: int,
    references: int,
    evidence_count: int,
    gaps: List[ResearchGap],
) -> float:
    score = 0.28  # topic is required
    score += 0.12 if not _is_generic_slot(req.audience, _GENERIC_AUDIENCE) else 0.04
    score += 0.10 if not _is_generic_slot(req.purpose, _GENERIC_PURPOSE) else 0.03
    score += 0.05 if not _is_generic_slot(req.style_preference, _GENERIC_STYLE) else 0.02
    score += 0.12 if req.required_facts else 0.03
    if str(req.time_range or "").strip():
        score += 0.06
    if str(req.geography or "").strip():
        score += 0.04
    if req.constraints:
        score += 0.05
    score += min(0.10, (key_data_points / 8.0) * 0.10)
    score += min(0.08, (references / max(1, req.desired_citations)) * 0.08)
    score += min(0.05, (evidence_count / 6.0) * 0.05)

    high_gaps = sum(1 for gap in gaps if gap.severity == "high")
    medium_gaps = sum(1 for gap in gaps if gap.severity == "medium")
    score -= min(0.09, high_gaps * 0.03 + medium_gaps * 0.015)
    return max(0.0, min(1.0, round(score, 3)))


def _search_serper_images_sync(
    *,
    query: str,
    api_key: str,
    num: int = 5,
    gl: str = "us",
    hl: str = "zh-cn",
) -> List[Dict[str, str]]:
    base_url = str(_env_value("SERPER_IMAGE_API_URL", "https://google.serper.dev/images")).strip()
    payload = json.dumps(
        {
            "q": query,
            "num": max(1, min(10, int(num))),
            "gl": gl,
            "hl": hl,
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        base_url,
        data=payload,
        method="POST",
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=12) as resp:  # nosec B310
            raw = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, json.JSONDecodeError):
        return []

    rows = parsed.get("images") if isinstance(parsed, dict) else []
    if not isinstance(rows, list):
        return []

    out: List[Dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        image_url = str(row.get("imageUrl") or row.get("url") or "").strip()
        title = str(row.get("title") or "").strip()
        source = str(row.get("source") or row.get("link") or "").strip()
        if not image_url.startswith(("http://", "https://")):
            continue
        out.append(
            {
                "title": title,
                "url": image_url,
                "source": source,
            }
        )
        if len(out) >= max(3, min(10, int(num))):
            break
    return out


async def _search_serper_images(
    *,
    query: str,
    api_key: str,
    num: int = 5,
    gl: str = "us",
    hl: str = "zh-cn",
) -> List[Dict[str, str]]:
    import asyncio

    try:
        return await asyncio.to_thread(
            _search_serper_images_sync,
            query=query,
            api_key=api_key,
            num=num,
            gl=gl,
            hl=hl,
        )
    except Exception:
        return []


def _fetch_image_data_uri_sync(url: str, max_bytes: int = 3_000_000) -> str:
    raw_url = str(url or "").strip()
    if not raw_url.startswith(("http://", "https://")):
        return ""

    req = urllib_request.Request(
        raw_url,
        method="GET",
        headers={
            "User-Agent": "Mozilla/5.0 (PPTAssetBot/1.0)",
            "Accept": "image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=12) as resp:  # nosec B310
            content_type = str(resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            payload = resp.read(max_bytes + 1)
    except Exception:
        return ""

    if not payload or len(payload) > max_bytes:
        return ""
    if not content_type.startswith("image/"):
        guessed = mimetypes.guess_type(raw_url)[0] or ""
        content_type = guessed.lower()
    if not content_type.startswith("image/"):
        return ""

    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


async def _fetch_image_data_uri(url: str, max_bytes: int = 3_000_000) -> str:
    import asyncio

    return await asyncio.to_thread(_fetch_image_data_uri_sync, url, max_bytes)


def _is_placeholder_image_url(url: str) -> bool:
    s = str(url or "").strip().lower()
    if not s:
        return True
    return "brand%20visual%20placeholder" in s or "brand visual placeholder" in s


_DEFAULT_STOCK_IMAGE_DOMAIN_HINTS = (
    "unsplash.com",
    "images.unsplash.com",
    "pexels.com",
    "images.pexels.com",
    "pixabay.com",
    "cdn.pixabay.com",
    "freepik.com",
    "i.ibb.co",
)


def _stock_image_domain_hints() -> List[str]:
    hints = {h.lower() for h in _DEFAULT_STOCK_IMAGE_DOMAIN_HINTS}
    extra = str(_env_value("PPT_STOCK_IMAGE_DOMAINS", "")).strip()
    if extra:
        hints.update(part.strip().lower() for part in extra.split(",") if part.strip())
    return sorted(hints)


def _is_stock_image_candidate(item: Dict[str, str], stock_domain_hints: List[str]) -> bool:
    if not isinstance(item, dict):
        return False
    url_candidates = [
        str(item.get("url") or "").strip().lower(),
        str(item.get("source") or "").strip().lower(),
    ]
    title = str(item.get("title") or "").strip().lower()
    hosts = []
    for candidate in url_candidates:
        if not candidate:
            continue
        try:
            parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        except ValueError:
            continue
        host = str(parsed.netloc or "").strip().lower()
        if host:
            hosts.append(host)
    for host in hosts:
        if any(hint in host for hint in stock_domain_hints):
            return True
    blob = " ".join([*url_candidates, title])
    return any(hint in blob for hint in stock_domain_hints)


def _dedupe_image_candidates(candidates: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        key = _canonical_image_url_key(url)
        if not url or not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _canonical_image_url_key(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw.lower()
    host = str(parsed.netloc or "").strip().lower()
    path = str(parsed.path or "").strip().lower()
    if not host and not path:
        return raw.lower()
    return f"{host}{path}"


def _tokenize_semantic_terms(text: str) -> List[str]:
    raw = str(text or "").strip().lower()
    if not raw:
        return []
    parts = re.split(r"[^\w\u4e00-\u9fff]+", raw)
    out: List[str] = []
    for part in parts:
        token = str(part or "").strip()
        if len(token) < 2:
            continue
        if token in out:
            continue
        out.append(token)
        if len(out) >= 40:
            break
    return out


def _infer_image_context(
    *,
    deck_title: str,
    slide_title: str,
    slide_narration: str,
    block_title: str,
) -> Dict[str, Any]:
    blob = " ".join(
        item
        for item in [deck_title, slide_title, slide_narration, block_title]
        if str(item or "").strip()
    ).lower()
    positive: List[str] = []
    negative: List[str] = []
    industrial_tokens = [
        "数控",
        "机床",
        "加工",
        "制造",
        "工业",
        "factory",
        "manufacturing",
        "machine",
        "machining",
        "cnc",
        "aerospace",
        "automotive",
        "tooling",
    ]
    for token in industrial_tokens:
        if token in blob and token not in positive:
            positive.append(token)
    if positive:
        negative.extend(
            [
                "portrait",
                "woman",
                "girl",
                "people",
                "fashion",
                "wedding",
                "beauty",
                "selfie",
                "model",
            ]
        )
    if ("案例" in blob or "case" in blob or "客户" in blob or "application" in blob) and "factory" not in positive:
        positive.extend(["factory", "production", "workshop", "equipment"])
    return {"positive": positive[:12], "negative": negative[:12], "industrial": bool(positive)}


def _score_image_candidate(
    item: Dict[str, str],
    *,
    keyword: str,
    stock_domain_hints: List[str],
    semantic_tokens: List[str],
    positive_hints: List[str],
    negative_hints: List[str],
) -> float:
    text_blob = " ".join(
        [
            str(item.get("title") or "").lower(),
            str(item.get("source") or "").lower(),
            str(item.get("url") or "").lower(),
            keyword.lower(),
        ]
    )
    score = 0.0
    if _is_stock_image_candidate(item, stock_domain_hints):
        score += 0.25
    if text_blob.startswith("https://images.unsplash.com"):
        score += 0.05

    token_hits = 0
    for token in semantic_tokens[:24]:
        if token and token in text_blob:
            token_hits += 1
    score += min(0.45, token_hits * 0.04)

    for token in positive_hints:
        if token and token in text_blob:
            score += 0.15
    for token in negative_hints:
        if token and token in text_blob:
            score -= 0.4
    return score


def _extract_image_keywords(slide: Dict[str, Any], block: Dict[str, Any], deck_title: str) -> List[str]:
    raw_terms: List[str] = []
    data = block.get("data")
    if isinstance(data, dict):
        kws = data.get("keywords")
        if isinstance(kws, list):
            raw_terms.extend(str(item or "").strip() for item in kws)
        for key in ("intent", "semantic_intent", "subject", "scene"):
            value = str(data.get(key) or "").strip()
            if value:
                raw_terms.append(value)
    image_keywords = slide.get("image_keywords")
    if isinstance(image_keywords, list):
        raw_terms.extend(str(item or "").strip() for item in image_keywords)

    content = block.get("content")
    if isinstance(content, dict):
        for key in ("title", "caption", "description", "text", "label"):
            value = str(content.get(key) or "").strip()
            if value:
                raw_terms.append(value)
    else:
        raw_terms.append(str(content or "").strip())

    raw_terms.extend(
        [
            str(deck_title or "").strip(),
            str(slide.get("title") or "").strip(),
            str(slide.get("narration") or slide.get("speaker_notes") or "").strip(),
        ]
    )

    semantic_rewrites = {
        "workflow-screen": "software workflow dashboard interface screenshot",
        "case-board": "business strategy case board meeting collaboration",
        "comparison-screen": "before after analytics comparison dashboard",
        "dashboard": "business analytics dashboard ui",
        "architecture": "cloud architecture diagram illustration",
        "blueprint": "technology blueprint system diagram",
        "llmops": "ai operations monitoring platform interface",
        "diagram": "clean vector process diagram",
    }

    split_re = re.compile(r"[;；,\n\r，。.!?、|]+")
    expanded: List[str] = []
    for item in raw_terms:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        expanded.append(text)
        for key, rewritten in semantic_rewrites.items():
            if key in lowered:
                expanded.append(rewritten)
        if "-" in text and len(text) <= 40:
            expanded.append(text.replace("-", " "))
        for part in split_re.split(text):
            part = part.strip()
            if len(part) >= 4:
                expanded.append(part)

    dedup: List[str] = []
    seen = set()
    for item in expanded:
        normalized = re.sub(r"\s+", " ", str(item or "").strip())
        if len(normalized) < 4:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(normalized)
        if len(dedup) >= 12:
            break
    return dedup


def _dedupe_terms(items: List[str], *, limit: int = 8) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in items:
        text = re.sub(r"\s+", " ", str(raw or "").strip())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _ensure_image_block_placeholders(render_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure image blocks always have a renderable URL fallback."""
    out = dict(render_payload or {})
    slides = out.get("slides")
    if not isinstance(slides, list) or not slides:
        return out

    deck_title = str(out.get("title") or "").strip()
    for slide_idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        blocks = slide.get("blocks")
        if not isinstance(blocks, list):
            continue
        slide_title = str(slide.get("title") or "").strip() or deck_title
        for block_idx, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            if str(block.get("block_type") or block.get("type") or "").strip().lower() != "image":
                continue

            content = block.get("content")
            content_obj = dict(content) if isinstance(content, dict) else {"title": str(content or slide_title or "Visual")}
            data = block.get("data")
            data_obj = dict(data) if isinstance(data, dict) else {}

            existing_url = ""
            for key in ("url", "src", "imageUrl", "image_url"):
                existing_url = str(content_obj.get(key) or data_obj.get(key) or block.get(key) or "").strip()
                if existing_url:
                    break
            if existing_url:
                continue

            label = str(content_obj.get("title") or slide_title or deck_title or f"Visual {slide_idx + 1}-{block_idx + 1}").strip()
            content_obj["url"] = _brand_placeholder_svg_data_uri(label[:48] or "Brand Visual")
            data_obj.setdefault("source_type", "placeholder")
            block["content"] = content_obj
            if data_obj:
                block["data"] = data_obj

    out["slides"] = slides
    return out


async def _hydrate_image_assets(render_payload: Dict[str, Any]) -> Dict[str, Any]:
    out = _ensure_image_block_placeholders(dict(render_payload or {}))
    slides = out.get("slides")
    if not isinstance(slides, list) or not slides:
        return out

    enabled = str(os.getenv("PPT_IMAGE_ASSET_ENABLED", "true")).strip().lower() not in {"0", "false", "no", "off"}
    serper_api_key = str(_env_value("SERPER_API_KEY", "")).strip()
    if not enabled:
        return out
    serper_enabled = bool(serper_api_key)
    ai_svg_enabled = str(os.getenv("PPT_IMAGE_AI_SVG_ENABLED", "false")).strip().lower() not in {"0", "false", "no", "off"}
    icon_bg_enabled = str(os.getenv("PPT_IMAGE_ICON_BG_ENABLED", "false")).strip().lower() not in {"0", "false", "no", "off"}

    image_search_cache: Dict[str, List[Dict[str, str]]] = {}
    data_uri_cache: Dict[str, str] = {}
    used_image_keys: set[str] = set()
    deck_title = str(out.get("title") or "").strip()
    hl = "zh-cn" if _prefer_zh(deck_title) else "en"
    stock_domain_hints = _stock_image_domain_hints()
    stock_search_domains = [
        part.strip().lower()
        for part in str(_env_value("PPT_STOCK_SEARCH_DOMAINS", "unsplash.com,pexels.com,pixabay.com")).split(",")
        if part.strip()
    ]
    deck_tokens = [deck_title]
    for slide in slides[:6]:
        if isinstance(slide, dict):
            deck_tokens.append(str(slide.get("title") or "").strip())
            deck_tokens.append(str(slide.get("narration") or "").strip())
    deck_blob = " ".join(token for token in deck_tokens if token).strip()
    fallback_stock_terms = (
        [
            f"{deck_blob} 场景 图",
            f"{deck_blob} 商业 插画",
            "科技 商务 数据 可视化",
        ]
        if hl == "zh-cn"
        else [
            f"{deck_blob} scene photo".strip(),
            f"{deck_blob} business illustration".strip(),
            "technology business data visualization",
        ]
    )

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        blocks = slide.get("blocks")
        if not isinstance(blocks, list):
            continue

        for block in blocks:
            if not isinstance(block, dict):
                continue
            if str(block.get("block_type") or block.get("type") or "").strip().lower() != "image":
                continue

            content = block.get("content")
            if isinstance(content, dict):
                content_obj = dict(content)
            else:
                content_obj = {"title": str(content or slide.get("title") or deck_title or "Visual")}
            data = block.get("data")
            data_obj = dict(data) if isinstance(data, dict) else {}

            existing_url = ""
            for key in ("url", "src", "imageUrl", "image_url"):
                existing_url = str(content_obj.get(key) or data_obj.get(key) or block.get(key) or "").strip()
                if existing_url:
                    break
            if existing_url and not _is_placeholder_image_url(existing_url):
                if existing_url.startswith("http://") or existing_url.startswith("https://"):
                    if existing_url not in data_uri_cache:
                        data_uri_cache[existing_url] = await _fetch_image_data_uri(existing_url)
                    if data_uri_cache[existing_url]:
                        content_obj["url"] = data_uri_cache[existing_url]
                        data_obj["source_url"] = existing_url
                        data_obj["source_type"] = data_obj.get("source_type") or "user_url"
                        data_obj["source_level"] = 1
                        data_obj["url"] = content_obj["url"]
                        key = _canonical_image_url_key(existing_url)
                        if key:
                            used_image_keys.add(key)
                block["content"] = content_obj
                if data_obj:
                    block["data"] = data_obj
                continue

            keywords = _extract_image_keywords(slide, block, deck_title)
            search_query = _build_image_search_query(
                deck_title=deck_title,
                slide_title=str(slide.get("title") or ""),
                block_title=str(content_obj.get("title") or content_obj.get("caption") or ""),
                keywords=keywords,
                hl=hl,
            )
            image_context = _infer_image_context(
                deck_title=deck_title,
                slide_title=str(slide.get("title") or ""),
                slide_narration=str(slide.get("narration") or slide.get("speaker_notes") or ""),
                block_title=str(content_obj.get("title") or content_obj.get("caption") or ""),
            )
            if ai_svg_enabled and _is_abstract_image_intent(
                keywords=keywords,
                slide_title=str(slide.get("title") or ""),
                block_title=str(content_obj.get("title") or content_obj.get("caption") or ""),
            ):
                content_obj["url"] = _ai_svg_visual_data_uri(
                    str(content_obj.get("title") or slide.get("title") or "Visual concept"),
                    search_query,
                )
                data_obj["source_type"] = "ai_svg"
                data_obj["source_level"] = 2
                data_obj["semantic_query"] = search_query
                block["content"] = content_obj
                if data_obj:
                    block["data"] = data_obj
                continue

            semantic_tokens = _tokenize_semantic_terms(
                " ".join([deck_title, str(slide.get("title") or ""), str(content_obj.get("title") or "")])
            )
            selected_url = ""
            selected_source = ""
            selected_score = -1e9
            query_candidates = _dedupe_terms([search_query, *keywords], limit=8)
            for keyword in query_candidates:
                if not serper_enabled:
                    continue
                if keyword not in image_search_cache:
                    stock_candidates: List[Dict[str, str]] = []
                    for domain in stock_search_domains:
                        site_query = f"{keyword} site:{domain}"
                        site_candidates = await _search_serper_images(
                            query=site_query,
                            api_key=serper_api_key,
                            num=4,
                            hl=hl,
                        )
                        stock_candidates.extend(site_candidates)
                        if len(stock_candidates) >= 10:
                            break
                    if not stock_candidates:
                        for seed in fallback_stock_terms:
                            for domain in stock_search_domains:
                                site_query = f"{seed} site:{domain}"
                                site_candidates = await _search_serper_images(
                                    query=site_query,
                                    api_key=serper_api_key,
                                    num=4,
                                    hl=hl,
                                )
                                stock_candidates.extend(site_candidates)
                                if len(stock_candidates) >= 10:
                                    break
                            if len(stock_candidates) >= 10:
                                break

                    generic_candidates = await _search_serper_images(
                        query=keyword,
                        api_key=serper_api_key,
                        num=6,
                        hl=hl,
                    )
                    stock_candidates.extend(
                        [
                            item
                            for item in generic_candidates
                            if _is_stock_image_candidate(item, stock_domain_hints)
                        ]
                    )
                    stock_candidates = [
                        item
                        for item in stock_candidates
                        if _is_stock_image_candidate(item, stock_domain_hints)
                    ]

                    ranked_candidates = _dedupe_image_candidates([*stock_candidates, *generic_candidates])
                    image_search_cache[keyword] = ranked_candidates

                candidates = image_search_cache.get(keyword, [])
                for item in candidates:
                    candidate_url = str(item.get("url") or "").strip()
                    if not candidate_url:
                        continue
                    candidate_key = _canonical_image_url_key(candidate_url)
                    if candidate_key and candidate_key in used_image_keys:
                        continue
                    if candidate_url not in data_uri_cache:
                        data_uri_cache[candidate_url] = await _fetch_image_data_uri(candidate_url)
                    if not data_uri_cache[candidate_url]:
                        continue
                    score = _score_image_candidate(
                        item,
                        keyword=keyword,
                        stock_domain_hints=stock_domain_hints,
                        semantic_tokens=semantic_tokens,
                        positive_hints=[str(v) for v in (image_context.get("positive") or [])],
                        negative_hints=[str(v) for v in (image_context.get("negative") or [])],
                    )
                    if score > selected_score:
                        selected_score = score
                        selected_url = candidate_url
                        selected_source = "stock" if _is_stock_image_candidate(item, stock_domain_hints) else "web"

            relevance_min_score = float(_to_float(os.getenv("PPT_IMAGE_RELEVANCE_MIN_SCORE"), 0.08) or 0.08)
            if bool(image_context.get("industrial")):
                relevance_min_score = max(relevance_min_score, 0.18)
            if selected_url and selected_score < relevance_min_score:
                selected_url = ""
                selected_source = ""

            if selected_url:
                data_uri = data_uri_cache[selected_url]
                if data_uri:
                    content_obj["url"] = data_uri
                    data_obj["source_url"] = selected_url
                    data_obj["source_type"] = selected_source or "web"
                    data_obj["source_level"] = 3
                    data_obj["semantic_score"] = round(float(selected_score), 4)
                    data_obj["url"] = content_obj["url"]
                    key = _canonical_image_url_key(selected_url)
                    if key:
                        used_image_keys.add(key)
                else:
                    data_obj["source_type"] = "missing"
            else:
                label = str(content_obj.get("title") or slide.get("title") or deck_title or "Brand Visual")
                if icon_bg_enabled:
                    symbol = _resolve_icon_bg_symbol(
                        keywords=query_candidates,
                        slide_title=str(slide.get("title") or ""),
                        block_title=str(content_obj.get("title") or content_obj.get("caption") or ""),
                    )
                    content_obj["url"] = _icon_background_svg_data_uri(label[:48] or "Visual", symbol)
                    data_obj["source_type"] = "icon_bg"
                    data_obj["source_level"] = 4
                else:
                    content_obj["url"] = _brand_placeholder_svg_data_uri(label[:48] or "Brand Visual")
                    data_obj["source_type"] = "placeholder"
                    data_obj["source_level"] = 5
                data_obj["semantic_score"] = 0.0

            block["content"] = content_obj
            if data_obj:
                block["data"] = data_obj

    out["slides"] = slides
    return out


def _get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
        if url and key:
            _supabase = create_client(url, key)
    return _supabase


def _persist_ppt_retry_diagnostic(payload: Dict[str, Any]) -> None:
    sb = _get_supabase()
    if not sb:
        return
    try:
        sb.table("autoviralvid_ppt_retry_diagnostics").insert(payload).execute()
    except Exception as exc:
        logger.debug("[ppt_service] skip retry diagnostic persistence: %s", exc)


def _persist_ppt_observability_report(payload: Dict[str, Any]) -> None:
    sb = _get_supabase()
    if not sb:
        return
    try:
        sb.table("autoviralvid_ppt_observability_reports").insert(payload).execute()
    except Exception as exc:
        logger.debug("[ppt_service] skip observability report persistence: %s", exc)


def _build_export_alerts(
    *,
    quality_score: Optional[Dict[str, Any]],
    visual_qa: Optional[Dict[str, Any]],
    diagnostics: List[Dict[str, Any]],
    template_renderer_summary: Optional[Dict[str, Any]] = None,
    text_qa: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    score_obj = quality_score if isinstance(quality_score, dict) else {}
    visual_obj = visual_qa if isinstance(visual_qa, dict) else {}
    score_value = _to_float(score_obj.get("score"), None)
    score_threshold = _to_float(score_obj.get("threshold"), None)
    if score_value is not None and score_threshold is not None and score_value < score_threshold:
        alerts.append(
            {
                "severity": "high",
                "code": "quality_score_below_threshold",
                "message": f"quality_score={score_value:.1f} < threshold={score_threshold:.1f}",
            }
        )
    warn_threshold = _to_float(score_obj.get("warn_threshold"), None)
    if score_value is not None and warn_threshold is not None and score_value < warn_threshold:
        alerts.append(
            {
                "severity": "medium",
                "code": "quality_score_below_warn",
                "message": f"quality_score={score_value:.1f} < warn_threshold={warn_threshold:.1f}",
            }
        )

    blank_ratio = _to_float(visual_obj.get("blank_slide_ratio"), None)
    if blank_ratio is not None and blank_ratio > 0.05:
        alerts.append(
            {
                "severity": "high" if blank_ratio >= 0.2 else "medium",
                "code": "visual_blank_ratio_high",
                "message": f"blank_slide_ratio={blank_ratio:.2f}",
            }
        )
    low_contrast_ratio = _to_float(visual_obj.get("low_contrast_ratio"), None)
    if low_contrast_ratio is not None and low_contrast_ratio > 0.25:
        alerts.append(
            {
                "severity": "medium",
                "code": "visual_low_contrast_ratio_high",
                "message": f"low_contrast_ratio={low_contrast_ratio:.2f}",
            }
        )
    blank_area_ratio = _to_float(visual_obj.get("blank_area_ratio"), None)
    if blank_area_ratio is not None and blank_area_ratio > 0.22:
        alerts.append(
            {
                "severity": "medium",
                "code": "visual_blank_area_ratio_high",
                "message": f"blank_area_ratio={blank_area_ratio:.2f}",
            }
        )
    style_drift_ratio = _to_float(visual_obj.get("style_drift_ratio"), None)
    if style_drift_ratio is not None and style_drift_ratio > 0.45:
        alerts.append(
            {
                "severity": "medium",
                "code": "visual_style_drift_ratio_high",
                "message": f"style_drift_ratio={style_drift_ratio:.2f}",
            }
        )
    issue_ratios = visual_obj.get("issue_ratios") if isinstance(visual_obj.get("issue_ratios"), dict) else {}
    for issue_code, limit in (
        ("text_overlap", 0.0),
        ("occlusion", 0.0),
        ("card_overlap", 0.0),
        ("title_crowded", 0.0),
        ("multi_title_bar", 0.0),
        ("text_overflow", 0.0),
        ("irrelevant_image", 0.05),
        ("image_distortion", 0.10),
    ):
        ratio = _to_float(issue_ratios.get(issue_code), None)
        if ratio is None or ratio <= limit:
            continue
        alerts.append(
            {
                "severity": "high" if ratio >= max(0.2, limit + 0.12) else "medium",
                "code": f"visual_{issue_code}_ratio_high",
                "message": f"{issue_code}_ratio={ratio:.2f}",
            }
        )

    failure_count = sum(1 for item in diagnostics if str(item.get("status") or "").endswith("failed"))
    if failure_count >= 2:
        alerts.append(
            {
                "severity": "medium",
                "code": "retry_failures_high",
                "message": f"failed_attempts={failure_count}",
            }
        )

    renderer_summary = (
        template_renderer_summary if isinstance(template_renderer_summary, dict) else {}
    )
    skipped_ratio = _to_float(renderer_summary.get("skipped_ratio"), None)
    evaluated_slides = int(_to_float(renderer_summary.get("evaluated_slides"), 0.0) or 0.0)
    skipped_slides = int(_to_float(renderer_summary.get("skipped_slides"), 0.0) or 0.0)
    if (
        skipped_ratio is not None
        and evaluated_slides > 0
        and skipped_slides > 0
        and skipped_ratio >= _TEMPLATE_RENDERER_SKIP_RATIO_WARN
    ):
        alerts.append(
            {
                "severity": "high"
                if skipped_ratio >= _TEMPLATE_RENDERER_SKIP_RATIO_HIGH
                else "medium",
                "code": "template_renderer_fallback_ratio_high",
                "message": (
                    "template_renderer_fallback_ratio="
                    f"{skipped_ratio:.2f} ({skipped_slides}/{evaluated_slides})"
                ),
            }
        )

    reason_ratios = (
        renderer_summary.get("reason_ratios")
        if isinstance(renderer_summary.get("reason_ratios"), dict)
        else {}
    )
    reason_counts = (
        renderer_summary.get("reason_counts")
        if isinstance(renderer_summary.get("reason_counts"), dict)
        else {}
    )
    dominant_reason = ""
    dominant_ratio: Optional[float] = None
    for reason, ratio_raw in reason_ratios.items():
        ratio = _to_float(ratio_raw, None)
        if ratio is None:
            continue
        if dominant_ratio is None or ratio > dominant_ratio:
            dominant_reason = str(reason or "").strip() or "unknown"
            dominant_ratio = ratio
    if (
        dominant_ratio is not None
        and dominant_ratio >= _TEMPLATE_RENDERER_REASON_CONCENTRATION_HIGH
        and skipped_slides >= 2
    ):
        dominant_count = int(_to_float(reason_counts.get(dominant_reason), 0.0) or 0.0)
        alerts.append(
            {
                "severity": "medium",
                "code": "template_renderer_fallback_reason_concentrated",
                "message": (
                    "template_renderer_fallback_reason="
                    f"{dominant_reason}:{dominant_ratio:.2f} ({dominant_count}/{skipped_slides})"
                ),
            }
        )

    text_obj = text_qa if isinstance(text_qa, dict) else {}
    placeholder_ratio = _to_float(text_obj.get("placeholder_ratio"), None)
    if placeholder_ratio is not None and placeholder_ratio >= _TEXT_QA_PLACEHOLDER_RATIO_WARN:
        alerts.append(
            {
                "severity": "high"
                if placeholder_ratio >= _TEXT_QA_PLACEHOLDER_RATIO_HIGH
                else "medium",
                "code": "text_qa_placeholder_ratio_high",
                "message": f"placeholder_ratio={placeholder_ratio:.2f}",
            }
        )
    missing_body_count = int(_to_float(text_obj.get("missing_body_count"), 0.0) or 0.0)
    slide_count = int(_to_float(text_obj.get("slide_count"), 0.0) or 0.0)
    if slide_count > 0:
        missing_body_ratio = float(missing_body_count) / float(slide_count)
        if missing_body_ratio >= _TEXT_QA_MISSING_BODY_RATIO_WARN:
            alerts.append(
                {
                    "severity": "medium",
                    "code": "text_qa_missing_evidence_body_ratio_high",
                    "message": f"missing_body_ratio={missing_body_ratio:.2f} ({missing_body_count}/{slide_count})",
                }
            )
    assertion_coverage_ratio = _to_float(text_obj.get("assertion_coverage_ratio"), None)
    if (
        assertion_coverage_ratio is not None
        and assertion_coverage_ratio < _TEXT_QA_ASSERTION_COVERAGE_WARN
    ):
        alerts.append(
            {
                "severity": "medium",
                "code": "text_qa_assertion_coverage_low",
                "message": f"assertion_coverage_ratio={assertion_coverage_ratio:.2f}",
            }
        )
    evidence_coverage_ratio = _to_float(text_obj.get("evidence_coverage_ratio"), None)
    if (
        evidence_coverage_ratio is not None
        and evidence_coverage_ratio < _TEXT_QA_EVIDENCE_COVERAGE_WARN
    ):
        alerts.append(
            {
                "severity": "medium",
                "code": "text_qa_evidence_coverage_low",
                "message": f"evidence_coverage_ratio={evidence_coverage_ratio:.2f}",
            }
        )
    if bool(text_obj.get("page_number_discontinuous")):
        page_numbers = text_obj.get("page_numbers") if isinstance(text_obj.get("page_numbers"), list) else []
        alerts.append(
            {
                "severity": "medium",
                "code": "text_qa_page_number_discontinuous",
                "message": f"page_numbers={page_numbers[:12]}",
            }
        )

    markitdown_obj = text_obj.get("markitdown") if isinstance(text_obj.get("markitdown"), dict) else {}
    if markitdown_obj:
        if not bool(markitdown_obj.get("ok")):
            alerts.append(
                {
                    "severity": "low",
                    "code": "text_qa_markitdown_unavailable",
                    "message": str(markitdown_obj.get("error") or "markitdown_extraction_failed")[:180],
                }
            )
        md_placeholder_ratio = _to_float(markitdown_obj.get("placeholder_ratio"), None)
        if md_placeholder_ratio is not None and md_placeholder_ratio >= 0.08:
            alerts.append(
                {
                    "severity": "medium" if md_placeholder_ratio < 0.22 else "high",
                    "code": "text_qa_markitdown_placeholder_ratio_high",
                    "message": f"markitdown_placeholder_ratio={md_placeholder_ratio:.2f}",
                }
            )
        if "markitdown_empty_output" in (
            markitdown_obj.get("issue_codes")
            if isinstance(markitdown_obj.get("issue_codes"), list)
            else []
        ):
            alerts.append(
                {
                    "severity": "medium",
                    "code": "text_qa_markitdown_empty_output",
                    "message": "markitdown output has no extracted text",
                }
            )
    return alerts


class PPTService:
    @staticmethod
    def _cache_render_job(job: RenderJob) -> None:
        _local_render_jobs[job.id] = {
            "id": job.id,
            "project_id": job.project_id,
            "status": job.status,
            "progress": job.progress,
            "lambda_job_id": job.lambda_job_id,
            "output_url": job.output_url,
            "error": job.error,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    async def generate_outline(self, req: OutlineRequest) -> PresentationOutline:
        from src.outline_generator import generate_outline

        return await generate_outline(
            requirement=req.requirement,
            language=req.language,
            num_slides=req.num_slides,
            style=req.style,
            purpose=req.purpose,
        )

    async def generate_content(self, req: ContentRequest) -> List[SlideContent]:
        from src.content_generator import generate_content

        return await generate_content(
            outline=req.outline,
            language=req.language,
        )

    async def generate_research_context(self, req: ResearchRequest) -> ResearchContext:
        topic = req.topic.strip()
        is_zh = req.language == "zh-CN" or _prefer_zh(
            topic,
            req.audience,
            req.purpose,
            req.style_preference,
            req.constraints,
            req.required_facts,
        )
        if is_zh:
            questions = [
                ResearchQuestion(
                    question="这份PPT的核心受众是谁？",
                    category="audience",
                    why="受众决定表达深度、叙事方式和术语密度。",
                ),
                ResearchQuestion(
                    question="这次演示最核心的目标是什么？",
                    category="purpose",
                    why="目标会影响结构是偏说服、汇报还是教学。",
                ),
                ResearchQuestion(
                    question="希望呈现怎样的视觉风格和语气？",
                    category="style",
                    why="风格偏好会直接影响配色、排版和内容密度。",
                ),
                ResearchQuestion(
                    question="必须展示的关键数据有哪些？",
                    category="data",
                    why="关键数据决定图表、KPI和证据链是否完整。",
                ),
                ResearchQuestion(
                    question="页数、时长和重点章节有哪些限制？",
                    category="scope",
                    why="范围约束决定每页信息量和取舍策略。",
                ),
            ]
            fallback_key_data_points = [
                f"{topic} 的市场规模与近3年增速",
                f"{topic} 的目标人群与转化漏斗",
                f"{topic} 的核心经营指标（收入/成本/ROI）",
                f"{topic} 的竞争格局与差异化优势",
                f"{topic} 的阶段目标与里程碑",
            ]
        else:
            questions = [
                ResearchQuestion(
                    question="Who is the primary audience for this deck?",
                    category="audience",
                    why="Audience determines language depth, examples, and narrative framing.",
                ),
                ResearchQuestion(
                    question="What is the primary objective of this presentation?",
                    category="purpose",
                    why="Objective drives whether the structure is persuasive, reporting, or educational.",
                ),
                ResearchQuestion(
                    question="Which visual tone and style is preferred?",
                    category="style",
                    why="Style preference affects theme, palette, and layout density.",
                ),
                ResearchQuestion(
                    question="Which key data points must be shown?",
                    category="data",
                    why="Must-have data determines chart and KPI component choices.",
                ),
                ResearchQuestion(
                    question="What are the page-count and time constraints?",
                    category="scope",
                    why="Scope constraints decide per-slide density and priority allocation.",
                ),
            ]
            fallback_key_data_points = [
                f"{topic} market size and 3-year growth trend",
                f"{topic} target audience and conversion funnel",
                f"{topic} core metrics (revenue/cost/ROI)",
                f"{topic} competitor comparison and differentiation",
                f"{topic} milestones and phased goals",
            ]
        required_facts = _dedup_strings(list(req.required_facts or []), limit=12)
        gaps = _build_research_gaps(req, is_zh=is_zh)
        search_queries = _build_research_queries(req, is_zh=is_zh, gaps=gaps)
        base_score = _score_research_completeness(
            req,
            key_data_points=0,
            references=0,
            evidence_count=0,
            gaps=gaps,
        )
        should_enrich = bool(req.web_enrichment) and (
            base_score < req.min_completeness
            or any(gap.severity in {"high", "medium"} for gap in gaps)
        )

        key_data_points: List[str] = []
        references: List[Dict[str, str]] = []
        evidence: List[ResearchEvidence] = []
        serper_api_key = str(_env_value("SERPER_API_KEY", "")).strip()

        if should_enrich and serper_api_key:
            seen_urls = set()
            fetched_at = _utc_now()
            for query in search_queries:
                items = await _search_serper_web(
                    query=query,
                    api_key=serper_api_key,
                    num=req.max_search_results,
                    gl="cn" if is_zh else "us",
                    hl="zh-cn" if is_zh else "en",
                )
                for item in items:
                    url = str(item.get("url") or "").strip()
                    title = str(item.get("title") or "").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    if not url or not title or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    confidence = _score_evidence_confidence(url, snippet)
                    references.append({"title": title, "url": url})
                    evidence.append(
                        ResearchEvidence(
                            claim=(snippet or title)[:500],
                            source_title=title[:300],
                            source_url=url,
                            snippet=snippet[:800],
                            fetched_at=fetched_at,
                            confidence=confidence,
                            provenance="web",
                            tags=_dedup_strings(
                                [
                                    "required_fact"
                                    for fact in required_facts
                                    if fact.lower() in f"{title} {snippet}".lower()
                                ],
                                limit=4,
                            ),
                        )
                    )
                    if snippet:
                        key_data_points.append(snippet[:180])
                    key_data_points.append(title[:140])
                if len(references) >= max(req.desired_citations, 3) and len(key_data_points) >= 8:
                    break
        elif should_enrich and not serper_api_key:
            logger.info(
                "[ppt_service] SERPER_API_KEY missing; fallback to synthesized research context for topic=%s",
                topic,
            )

        dedup_points = _dedup_strings(
            [*required_facts, *key_data_points, *fallback_key_data_points],
            limit=8,
        )
        guard = 0
        while len(dedup_points) < 3:
            dedup_points.append(
                (
                    f"{topic} 的关键指标需进一步补充来源（补充项{guard + 1}）"
                    if is_zh
                    else f"{topic} key metrics need additional verifiable sources ({guard + 1})"
                )
            )
            dedup_points = _dedup_strings(dedup_points, limit=8)
            guard += 1
            if guard >= 3:
                break

        dedup_refs: List[Dict[str, str]] = []
        seen_urls = set()
        for row in references:
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            dedup_refs.append({"title": title, "url": url})
            if len(dedup_refs) >= max(req.desired_citations + 2, 5):
                break

        if len(dedup_refs) < req.desired_citations:
            for query in search_queries:
                fallback_url = f"https://www.google.com/search?q={url_quote(query)}"
                if fallback_url in seen_urls:
                    continue
                seen_urls.add(fallback_url)
                dedup_refs.append(
                    {
                        "title": (
                            f"待核验检索入口：{query}"
                            if is_zh
                            else f"Search entry to verify: {query}"
                        )[:300],
                        "url": fallback_url,
                    }
                )
                if len(dedup_refs) >= req.desired_citations:
                    break

        unresolved_gaps = list(gaps)
        if len(dedup_refs) < req.desired_citations:
            unresolved_gaps.append(
                ResearchGap(
                    code="citations",
                    severity="high",
                    message=(
                        f"可用参考来源不足（{len(dedup_refs)}/{req.desired_citations}）"
                        if is_zh
                        else f"Insufficient references ({len(dedup_refs)}/{req.desired_citations})"
                    ),
                    query_hint=search_queries[0] if search_queries else topic,
                )
            )

        if required_facts:
            evidence_corpus = " ".join(
                [*dedup_points, *[e.claim for e in evidence], *[e.snippet for e in evidence]]
            ).lower()
            missing_facts = [fact for fact in required_facts if fact.lower() not in evidence_corpus]
            for fact in missing_facts[:3]:
                unresolved_gaps.append(
                    ResearchGap(
                        code="required_facts",
                        severity="medium",
                        message=(
                            f"关键数据点未被覆盖：{fact}"
                            if is_zh
                            else f"Required fact not covered: {fact}"
                        ),
                        query_hint=fact,
                    )
                )

        dedup_gaps: List[ResearchGap] = []
        seen_gap_keys = set()
        for gap in unresolved_gaps:
            marker = f"{gap.code}|{gap.message.strip().lower()}|{gap.query_hint.strip().lower()}"
            if marker in seen_gap_keys:
                continue
            seen_gap_keys.add(marker)
            dedup_gaps.append(gap)

        completeness_score = _score_research_completeness(
            req,
            key_data_points=len(dedup_points),
            references=len(dedup_refs),
            evidence_count=len(evidence),
            gaps=dedup_gaps,
        )
        enrichment_strategy = (
            "web" if evidence else ("web+fallback" if should_enrich else "none")
        )
        return ResearchContext(
            topic=topic,
            language="zh-CN" if is_zh else "en-US",
            audience=req.audience,
            purpose=req.purpose,
            style_preference=req.style_preference,
            constraints=req.constraints,
            required_facts=required_facts,
            geography=req.geography,
            time_range=req.time_range,
            domain_terms=req.domain_terms,
            key_data_points=dedup_points[:8],
            reference_materials=dedup_refs[: max(req.desired_citations, 3)],
            evidence=evidence[:12],
            gap_report=dedup_gaps[:12],
            completeness_score=completeness_score,
            enrichment_applied=bool(should_enrich),
            enrichment_strategy=enrichment_strategy,
            questions=questions,
        )

    async def generate_outline_plan(self, req: OutlinePlanRequest) -> OutlinePlan:
        total_pages = req.total_pages
        data_points = [str(x).strip() for x in req.research.key_data_points if str(x).strip()]
        if not data_points:
            data_points = [req.research.topic]
        is_zh = _prefer_zh(req.research.topic, req.research.audience, req.research.purpose)

        notes: List[StickyNote] = []
        for idx in range(total_pages):
            page_number = idx + 1
            if idx == 0:
                core_message = (
                    f"{req.research.topic}总览"[:30]
                    if is_zh
                    else f"{req.research.topic} overview"
                )
                density = "low"
                data_elements: List[str] = []
                visual_anchor = "title"
            elif idx == 1 and total_pages >= 6:
                core_message = "目录与结构" if is_zh else "Table of contents"
                density = "low"
                data_elements = ["toc", "agenda"]
                visual_anchor = "toc"
            elif idx == total_pages - 1:
                core_message = (
                    f"{req.research.topic}关键结论"[:30]
                    if is_zh
                    else f"{req.research.topic} key takeaways"
                )
                density = "low"
                data_elements = ["summary", "action"]
                visual_anchor = "summary"
            elif total_pages >= 10 and idx in {max(2, total_pages // 3), max(3, (total_pages * 2) // 3)}:
                core_message = (
                    f"第{1 if idx <= total_pages // 2 else 2}阶段重点"
                    if is_zh
                    else f"Section {1 if idx <= total_pages // 2 else 2}"
                )
                density = "low"
                data_elements = ["section", "transition"]
                visual_anchor = "section"
            else:
                seed = data_points[(idx - 1) % len(data_points)]
                core_message = seed[:30]
                if idx % 4 == 0:
                    data_elements = ["kpi", "chart", "table", "trend"]
                elif idx % 3 == 0:
                    data_elements = ["kpi", "chart", "comparison"]
                elif idx % 2 == 0:
                    data_elements = ["timeline", "list"]
                else:
                    data_elements = ["list", "insight"]
                density = "high" if len(data_elements) >= 3 else "medium"
                visual_anchor = "chart" if "chart" in data_elements or "kpi" in data_elements else "text"

            point_base = idx % len(data_points)
            points = [
                data_points[(point_base + 0) % len(data_points)][:120],
                data_points[(point_base + 1) % len(data_points)][:120],
                data_points[(point_base + 2) % len(data_points)][:120],
            ]

            seed_note = StickyNote(
                page_number=page_number,
                core_message=core_message[:30],
                layout_hint="split_2",
                content_density=density,  # type: ignore[arg-type]
                data_elements=data_elements,
                visual_anchor=visual_anchor,
                key_points=points,
                speaker_notes=(
                    f"第{page_number}页：突出一个核心观点，并给出可执行结论。"
                    if is_zh
                    else f"Page {page_number} focus with concise storyline."
                ),
            )
            layout = recommend_layout(seed_note, idx, total_pages)
            if any(item in {"toc", "section"} for item in data_elements):
                layout = "hero_1"
            notes.append(seed_note.model_copy(update={"layout_hint": layout}))

        fixed_layouts = enforce_layout_diversity([note.layout_hint for note in notes])
        fixed_layouts = enforce_density_rhythm(fixed_layouts)
        notes = [
            note.model_copy(
                update={
                    "layout_hint": fixed_layouts[idx],
                    "content_density": (
                        "high"
                        if density_level_for_layout(fixed_layouts[idx]) == "high"
                        else ("low" if density_level_for_layout(fixed_layouts[idx]) in {"low", "breathing"} else "medium")
                    ),
                }
            )
            for idx, note in enumerate(notes)
        ]

        return OutlinePlan(
            title=req.research.topic,
            total_pages=total_pages,
            theme_suggestion="slate_minimal",
            style_suggestion="soft",
            notes=notes,
            logic_flow=(
                "先交代背景与问题，再给出证据和方案，最后收束到行动建议。"
                if is_zh
                else "Open with context, build evidence and proposals, end with clear actions."
            ),
        )

    async def generate_presentation_plan(
        self, req: PresentationPlanRequest
    ) -> PresentationPlan:
        is_zh = _prefer_zh(req.outline.title, req.research.topic if req.research else "")
        total_outline_pages = len(req.outline.notes)

        def _kpi_seed(page_number: int) -> int:
            return 80 + ((page_number * 17) % 65)

        def _chart_series(base: int) -> List[int]:
            return [base, int(base * 1.18), int(base * 1.36)]

        def _labels() -> List[str]:
            return ["2024", "2025E", "2026E"] if is_zh else ["2024", "2025E", "2026E"]

        def _compact_points(
            points: List[str],
            *,
            max_points: int = 4,
            max_chars: int = 96,
        ) -> List[str]:
            dedup: List[str] = []
            seen = set()
            for raw in points or []:
                text = str(raw or "").strip()
                if not text:
                    continue
                for piece in re.split(r"[;；,\n，。.!?]+", text):
                    item = str(piece or "").strip()
                    if len(item) < 4:
                        continue
                    clipped = item[:max_chars].strip()
                    if not clipped:
                        continue
                    key = clipped.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    dedup.append(clipped)
                    if len(dedup) >= max_points:
                        return dedup
            return dedup

        def _split_points_for_two_columns(points: List[str]) -> tuple[List[str], List[str]]:
            unique: List[str] = []
            seen = set()
            for item in points:
                text = str(item or "").strip()
                if not text:
                    continue
                key = text.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(text)
            if not unique:
                return [], []
            if len(unique) == 1:
                return [unique[0]], []
            pivot = max(1, (len(unique) + 1) // 2)
            left = unique[:pivot]
            right = unique[pivot:]
            if not right:
                right = unique[-1:]
            return left, right

        def _resolve_note_slide_type(note: StickyNote, note_idx: int) -> str:
            if note_idx <= 0:
                return "cover"
            if note_idx >= max(0, total_outline_pages - 1):
                return "summary"
            elements = {
                str(item or "").strip().lower()
                for item in (note.data_elements or [])
                if str(item or "").strip()
            }
            core_message = str(note.core_message or "").strip().lower()
            if "toc" in elements or "agenda" in elements or "目录" in core_message or "table of contents" in core_message:
                return "toc"
            if "section" in elements or "transition" in elements:
                return "divider"
            return _layout_to_slide_type(note.layout_hint)

        slides: List[SlidePlan] = []
        research_key_points = [
            str(item or "").strip()
            for item in ((req.research.key_data_points if req.research else []) or [])
            if str(item or "").strip()
        ]
        for note_idx, note in enumerate(req.outline.notes):
            lower_elements = [str(item).strip().lower() for item in note.data_elements]
            strategy = build_slide_content_strategy(
                note,
                is_zh=is_zh,
                research_points=research_key_points,
            )
            title_text = str(strategy.assertion or note.core_message).strip() or str(note.core_message)
            need_chart = ("chart" in lower_elements) or note.layout_hint in {"grid_3", "grid_4", "bento_6", "timeline"}
            need_kpi = ("kpi" in lower_elements) or note.layout_hint in {"grid_3", "bento_6"}
            need_image = ("image" in lower_elements) or note.visual_anchor.lower() in {"image", "图片", "图像"} or note.layout_hint in {"asymmetric_2", "bento_5"}
            compact_points = _compact_points(strategy.evidence or note.key_points, max_points=4, max_chars=96)
            if not compact_points:
                compact_points = (
                    ["核心结论", "关键论据", "落地动作"]
                    if is_zh
                    else ["Core insight", "Key evidence", "Execution action"]
                )

            blocks: List[ContentBlock] = [
                ContentBlock(
                    block_type="title",
                    position="top",
                    content=title_text,
                    emphasis=[],
                )
            ]

            if note.layout_hint == "cover":
                blocks.append(
                    ContentBlock(
                        block_type="subtitle",
                        position="center",
                        content=(
                            "围绕核心价值主张，建立背景、痛点与机会的第一页认知。"
                            if is_zh
                            else "Opening statement tailored to target audience."
                        ),
                        emphasis=["value"],
                    )
                )
            elif note.layout_hint == "summary":
                blocks.append(
                    ContentBlock(
                        block_type="list",
                        position="center",
                        content="; ".join(compact_points[:3]),
                        emphasis=["conclusion", "action"] if not is_zh else ["结论", "行动"],
                    )
                )
            else:
                left_points, right_points = _split_points_for_two_columns(compact_points)
                if not left_points:
                    left_points = compact_points[:1]
                if not right_points:
                    right_points = compact_points[-1:] or left_points[:1]
                if need_kpi:
                    kpi_value = _kpi_seed(note.page_number)
                    blocks.append(
                        ContentBlock(
                            block_type="kpi",
                            position="left",
                            content="核心指标" if is_zh else "Core KPI",
                            data={
                                "number": kpi_value,
                                "unit": "%" if ("占比" in title_text or "增长" in title_text or not is_zh) else "点",
                                "trend": 6 + (note.page_number % 12),
                                "label": title_text[:24],
                            },
                            emphasis=["growth"] if not is_zh else ["增长"],
                        )
                    )
                if need_chart:
                    base = 35 + (note.page_number * 9)
                    blocks.append(
                        ContentBlock(
                            block_type="chart",
                            position="right" if need_kpi else "center",
                            content="趋势对比" if is_zh else "Trend comparison",
                            data={
                                "chartType": "bar",
                                "labels": _labels(),
                                "datasets": [
                                    {
                                        "label": "关键指标" if is_zh else "Key metric",
                                        "data": _chart_series(base),
                                    }
                                ],
                            },
                            emphasis=["trend"] if not is_zh else ["趋势"],
                        )
                    )
                if need_image:
                    blocks.append(
                        ContentBlock(
                            block_type="image",
                            position="right" if not need_chart else "bottom_right",
                            content="视觉锚点图" if is_zh else "Visual anchor image",
                            data={
                                "title": title_text,
                                "keywords": [req.outline.title, title_text, note.visual_anchor],
                            },
                            emphasis=["visual_anchor"],
                        )
                    )
                blocks.append(
                    ContentBlock(
                        block_type="body",
                        position="left",
                        content="; ".join(left_points),
                        emphasis=["focus"] if not is_zh else ["重点"],
                    )
                )
                blocks.append(
                    ContentBlock(
                        block_type="list",
                        position="right",
                        content="; ".join(right_points),
                        emphasis=["evidence"] if not is_zh else ["证据"],
                    )
                )

            slides.append(
                SlidePlan(
                    page_number=note.page_number,
                    slide_type=_resolve_note_slide_type(note, note_idx),  # type: ignore[arg-type]
                    layout_grid=note.layout_hint,
                    blocks=blocks,
                    bg_style="light",
                    image_keywords=[req.outline.title, note.visual_anchor],
                    content_strategy=SlideContentStrategy(
                        assertion=title_text[:220],
                        evidence=compact_points[:6],
                        data_anchor=str(strategy.data_anchor or "")[:160],
                        page_role=str(strategy.page_role or "argument"),
                        density_hint=str(strategy.density_hint or "medium"),
                        render_path=str(strategy.render_path or "pptxgenjs"),
                    ),
                    notes_for_designer=(
                        "保证标题层级明显，视觉锚点优先，图文区域留足呼吸感。"
                        if is_zh
                        else "Keep hierarchy clear and prioritize readability."
                    ),
                )
            )

        return PresentationPlan(
            title=req.outline.title,
            theme=req.outline.theme_suggestion,
            style=req.outline.style_suggestion,
            slides=slides,
            global_notes=(
                "先确保内容完整与证据链，再做视觉打磨。"
                if is_zh
                else "Prioritize content completeness and logic before styling polish."
            ),
        )

    async def run_ppt_pipeline(self, req: PPTPipelineRequest) -> PPTPipelineResult:
        from src.minimax_exporter import export_minimax_pptx
        from src.ppt_quality_gate import (
            score_deck_quality,
            validate_deck,
            validate_layout_diversity,
            validate_visual_audit,
        )
        from src.ppt_route_strategy import resolve_route_policy

        run_id = _new_id()
        stages: List[PPTPipelineStageStatus] = []
        requested_quality_profile = _resolve_quality_profile_id(
            req.quality_profile,
            topic=req.topic,
            purpose=req.purpose,
            audience=req.audience,
            total_pages=req.total_pages,
        )
        route_policy = resolve_route_policy(
            req.route_mode,
            slide_count=int(req.total_pages),
            constraint_count=(
                len(req.constraints or [])
                + len(req.required_facts or [])
                + len(req.domain_terms or [])
            ),
            quality_profile=requested_quality_profile,
            has_explicit_template=False,
            visual_density="balanced",
        )

        def _append_stage(
            stage: str,
            started_at: str,
            ok: bool,
            diagnostics: Optional[List[str]] = None,
        ) -> None:
            stages.append(
                PPTPipelineStageStatus(
                    stage=stage,  # type: ignore[arg-type]
                    ok=ok,
                    started_at=started_at,
                    finished_at=_utc_now(),
                    diagnostics=diagnostics or [],
                )
            )

        # Stage 1: research
        research_started = _utc_now()
        research_req = ResearchRequest(
            topic=req.topic,
            language=req.language,
            audience=req.audience,
            purpose=req.purpose,
            style_preference=req.style_preference,
            constraints=req.constraints,
            required_facts=req.required_facts,
            geography=req.geography,
            time_range=req.time_range,
            domain_terms=req.domain_terms,
            web_enrichment=req.web_enrichment,
            min_completeness=req.research_min_completeness,
            desired_citations=req.desired_citations,
            max_web_queries=req.max_web_queries,
            max_search_results=req.max_search_results,
        )
        research = await self.generate_research_context(research_req)
        min_points = max(3, int(req.min_key_data_points))
        min_refs = max(1, int(req.min_reference_materials))
        failures: List[str] = []
        if len(research.key_data_points) < min_points:
            failures.append(f"insufficient key_data_points (<{min_points})")
        if len(research.reference_materials) < min_refs:
            failures.append(f"insufficient reference_materials (<{min_refs})")
        if float(research.completeness_score) < float(req.research_min_completeness):
            failures.append(
                "insufficient completeness "
                f"({research.completeness_score:.3f} < {float(req.research_min_completeness):.3f})"
            )
        diagnostics = [
            f"completeness={research.completeness_score:.3f}",
            f"references={len(research.reference_materials)}",
            f"evidence={len(research.evidence)}",
            f"gaps={len(research.gap_report)}",
            f"enrichment={research.enrichment_strategy}",
        ]
        if failures:
            _append_stage("research", research_started, False, failures + diagnostics)
            raise ValueError("Research stage failed: " + "; ".join(failures[:3]))
        _append_stage("research", research_started, True, diagnostics)
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-1-research", research.model_dump())

        # Stage 2: sticky-note outline plan
        outline_started = _utc_now()
        outline_plan = await self.generate_outline_plan(
            OutlinePlanRequest(
                research=research,
                total_pages=req.total_pages,
            )
        )
        _append_stage("outline_plan", outline_started, True)
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-2-outline-plan", outline_plan.model_dump())

        # Stage 3: wireframe presentation plan
        presentation_started = _utc_now()
        presentation_plan = await self.generate_presentation_plan(
            PresentationPlanRequest(outline=outline_plan, research=research)
        )
        _append_stage("presentation_plan", presentation_started, True)
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-3-presentation-plan", presentation_plan.model_dump())

        base_render_payload = _apply_skill_planning_to_render_payload(
            _presentation_plan_to_render_payload(presentation_plan)
        )
        if str(req.quality_profile or "").strip() and str(req.quality_profile).strip().lower() != "auto":
            base_render_payload["quality_profile"] = str(req.quality_profile).strip()
        render_payload = await _hydrate_image_assets(
            _apply_visual_orchestration(base_render_payload)
        )

        # Stage 4: strict quality gate before any render/export
        quality_started = _utc_now()
        quality_issues = []
        quality_profile = _resolve_quality_profile_id(
            str(render_payload.get("quality_profile") or req.quality_profile or "auto"),
            topic=req.topic,
            purpose=req.purpose,
            audience=req.audience,
            total_pages=req.total_pages,
        )
        pipeline_strict_quality_mode = _is_strict_quality_mode(
            constraint_hardness="minimal",
            hardness_profile=render_payload.get("hardness_profile"),
            route_mode=route_policy.mode,
            quality_profile=quality_profile,
        )
        pipeline_constraint_hardness = "strict" if pipeline_strict_quality_mode else "minimal"
        quality_score = None
        quality_score_failed = False
        for _attempt in range(1, max(1, int(route_policy.max_retry_attempts)) + 1):
            content_gate = validate_deck(
                render_payload.get("slides") or [],
                profile=quality_profile,
            )
            layout_gate = validate_layout_diversity(
                render_payload,
                profile=quality_profile,
                enforce_terminal_slide_types=True,
            )
            quality_issues = [*content_gate.issues, *layout_gate.issues]
            quality_score = score_deck_quality(
                slides=render_payload.get("slides") or [],
                render_spec=render_payload,
                profile=quality_profile,
                content_issues=content_gate.issues,
                layout_issues=layout_gate.issues,
            )
            score_passed = bool(quality_score.passed) if route_policy.require_weighted_quality_score else True
            quality_score_failed = not score_passed
            if (not quality_issues) and score_passed:
                break
            # Stage 2 repair: enforce visual contract and asset placeholders before retrying.
            render_payload = _apply_skill_planning_to_render_payload(render_payload)
            render_payload = await _hydrate_image_assets(_apply_visual_orchestration(render_payload))
            if _attempt >= max(1, int(route_policy.max_retry_attempts)):
                break

        if quality_issues or quality_score_failed:
            diagnostics = _collect_stage_diagnostics(
                "quality",
                [
                    f"{issue.slide_id}:{issue.code}:{issue.message}"
                    for issue in quality_issues
                ],
                limit=20,
            )
            score_diag = []
            if quality_score is not None:
                score_diag = [f"score={quality_score.score:.1f}/{quality_score.threshold:.1f}"]
            if quality_score_failed and not diagnostics:
                diagnostics = ["deck:quality_score_low:weighted quality score below threshold"]
            _append_stage(
                "quality_gate",
                quality_started,
                False,
                diagnostics + [f"profile={quality_profile}", f"route={route_policy.mode}", *score_diag],
            )
            raise ValueError("Quality gate failed: " + "; ".join(diagnostics[:6]))
        quality_success_diag = [f"profile={quality_profile}", f"route={route_policy.mode}"]
        if quality_score is not None:
            quality_success_diag.append(f"score={quality_score.score:.1f}/{quality_score.threshold:.1f}")
        _append_stage("quality_gate", quality_started, True, quality_success_diag)
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-4-render-payload", render_payload)

        export_data: Optional[Dict[str, Any]] = None
        export_started = _utc_now()
        if req.with_export:
            pipeline_layer1_design = _run_layer1_design_skill_chain(
                deck_title=req.title or presentation_plan.title,
                slides=list(render_payload.get("slides") or []),
                requested_style_variant=req.minimax_style_variant,
                requested_palette_key=req.minimax_palette_key,
                requested_template_family="auto",
                requested_skill_profile=str(render_payload.get("skill_profile") or "auto"),
            )
            pipeline_style_variant = str(
                pipeline_layer1_design.get("style_variant") or req.minimax_style_variant
            )
            pipeline_palette_key = str(
                pipeline_layer1_design.get("palette_key") or req.minimax_palette_key
            )
            pipeline_skill_profile = str(
                pipeline_layer1_design.get("skill_profile") or render_payload.get("skill_profile") or ""
            )
            export_channel = _resolve_export_channel(req.export_channel)
            export_data = export_minimax_pptx(
                slides=render_payload["slides"],
                title=req.title or presentation_plan.title,
                author=req.author,
                render_channel=export_channel,
                route_mode=route_policy.mode,
                style_variant=pipeline_style_variant,
                palette_key=pipeline_palette_key,
                deck_id=run_id,
                generator_mode="official",
                original_style=False,
                disable_local_style_rewrite=False,
                visual_priority=True,
                visual_preset="tech_cinematic",
                visual_density="balanced",
                constraint_hardness=pipeline_constraint_hardness,
                svg_mode="on",
                template_family="auto",
                template_id=str(render_payload.get("template_id") or ""),
                skill_profile=pipeline_skill_profile,
                hardness_profile=str(render_payload.get("hardness_profile") or ""),
                schema_profile=str(render_payload.get("schema_profile") or ""),
                contract_profile=str(render_payload.get("contract_profile") or ""),
                quality_profile=quality_profile,
                enforce_visual_contract=True,
                timeout=180,
            )
            layer1_runtime = (
                pipeline_layer1_design.get("runtime")
                if isinstance(pipeline_layer1_design.get("runtime"), dict)
                else {}
            )
            if isinstance(export_data, dict):
                export_data["style_variant"] = pipeline_style_variant
                export_data["palette_key"] = pipeline_palette_key
                export_data["skill_profile"] = pipeline_skill_profile
                if layer1_runtime:
                    export_data["layer1_skill_runtime"] = layer1_runtime
            _append_stage("export", export_started, True, [f"channel={export_channel}", f"route={route_policy.mode}"])
            if req.save_artifacts and isinstance(export_data, dict):
                _write_pipeline_artifact(run_id, "stage-5-export", export_data)
        else:
            _append_stage("export", export_started, True, ["skipped by request"])

        return PPTPipelineResult(
            run_id=run_id,
            stages=stages,
            artifacts=PPTPipelineArtifacts(
                research=research,
                outline_plan=outline_plan,
                presentation_plan=presentation_plan,
                render_payload=render_payload,
            ),
            export=export_data,
        )

    async def export_pptx(self, req: ExportRequest) -> Dict[str, Any]:
        import asyncio

        from src.minimax_exporter import MiniMaxExportError, export_minimax_pptx
        from src.ppt_failure_classifier import classify_failure
        from src.ppt_patch_merge import merge_render_spec
        from src.ppt_quality_gate import (
            score_deck_quality,
            validate_deck,
            validate_layout_diversity,
            validate_visual_audit,
        )
        from src.ppt_route_strategy import resolve_route_policy
        from src.ppt_retry_orchestrator import (
            build_retry_hint,
            compute_render_path_downgrade,
            make_retry_decision,
        )
        from src.ppt_visual_qa import (
            audit_rendered_slides,
            audit_textual_slides,
            run_markitdown_text_qa,
        )
        from src.pptx_engine import fill_template_pptx
        from src.pptx_rasterizer import rasterize_pptx_bytes_to_png_bytes
        from src.r2 import upload_bytes_to_r2

        raw_slides_data = [s.model_dump() for s in req.slides]
        slides_data = [dict(item) for item in raw_slides_data]
        layer1_design = _run_layer1_design_skill_chain(
            deck_title=req.title,
            slides=slides_data,
            requested_style_variant=req.minimax_style_variant,
            requested_palette_key=req.minimax_palette_key,
            requested_template_family=req.template_family,
            requested_skill_profile=req.skill_profile,
        )
        effective_style_variant = str(layer1_design.get("style_variant") or req.minimax_style_variant)
        effective_palette_key = str(layer1_design.get("palette_key") or req.minimax_palette_key)
        effective_template_family = str(layer1_design.get("template_family") or req.template_family)
        effective_skill_profile = str(layer1_design.get("skill_profile") or req.skill_profile)
        requested_quality_profile = _resolve_quality_profile_id(
            req.quality_profile,
            topic=req.title,
            purpose=req.retry_hint,
            audience=req.author,
            total_pages=len(slides_data),
        )
        visual_seed = await _hydrate_image_assets(
            _apply_visual_orchestration(
                _apply_skill_planning_to_render_payload(
                    {
                        "title": req.title,
                        "theme": {"palette": effective_palette_key, "style": effective_style_variant},
                        "slides": slides_data,
                        "template_family": effective_template_family,
                        "template_id": effective_template_family if effective_template_family != "auto" else "",
                        "skill_profile": effective_skill_profile,
                        "hardness_profile": req.hardness_profile,
                        "schema_profile": req.schema_profile,
                        "contract_profile": req.contract_profile,
                        "quality_profile": requested_quality_profile,
                        "svg_mode": req.svg_mode,
                    }
                )
            )
        )
        orchestrated_slides = visual_seed.get("slides")
        if isinstance(orchestrated_slides, list):
            slides_data = orchestrated_slides
        skill = "minimax_pptx_generator"
        logger.info("[ppt_service] export_pptx using skill=%s", skill)

        retry_enabled = str(os.getenv("PPT_RETRY_ENABLED", "true")).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        partial_retry_enabled = (
            str(os.getenv("PPT_PARTIAL_RETRY_ENABLED", "true")).strip().lower()
            not in {"0", "false", "no", "off"}
        )
        max_retry_attempts = max(1, int(os.getenv("PPT_RETRY_MAX_ATTEMPTS", "3")))
        route_policy = resolve_route_policy(
            req.route_mode,
            slide_count=len(slides_data),
            constraint_count=(
                len(req.target_slide_ids or [])
                + len(req.target_block_ids or [])
                + (1 if str(req.retry_hint or "").strip() else 0)
                + (1 if str(effective_template_family or "").strip().lower() not in {"", "auto"} else 0)
            ),
            quality_profile=requested_quality_profile,
            has_explicit_template=str(effective_template_family or "").strip().lower() not in {"", "auto"},
            visual_density=req.visual_density,
        )
        if route_policy.mode == "fast":
            max_retry_attempts = min(max_retry_attempts, route_policy.max_retry_attempts)
        elif route_policy.mode == "refine":
            max_retry_attempts = max(max_retry_attempts, route_policy.max_retry_attempts)
        else:
            max_retry_attempts = min(max_retry_attempts, route_policy.max_retry_attempts)
        partial_retry_enabled = partial_retry_enabled and route_policy.partial_retry_enabled
        env_generator_mode = str(os.getenv("PPT_GENERATOR_MODE", "official")).strip().lower()
        if env_generator_mode not in {"official", "legacy"}:
            env_generator_mode = "official"
        allow_legacy_mode = _env_flag("PPT_ALLOW_LEGACY_MODE", "false")
        enable_legacy_fallback = _env_flag("PPT_ENABLE_LEGACY_FALLBACK", "false") and allow_legacy_mode

        retry_scope = req.retry_scope
        target_slide_ids = list(req.target_slide_ids or [])
        target_block_ids = list(req.target_block_ids or [])
        retry_hint = req.retry_hint
        deck_id = req.deck_id or _new_id()
        export_channel = _resolve_export_channel(req.export_channel)
        quality_profile = _resolve_quality_profile_id(
            str(req.quality_profile or visual_seed.get("quality_profile") or "auto"),
            topic=req.title,
            purpose=req.retry_hint,
            audience=req.author,
            total_pages=len(slides_data),
        )
        requested_constraint_hardness = _normalize_constraint_hardness(req.constraint_hardness)
        strict_quality_mode = _is_strict_quality_mode(
            constraint_hardness=requested_constraint_hardness,
            hardness_profile=req.hardness_profile or visual_seed.get("hardness_profile"),
            route_mode=route_policy.mode,
            quality_profile=quality_profile,
        )
        if strict_quality_mode and requested_constraint_hardness != "strict":
            requested_constraint_hardness = "strict"
        template_file_url = str(req.template_file_url or "").strip()
        if template_file_url:
            template_bytes = await _download_remote_file_bytes(template_file_url, suffix=".pptx")
            template_skill_runtime: Dict[str, Any] = {}
            try:
                from src.installed_skill_executor import execute_installed_skill_request

                template_skill_runtime = execute_installed_skill_request(
                    {
                        "version": 1,
                        "requested_skills": [
                            "ppt-editing-skill",
                            "ppt-orchestra-skill",
                            "design-style-skill",
                            "color-font-skill",
                        ],
                        "slide": (
                            dict(raw_slides_data[0])
                            if raw_slides_data and isinstance(raw_slides_data[0], dict)
                            else {"slide_type": "cover", "title": req.title}
                        ),
                        "deck": {
                            "title": req.title,
                            "topic": req.title,
                            "total_slides": len(raw_slides_data),
                            "template_family": effective_template_family,
                            "style_variant": effective_style_variant,
                            "palette_key": effective_palette_key,
                        },
                    }
                )
                if _require_direct_skill_runtime():
                    _assert_skill_runtime_success(
                        stage="template_edit",
                        skill_output=template_skill_runtime if isinstance(template_skill_runtime, dict) else {},
                        requested_skills=[
                            "ppt-editing-skill",
                            "ppt-orchestra-skill",
                            "design-style-skill",
                            "color-font-skill",
                        ],
                    )
            except Exception as exc:
                if _require_direct_skill_runtime():
                    raise RuntimeError(f"template_skill_runtime_failed:{str(exc)[:180]}") from exc
                template_skill_runtime = {
                    "error": f"template_skill_runtime_failed:{str(exc)[:180]}",
                }
            template_markitdown_summary: Dict[str, Any] = {}
            try:
                template_markitdown_summary = await asyncio.to_thread(
                    run_markitdown_text_qa,
                    template_bytes,
                    timeout_sec=20,
                )
            except Exception as exc:
                template_markitdown_summary = {
                    "enabled": True,
                    "ok": False,
                    "error": f"markitdown_template_probe_failed: {str(exc)[:180]}",
                    "issue_codes": ["markitdown_extraction_failed"],
                }
            template_result = fill_template_pptx(
                template_bytes=template_bytes,
                slides=[dict(item) for item in raw_slides_data],
                deck_title=req.title,
                author=req.author,
            )
            project_id = _new_id()
            key = f"projects/{project_id}/pptx/presentation.pptx"
            url = await upload_bytes_to_r2(
                template_result["pptx_bytes"],
                key,
                content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
            diagnostics: List[Dict[str, Any]] = [
                {
                    "attempt": 1,
                    "status": "template_edit_applied",
                    "template_file_url": template_file_url,
                    "replacement_count": int(template_result.get("replacement_count") or 0),
                    "template_slide_count": int(template_result.get("template_slide_count") or 0),
                    "slides_used": int(template_result.get("slides_used") or 0),
                    "template_edit_engine": str(template_result.get("engine") or "unknown"),
                    "template_markitdown_used": bool(template_result.get("markitdown_used")),
                }
            ]
            if template_skill_runtime:
                diagnostics.append(
                    {
                        "attempt": 1,
                        "status": "template_skill_runtime",
                        "runtime": template_skill_runtime,
                    }
                )
            if template_markitdown_summary:
                diagnostics.append(
                    {
                        "attempt": 1,
                        "status": "template_markitdown_probe",
                        "markitdown": template_markitdown_summary,
                    }
                )
            text_render_spec = {
                "slides": [
                    {
                        "slide_id": str(
                            slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}"
                        ),
                        "page_number": idx + 1,
                    }
                    for idx, slide in enumerate(raw_slides_data)
                    if isinstance(slide, dict)
                ]
            }
            text_qa: Dict[str, Any] = {}
            try:
                text_qa = audit_textual_slides([dict(item) for item in raw_slides_data], render_spec=text_render_spec)
            except Exception as exc:
                text_qa = {"error": str(exc)[:220]}

            export_data: Dict[str, Any] = {
                "url": url,
                "skill": "pptx_template_editor",
                "generator_mode": "template_edit",
                "export_channel": export_channel,
                "quality_profile": quality_profile,
                "deck_id": deck_id,
                "attempts": 1,
                "retry_scope": "deck",
                "route_mode": route_policy.mode,
                "render_spec_version": "template-edit-v1",
                "diagnostics": diagnostics,
                "template_edit": {
                    "template_file_url": template_file_url,
                    "replacement_count": int(template_result.get("replacement_count") or 0),
                    "token_keys": list(template_result.get("token_keys") or []),
                    "slides_used": int(template_result.get("slides_used") or 0),
                    "template_slide_count": int(template_result.get("template_slide_count") or 0),
                    "engine": str(template_result.get("engine") or "unknown"),
                    "cleaned_resource_count": int(template_result.get("cleaned_resource_count") or 0),
                    "markitdown_used": bool(template_result.get("markitdown_used")),
                    "markitdown_ok": bool(template_result.get("markitdown_ok")),
                    "markitdown_issue": str(template_result.get("markitdown_issue") or ""),
                    "skill_runtime": template_skill_runtime,
                },
            }
            if text_qa:
                export_data["text_qa"] = text_qa
            if template_markitdown_summary:
                export_data["template_markitdown"] = template_markitdown_summary
            export_data["observability_report"] = {
                "route_mode": route_policy.mode,
                "quality_profile": quality_profile,
                "attempts": 1,
                "generator_mode": "template_edit",
                "export_channel": export_channel,
                "has_visual_qa": False,
                "has_text_qa": bool(text_qa),
                "has_quality_score": False,
                "issue_codes": sorted(
                    {
                        str(item)
                        for item in (
                            text_qa.get("issue_codes")
                            if isinstance(text_qa.get("issue_codes"), list)
                            else []
                        )
                        if str(item).strip()
                    }
                ),
            }
            alerts = _build_export_alerts(
                quality_score=None,
                visual_qa=None,
                diagnostics=diagnostics,
                template_renderer_summary=None,
                text_qa=text_qa,
            )
            if alerts:
                export_data["alerts"] = alerts
                export_data["observability_report"]["alerts"] = alerts
            _persist_ppt_retry_diagnostic(
                {
                    "deck_id": deck_id,
                    "failure_code": None,
                    "failure_detail": None,
                    "retry_scope": "deck",
                    "retry_target_ids": [],
                    "attempt": 1,
                    "idempotency_key": req.idempotency_key,
                    "render_spec_version": "template-edit-v1",
                    "route_mode": route_policy.mode,
                    "quality_score": None,
                    "alert_count": len(alerts),
                    "status": "success",
                    "created_at": _utc_now(),
                }
            )
            _persist_ppt_observability_report(
                {
                    "deck_id": deck_id,
                    "status": "success",
                    "failure_code": None,
                    "failure_detail": None,
                    "route_mode": route_policy.mode,
                    "quality_profile": quality_profile,
                    "attempts": 1,
                    "quality_score": None,
                    "quality_score_threshold": None,
                    "alert_count": len(alerts),
                    "alerts": alerts,
                    "issue_codes": export_data.get("observability_report", {}).get("issue_codes", []),
                    "export_channel": export_channel,
                    "generator_mode": "template_edit",
                    "diagnostics": diagnostics,
                    "created_at": _utc_now(),
                }
            )
            return export_data

        async def _reorchestrate_retry_slides(seed_slides: List[Dict[str, Any]]) -> None:
            nonlocal slides_data
            repaired = await _hydrate_image_assets(
                _apply_visual_orchestration(
                    _apply_skill_planning_to_render_payload(
                        {
                            "title": req.title,
                            "theme": {"palette": effective_palette_key, "style": effective_style_variant},
                            "slides": seed_slides,
                            "template_family": effective_template_family,
                            "template_id": effective_template_family if effective_template_family != "auto" else "",
                            "skill_profile": effective_skill_profile,
                            "hardness_profile": req.hardness_profile,
                            "schema_profile": req.schema_profile,
                            "contract_profile": req.contract_profile,
                            "quality_profile": quality_profile,
                            "svg_mode": req.svg_mode,
                        }
                    )
                )
            )
            repaired_slides = repaired.get("slides")
            if isinstance(repaired_slides, list) and repaired_slides:
                slides_data = repaired_slides

        def _degrade_render_paths_for_retry(
            *,
            seed_slides: List[Dict[str, Any]],
            failure_code: str,
            scope: str,
            scoped_slide_ids: List[str],
        ) -> Dict[str, Any]:
            if not isinstance(seed_slides, list) or not seed_slides:
                return {
                    "applied": False,
                    "failure_code": str(failure_code or ""),
                    "changed_slide_ids": [],
                    "transitions": [],
                }
            target_set = {
                str(item).strip() for item in (scoped_slide_ids or []) if str(item).strip()
            }
            use_target_filter = scope in {"slide", "block"} and bool(target_set)
            changed_slide_ids: List[str] = []
            transitions: List[str] = []
            for idx, slide in enumerate(seed_slides):
                if not isinstance(slide, dict):
                    continue
                slide_id = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}").strip()
                if use_target_filter and slide_id not in target_set:
                    continue
                current_path = str(slide.get("render_path") or "pptxgenjs").strip().lower()
                next_path = compute_render_path_downgrade(
                    current_render_path=current_path,
                    failure_code=failure_code,
                )
                if not next_path:
                    continue
                slide["render_path"] = next_path
                if next_path == "png_fallback":
                    slide["svg_fallback_png"] = True
                changed_slide_ids.append(slide_id)
                transitions.append(f"{slide_id}:{current_path}->{next_path}")
            return {
                "applied": bool(changed_slide_ids),
                "failure_code": str(failure_code or ""),
                "changed_slide_ids": changed_slide_ids,
                "transitions": transitions,
            }

        def _collect_issue_retry_target_slides(gate_issues: List[Any]) -> List[str]:
            ordered: List[str] = []
            seen: set[str] = set()
            for issue in gate_issues or []:
                retry_ids = getattr(issue, "retry_target_ids", None)
                if isinstance(retry_ids, list):
                    for raw in retry_ids:
                        sid = str(raw or "").strip()
                        if not sid or sid.lower() == "deck" or sid in seen:
                            continue
                        seen.add(sid)
                        ordered.append(sid)
                sid = str(getattr(issue, "slide_id", "") or "").strip()
                if sid and sid.lower() != "deck" and sid not in seen:
                    seen.add(sid)
                    ordered.append(sid)
            return ordered

        requested_mode = str(req.generator_mode or "auto").strip().lower()
        if requested_mode == "legacy" and allow_legacy_mode:
            generator_mode = "legacy"
        elif requested_mode == "legacy" and not allow_legacy_mode:
            logger.warning(
                "[ppt_service] requested legacy mode but PPT_ALLOW_LEGACY_MODE=false; forcing official"
            )
            generator_mode = "official"
        elif requested_mode == "official":
            generator_mode = "official"
        else:
            if env_generator_mode == "legacy" and allow_legacy_mode:
                generator_mode = "legacy"
            else:
                generator_mode = "official"

        render_spec_version = "v1"
        diagnostics: List[Dict[str, Any]] = []
        attempt = 1
        export_result: Dict[str, Any] | None = None
        base_render_spec: Dict[str, Any] | None = None
        final_content_issues: List[Any] = []
        final_layout_issues: List[Any] = []
        final_visual_gate_issues: List[Any] = []
        final_quality_score = None
        final_visual_audit: Dict[str, Any] = {}
        final_text_qa: Dict[str, Any] = {}
        final_png_bytes_list: List[bytes] = []

        while True:
            try:
                effective_visual_preset = (
                    "tech_cinematic" if str(req.visual_preset or "auto").strip().lower() == "auto" else str(req.visual_preset)
                )
                current_result = export_minimax_pptx(
                    slides=slides_data,
                    title=req.title,
                    author=req.author,
                    render_channel=export_channel,
                    route_mode=route_policy.mode,
                    generator_mode=generator_mode,
                    enable_legacy_fallback=enable_legacy_fallback,
                    style_variant=effective_style_variant,
                    palette_key=effective_palette_key,
                    verbatim_content=bool(req.verbatim_content),
                    deck_id=deck_id,
                    retry_scope=retry_scope,
                    target_slide_ids=target_slide_ids,
                    target_block_ids=target_block_ids,
                    retry_hint=retry_hint,
                    idempotency_key=req.idempotency_key or "",
                    original_style=bool(req.original_style),
                    disable_local_style_rewrite=bool(req.disable_local_style_rewrite),
                    visual_priority=bool(req.visual_priority),
                    visual_preset=effective_visual_preset,
                    visual_density=str(req.visual_density or "balanced"),
                    constraint_hardness=requested_constraint_hardness,
                    svg_mode=str(req.svg_mode or "on"),
                    template_family=str(effective_template_family or "auto"),
                    template_id=str(effective_template_family if effective_template_family != "auto" else ""),
                    skill_profile=str(effective_skill_profile or ""),
                    hardness_profile=str(req.hardness_profile or ""),
                    schema_profile=str(req.schema_profile or ""),
                    contract_profile=str(req.contract_profile or ""),
                    quality_profile=quality_profile,
                    enforce_visual_contract=bool(req.enforce_visual_contract),
                    timeout=180,
                )
                generator_mode = str(current_result.get("generator_mode") or generator_mode)
                partial_result_is_full_deck = bool(current_result.get("is_full_deck"))
                if retry_scope in {"slide", "block"} and not partial_result_is_full_deck:
                    # Partial retry may return a patch-like PPTX (subset of slides).
                    # Always consolidate to full deck before quality gates and delivery.
                    current_result = export_minimax_pptx(
                        slides=slides_data,
                        title=req.title,
                        author=req.author,
                        render_channel=export_channel,
                        route_mode=route_policy.mode,
                        generator_mode=generator_mode,
                        enable_legacy_fallback=enable_legacy_fallback,
                        style_variant=effective_style_variant,
                        palette_key=effective_palette_key,
                        verbatim_content=bool(req.verbatim_content),
                        deck_id=deck_id,
                        retry_scope="deck",
                        target_slide_ids=[],
                        target_block_ids=[],
                        retry_hint=f"{str(retry_hint or '').strip()} | full_deck_finalize"[:1500],
                        idempotency_key=req.idempotency_key or "",
                        original_style=bool(req.original_style),
                        disable_local_style_rewrite=bool(req.disable_local_style_rewrite),
                        visual_priority=bool(req.visual_priority),
                        visual_preset=effective_visual_preset,
                        visual_density=str(req.visual_density or "balanced"),
                        constraint_hardness=requested_constraint_hardness,
                        svg_mode=str(req.svg_mode or "on"),
                        template_family=str(effective_template_family or "auto"),
                        template_id=str(effective_template_family if effective_template_family != "auto" else ""),
                        skill_profile=str(effective_skill_profile or ""),
                        hardness_profile=str(req.hardness_profile or ""),
                        schema_profile=str(req.schema_profile or ""),
                        contract_profile=str(req.contract_profile or ""),
                        quality_profile=quality_profile,
                        enforce_visual_contract=bool(req.enforce_visual_contract),
                        timeout=180,
                    )
                    generator_mode = str(current_result.get("generator_mode") or generator_mode)
                    partial_result_is_full_deck = bool(current_result.get("is_full_deck", True))
                    retry_scope = "deck"
                    target_slide_ids = []
                    target_block_ids = []
                elif retry_scope in {"slide", "block"} and partial_result_is_full_deck:
                    # Phase 20: modular per-slide retry path already compiles back to
                    # a full deck, so no extra full-deck finalize pass is required.
                    retry_scope = "deck"
                    target_slide_ids = []
                    target_block_ids = []

                if base_render_spec is None:
                    base_render_spec = current_result.get("render_spec") or {}
                elif (
                    partial_retry_enabled
                    and retry_scope in {"slide", "block"}
                    and not partial_result_is_full_deck
                ):
                    current_patch = current_result.get("render_spec") or {}
                    current_result["render_spec"] = merge_render_spec(base_render_spec, current_patch)
                    base_render_spec = current_result.get("render_spec") or {}

                content_gate = validate_deck(
                    (current_result.get("input_payload") or {}).get("slides") or slides_data,
                    profile=quality_profile,
                )
                layout_gate_source: Dict[str, Any] = {
                    "slides": (current_result.get("input_payload") or {}).get("slides") or slides_data
                }
                layout_gate = validate_layout_diversity(
                    layout_gate_source,
                    profile=quality_profile,
                )
                content_issues = list(content_gate.issues)
                layout_issues = list(layout_gate.issues)
                relaxed_codes: set[str] = set()
                if route_policy.mode == "fast" or quality_profile == "lenient_draft":
                    relaxed_codes = {
                        "layout_homogeneous",
                        "layout_top2_homogeneous",
                        "layout_adjacent_repeat",
                        "template_family_homogeneous",
                        "template_family_top2_homogeneous",
                        "placeholder_kpi_data",
                        "placeholder_pollution",
                    }
                if relaxed_codes:
                    content_issues = [
                        issue for issue in content_issues if str(getattr(issue, "code", "")).strip() not in relaxed_codes
                    ]
                    layout_issues = [
                        issue for issue in layout_issues if str(getattr(issue, "code", "")).strip() not in relaxed_codes
                    ]
                gate_issues = [*content_issues, *layout_issues]
                score_result = score_deck_quality(
                    slides=(current_result.get("input_payload") or {}).get("slides") or slides_data,
                    render_spec=layout_gate_source,
                    profile=quality_profile,
                    content_issues=content_issues,
                    layout_issues=layout_issues,
                )
                effective_threshold = max(
                    1.0,
                    min(100.0, float(score_result.threshold) + float(route_policy.quality_threshold_offset)),
                )
                score_passed = bool(score_result.passed) and float(score_result.score) >= effective_threshold
                final_content_issues = list(content_issues)
                final_layout_issues = list(layout_issues)
                final_quality_score = score_result

                if (not gate_issues) and ((not route_policy.require_weighted_quality_score) or score_passed):
                    visual_audit: Dict[str, Any] = {}
                    visual_gate_issues: List[Any] = []
                    png_bytes_list: List[bytes] = []
                    if route_policy.run_post_render_visual_qa and route_policy.force_rasterization:
                        try:
                            png_bytes_list = rasterize_pptx_bytes_to_png_bytes(current_result["pptx_bytes"])
                            if not png_bytes_list:
                                raise RuntimeError("native_rasterization_no_output")
                            visual_audit = await audit_rendered_slides(
                                png_bytes_list,
                                deck_title=req.title,
                                route_mode=route_policy.mode,
                            )
                            score_result = score_deck_quality(
                                slides=(current_result.get("input_payload") or {}).get("slides") or slides_data,
                                render_spec=layout_gate_source,
                                profile=quality_profile,
                                content_issues=content_gate.issues,
                                layout_issues=layout_gate.issues,
                                visual_audit=visual_audit,
                            )
                            visual_gate = validate_visual_audit(
                                visual_audit=visual_audit,
                                slides=(current_result.get("input_payload") or {}).get("slides") or slides_data,
                                profile=quality_profile,
                                layout_diversity_ok=(len(layout_issues) == 0),
                            )
                            visual_gate_issues = list(visual_gate.issues)
                            gate_issues = [*content_issues, *layout_issues, *visual_gate_issues]
                            effective_threshold = max(
                                1.0,
                                min(100.0, float(score_result.threshold) + float(route_policy.quality_threshold_offset)),
                            )
                            score_passed = (
                                bool(score_result.passed)
                                and float(score_result.score) >= effective_threshold
                                and len(visual_gate_issues) == 0
                            )
                            final_quality_score = score_result
                            final_visual_audit = visual_audit
                            final_visual_gate_issues = list(visual_gate_issues)
                        except Exception as qa_exc:
                            visual_audit = {"error": str(qa_exc)[:300]}
                            final_visual_audit = visual_audit
                            raise MiniMaxExportError(
                                message="PPT native rasterization failed",
                                classification=classify_failure("native_rasterization_failed"),
                                detail=str(qa_exc),
                            ) from qa_exc
                    if gate_issues:
                        if partial_retry_enabled:
                            issue_slide_targets = _collect_issue_retry_target_slides(gate_issues)
                            if issue_slide_targets:
                                retry_scope = "slide"
                                target_slide_ids = issue_slide_targets
                                target_block_ids = []
                        failure_code = "schema_invalid"
                        failure_detail = "; ".join(
                            f"{issue.slide_id}:{issue.code}" for issue in gate_issues[:10]
                        )
                        classification = classify_failure(failure_code)
                        decision = make_retry_decision(
                            code=classification.code,
                            attempt=attempt,
                            max_attempts=min(max_retry_attempts, classification.max_attempts),
                            base_delay_ms=classification.base_delay_ms,
                        )
                        diagnostics.append(
                            {
                                "attempt": attempt,
                                "status": "visual_gate_failed",
                                "failure_code": classification.code,
                                "failure_detail": failure_detail,
                                "score": score_result.score,
                                "score_threshold": effective_threshold,
                                "route_mode": route_policy.mode,
                                "visual_audit": visual_audit or None,
                                "generator_mode": generator_mode,
                                "retry_scope": retry_scope,
                            }
                        )
                        _persist_ppt_retry_diagnostic(
                            {
                                "deck_id": deck_id,
                                "failure_code": classification.code,
                                "failure_detail": failure_detail,
                                "retry_scope": retry_scope,
                                "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                                "attempt": attempt,
                                "idempotency_key": req.idempotency_key,
                                "export_channel": export_channel,
                                "quality_profile": quality_profile,
                                "route_mode": route_policy.mode,
                                "quality_score": float(score_result.score),
                                "quality_score_threshold": effective_threshold,
                                "render_spec_version": render_spec_version,
                                "status": "visual_gate_failed",
                                "created_at": _utc_now(),
                            }
                        )
                        if (not retry_enabled) or (not decision.should_retry):
                            _persist_ppt_observability_report(
                                {
                                    "deck_id": deck_id,
                                    "status": "failed",
                                    "failure_code": classification.code,
                                    "failure_detail": failure_detail[:1200],
                                    "route_mode": route_policy.mode,
                                    "quality_profile": quality_profile,
                                    "attempts": attempt,
                                    "quality_score": float(score_result.score),
                                    "quality_score_threshold": effective_threshold,
                                    "export_channel": export_channel,
                                    "generator_mode": generator_mode,
                                    "diagnostics": diagnostics[-20:],
                                    "created_at": _utc_now(),
                                }
                            )
                            raise MiniMaxExportError(
                                message=f"PPT visual quality gate failed: {failure_detail}",
                                classification=classification,
                                detail=failure_detail,
                            )
                        downgrade_info = _degrade_render_paths_for_retry(
                            seed_slides=slides_data,
                            failure_code=classification.code,
                            scope=retry_scope,
                            scoped_slide_ids=target_slide_ids,
                        )
                        if downgrade_info["applied"]:
                            diagnostics.append(
                                {
                                    "attempt": attempt,
                                    "status": "render_path_downgrade",
                                    "failure_code": classification.code,
                                    "retry_scope": retry_scope,
                                    "changed_slide_ids": downgrade_info["changed_slide_ids"],
                                    "transitions": downgrade_info["transitions"],
                                }
                            )
                        retry_hint = build_retry_hint(
                            failure_code=classification.code,
                            failure_detail=failure_detail,
                            attempt=attempt,
                            retry_scope=retry_scope,
                            target_ids=target_block_ids if retry_scope == "block" else target_slide_ids,
                        )
                        await asyncio.sleep(decision.delay_ms / 1000.0)
                        attempt += 1
                        continue

                    if route_policy.require_weighted_quality_score and (not score_passed):
                        failure_code = "quality_score_low"
                        failure_detail = (
                            f"weighted_score={score_result.score:.1f} < threshold={effective_threshold:.1f}"
                        )
                        classification = classify_failure(failure_code)
                        decision = make_retry_decision(
                            code=classification.code,
                            attempt=attempt,
                            max_attempts=min(max_retry_attempts, classification.max_attempts),
                            base_delay_ms=classification.base_delay_ms,
                        )
                        diagnostics.append(
                            {
                                "attempt": attempt,
                                "status": "quality_score_failed",
                                "failure_code": classification.code,
                                "failure_detail": failure_detail,
                                "score": score_result.score,
                                "score_threshold": effective_threshold,
                                "route_mode": route_policy.mode,
                                "visual_audit": visual_audit or None,
                                "generator_mode": generator_mode,
                                "retry_scope": retry_scope,
                            }
                        )
                        _persist_ppt_retry_diagnostic(
                            {
                                "deck_id": deck_id,
                                "failure_code": classification.code,
                                "failure_detail": failure_detail,
                                "retry_scope": retry_scope,
                                "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                                "attempt": attempt,
                                "idempotency_key": req.idempotency_key,
                                "export_channel": export_channel,
                                "quality_profile": quality_profile,
                                "route_mode": route_policy.mode,
                                "quality_score": float(score_result.score),
                                "quality_score_threshold": effective_threshold,
                                "render_spec_version": render_spec_version,
                                "status": "quality_score_failed",
                                "created_at": _utc_now(),
                            }
                        )
                        if (not retry_enabled) or (not decision.should_retry):
                            _persist_ppt_observability_report(
                                {
                                    "deck_id": deck_id,
                                    "status": "failed",
                                    "failure_code": classification.code,
                                    "failure_detail": failure_detail[:1200],
                                    "route_mode": route_policy.mode,
                                    "quality_profile": quality_profile,
                                    "attempts": attempt,
                                    "quality_score": float(score_result.score),
                                    "quality_score_threshold": effective_threshold,
                                    "export_channel": export_channel,
                                    "generator_mode": generator_mode,
                                    "diagnostics": diagnostics[-20:],
                                    "created_at": _utc_now(),
                                }
                            )
                            raise MiniMaxExportError(
                                message=f"PPT weighted quality score failed: {failure_detail}",
                                classification=classification,
                                detail=failure_detail,
                            )
                        downgrade_info = _degrade_render_paths_for_retry(
                            seed_slides=slides_data,
                            failure_code=classification.code,
                            scope=retry_scope,
                            scoped_slide_ids=target_slide_ids,
                        )
                        if downgrade_info["applied"]:
                            diagnostics.append(
                                {
                                    "attempt": attempt,
                                    "status": "render_path_downgrade",
                                    "failure_code": classification.code,
                                    "retry_scope": retry_scope,
                                    "changed_slide_ids": downgrade_info["changed_slide_ids"],
                                    "transitions": downgrade_info["transitions"],
                                }
                            )
                        retry_hint = build_retry_hint(
                            failure_code=classification.code,
                            failure_detail=failure_detail,
                            attempt=attempt,
                            retry_scope=retry_scope,
                            target_ids=target_block_ids if retry_scope == "block" else target_slide_ids,
                        )
                        await asyncio.sleep(decision.delay_ms / 1000.0)
                        attempt += 1
                        continue

                    export_result = current_result
                    final_png_bytes_list = png_bytes_list
                    diagnostics.append(
                        {
                            "attempt": attempt,
                            "status": "success",
                            "export_channel": export_channel,
                            "generator_mode": generator_mode,
                            "retry_scope": retry_scope,
                            "route_mode": route_policy.mode,
                            "quality_profile": quality_profile,
                            "score": float(score_result.score),
                            "score_threshold": effective_threshold,
                            "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                        }
                    )
                    break

                issue_codes = {issue.code for issue in gate_issues}
                failure_code = (
                    "encoding_invalid"
                    if "encoding_invalid" in issue_codes
                    else (
                        "layout_homogeneous"
                        if (
                            "layout_homogeneous" in issue_codes
                            or "layout_adjacent_repeat" in issue_codes
                            or "template_family_homogeneous" in issue_codes
                            or "template_family_top2_homogeneous" in issue_codes
                            or "template_family_switch_frequent" in issue_codes
                            or "template_family_abab_repeat" in issue_codes
                        )
                        else "schema_invalid"
                    )
                )
                failure_detail = "; ".join(
                    f"{issue.slide_id}:{issue.code}" for issue in gate_issues[:10]
                )
                classification = classify_failure(failure_code)
                decision = make_retry_decision(
                    code=classification.code,
                    attempt=attempt,
                    max_attempts=min(max_retry_attempts, classification.max_attempts),
                    base_delay_ms=classification.base_delay_ms,
                )
                diagnostics.append(
                    {
                        "attempt": attempt,
                        "status": "quality_gate_failed",
                        "export_channel": export_channel,
                        "failure_code": classification.code,
                        "failure_detail": failure_detail,
                        "quality_profile": quality_profile,
                        "generator_mode": generator_mode,
                        "retry_scope": retry_scope,
                        "route_mode": route_policy.mode,
                        "score": float(score_result.score),
                        "score_threshold": effective_threshold,
                    }
                )
                _persist_ppt_retry_diagnostic(
                    {
                        "deck_id": deck_id,
                        "failure_code": classification.code,
                        "failure_detail": failure_detail,
                        "retry_scope": retry_scope,
                        "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                        "attempt": attempt,
                        "idempotency_key": req.idempotency_key,
                        "export_channel": export_channel,
                        "quality_profile": quality_profile,
                        "render_spec_version": render_spec_version,
                        "route_mode": route_policy.mode,
                        "quality_score": float(score_result.score),
                        "quality_score_threshold": effective_threshold,
                        "status": "quality_gate_failed",
                        "created_at": _utc_now(),
                    }
                )
                if (not retry_enabled) or (not decision.should_retry):
                    _persist_ppt_observability_report(
                        {
                            "deck_id": deck_id,
                            "status": "failed",
                            "failure_code": classification.code,
                            "failure_detail": failure_detail[:1200],
                            "route_mode": route_policy.mode,
                            "quality_profile": quality_profile,
                            "attempts": attempt,
                            "quality_score": float(score_result.score),
                            "quality_score_threshold": effective_threshold,
                            "export_channel": export_channel,
                            "generator_mode": generator_mode,
                            "diagnostics": diagnostics[-20:],
                            "created_at": _utc_now(),
                        }
                    )
                    raise MiniMaxExportError(
                        message=f"PPT quality gate failed: {failure_detail}",
                        classification=classification,
                        detail=failure_detail,
                    )

                if partial_retry_enabled and gate_issues and failure_code != "layout_homogeneous":
                    issue_slide_targets = _collect_issue_retry_target_slides(gate_issues)
                    if issue_slide_targets:
                        retry_scope = "slide"
                        target_slide_ids = issue_slide_targets
                        target_block_ids = []

                seed_slides = (current_result.get("input_payload") or {}).get("slides")
                if not isinstance(seed_slides, list) or not seed_slides:
                    seed_slides = slides_data
                downgrade_info = _degrade_render_paths_for_retry(
                    seed_slides=seed_slides,
                    failure_code=classification.code,
                    scope=retry_scope,
                    scoped_slide_ids=target_slide_ids,
                )
                if downgrade_info["applied"]:
                    diagnostics.append(
                        {
                            "attempt": attempt,
                            "status": "render_path_downgrade",
                            "failure_code": classification.code,
                            "retry_scope": retry_scope,
                            "changed_slide_ids": downgrade_info["changed_slide_ids"],
                            "transitions": downgrade_info["transitions"],
                        }
                    )
                retry_hint = build_retry_hint(
                    failure_code=classification.code,
                    failure_detail=failure_detail,
                    attempt=attempt,
                    retry_scope=retry_scope,
                    target_ids=target_block_ids if retry_scope == "block" else target_slide_ids,
                )
                await _reorchestrate_retry_slides(seed_slides)
                await asyncio.sleep(decision.delay_ms / 1000.0)
                attempt += 1
            except MiniMaxExportError as exc:
                classification = exc.classification
                schema_downgrade_applied = False
                if classification.code == "schema_invalid":
                    schema_targets = _extract_slide_targets_from_schema_error(exc.detail, slides_data)
                    if schema_targets:
                        retry_scope = "slide"
                        target_slide_ids = schema_targets
                        target_block_ids = []
                        downgrade_info = _degrade_render_paths_for_retry(
                            seed_slides=slides_data,
                            failure_code=classification.code,
                            scope=retry_scope,
                            scoped_slide_ids=target_slide_ids,
                        )
                        if downgrade_info["applied"]:
                            schema_downgrade_applied = True
                            diagnostics.append(
                                {
                                    "attempt": attempt,
                                    "status": "render_path_downgrade",
                                    "failure_code": classification.code,
                                    "retry_scope": retry_scope,
                                    "changed_slide_ids": downgrade_info["changed_slide_ids"],
                                    "transitions": downgrade_info["transitions"],
                                }
                            )
                        # Re-apply visual orchestration before retrying only failed pages.
                        await _reorchestrate_retry_slides(slides_data)
                decision = make_retry_decision(
                    code=classification.code,
                    attempt=attempt,
                    max_attempts=min(max_retry_attempts, classification.max_attempts),
                    base_delay_ms=classification.base_delay_ms,
                )
                diagnostics.append(
                    {
                        "attempt": attempt,
                        "status": "failed",
                        "failure_code": classification.code,
                        "failure_detail": exc.detail[:800],
                        "generator_mode": generator_mode,
                        "retry_scope": retry_scope,
                        "route_mode": route_policy.mode,
                        "retryable": classification.retryable,
                    }
                )
                _persist_ppt_retry_diagnostic(
                    {
                        "deck_id": deck_id,
                        "failure_code": classification.code,
                        "failure_detail": exc.detail[:1200],
                        "retry_scope": retry_scope,
                        "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                        "attempt": attempt,
                        "idempotency_key": req.idempotency_key,
                        "export_channel": export_channel,
                        "quality_profile": quality_profile,
                        "render_spec_version": render_spec_version,
                        "route_mode": route_policy.mode,
                        "status": "failed",
                        "created_at": _utc_now(),
                    }
                )

                if (not retry_enabled) or (not decision.should_retry):
                    _persist_ppt_observability_report(
                        {
                            "deck_id": deck_id,
                            "status": "failed",
                            "failure_code": classification.code,
                            "failure_detail": str(exc.detail or "")[:1200],
                            "route_mode": route_policy.mode,
                            "quality_profile": quality_profile,
                            "attempts": attempt,
                            "export_channel": export_channel,
                            "generator_mode": generator_mode,
                            "diagnostics": diagnostics[-20:],
                            "created_at": _utc_now(),
                        }
                    )
                    raise

                if not schema_downgrade_applied:
                    downgrade_info = _degrade_render_paths_for_retry(
                        seed_slides=slides_data,
                        failure_code=classification.code,
                        scope=retry_scope,
                        scoped_slide_ids=target_slide_ids,
                    )
                    if downgrade_info["applied"]:
                        diagnostics.append(
                            {
                                "attempt": attempt,
                                "status": "render_path_downgrade",
                                "failure_code": classification.code,
                                "retry_scope": retry_scope,
                                "changed_slide_ids": downgrade_info["changed_slide_ids"],
                                "transitions": downgrade_info["transitions"],
                            }
                        )
                retry_hint = build_retry_hint(
                    failure_code=classification.code,
                    failure_detail=exc.detail,
                    attempt=attempt,
                    retry_scope=retry_scope,
                    target_ids=target_block_ids if retry_scope == "block" else target_slide_ids,
                )
                await asyncio.sleep(decision.delay_ms / 1000.0)
                attempt += 1
            except Exception as exc:
                classification = classify_failure(exc)
                decision = make_retry_decision(
                    code=classification.code,
                    attempt=attempt,
                    max_attempts=min(max_retry_attempts, classification.max_attempts),
                    base_delay_ms=classification.base_delay_ms,
                )
                failure_detail = str(exc)
                diagnostics.append(
                    {
                        "attempt": attempt,
                        "status": "failed",
                        "failure_code": classification.code,
                        "failure_detail": failure_detail[:800],
                        "generator_mode": generator_mode,
                        "retry_scope": retry_scope,
                        "route_mode": route_policy.mode,
                        "retryable": classification.retryable,
                    }
                )
                _persist_ppt_retry_diagnostic(
                    {
                        "deck_id": deck_id,
                        "failure_code": classification.code,
                        "failure_detail": failure_detail[:1200],
                        "retry_scope": retry_scope,
                        "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                        "attempt": attempt,
                        "idempotency_key": req.idempotency_key,
                        "render_spec_version": render_spec_version,
                        "route_mode": route_policy.mode,
                        "status": "failed",
                        "created_at": _utc_now(),
                    }
                )
                if (not retry_enabled) or (not decision.should_retry):
                    _persist_ppt_observability_report(
                        {
                            "deck_id": deck_id,
                            "status": "failed",
                            "failure_code": classification.code,
                            "failure_detail": failure_detail[:1200],
                            "route_mode": route_policy.mode,
                            "quality_profile": quality_profile,
                            "attempts": attempt,
                            "export_channel": export_channel,
                            "generator_mode": generator_mode,
                            "diagnostics": diagnostics[-20:],
                            "created_at": _utc_now(),
                        }
                    )
                    raise
                downgrade_info = _degrade_render_paths_for_retry(
                    seed_slides=slides_data,
                    failure_code=classification.code,
                    scope=retry_scope,
                    scoped_slide_ids=target_slide_ids,
                )
                if downgrade_info["applied"]:
                    diagnostics.append(
                        {
                            "attempt": attempt,
                            "status": "render_path_downgrade",
                            "failure_code": classification.code,
                            "retry_scope": retry_scope,
                            "changed_slide_ids": downgrade_info["changed_slide_ids"],
                            "transitions": downgrade_info["transitions"],
                        }
                    )
                retry_hint = build_retry_hint(
                    failure_code=classification.code,
                    failure_detail=failure_detail,
                    attempt=attempt,
                    retry_scope=retry_scope,
                    target_ids=target_block_ids if retry_scope == "block" else target_slide_ids,
                )
                await asyncio.sleep(decision.delay_ms / 1000.0)
                attempt += 1

        if export_result is None:
            _persist_ppt_observability_report(
                {
                    "deck_id": deck_id,
                    "status": "failed",
                    "failure_code": "export_result_missing",
                    "failure_detail": "MiniMax export completed without result",
                    "route_mode": route_policy.mode,
                    "quality_profile": quality_profile,
                    "attempts": attempt,
                    "export_channel": export_channel,
                    "generator_mode": generator_mode,
                    "diagnostics": diagnostics[-20:],
                    "created_at": _utc_now(),
                }
            )
            raise RuntimeError("MiniMax export completed without result")

        project_id = _new_id()
        key = f"projects/{project_id}/pptx/presentation.pptx"
        url = await upload_bytes_to_r2(
            export_result["pptx_bytes"],
            key,
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        export_data: Dict[str, Any] = {"url": url, "skill": skill}
        generator_meta = export_result.get("generator_meta") or {}
        if generator_meta:
            export_data["generator_meta"] = generator_meta
        export_data["style_variant"] = effective_style_variant
        export_data["palette_key"] = effective_palette_key
        export_data["template_family"] = effective_template_family
        export_data["skill_profile"] = effective_skill_profile
        layer1_runtime = layer1_design.get("runtime") if isinstance(layer1_design.get("runtime"), dict) else {}
        if layer1_runtime:
            export_data["layer1_skill_runtime"] = layer1_runtime
        export_data["generator_mode"] = export_result.get("generator_mode", generator_mode)
        export_data["export_channel"] = export_result.get("render_channel", export_channel)
        export_data["quality_profile"] = quality_profile
        export_data["deck_id"] = deck_id
        export_data["attempts"] = attempt
        export_data["retry_scope"] = retry_scope
        export_data["route_mode"] = route_policy.mode
        export_data["render_spec_version"] = render_spec_version
        export_data["diagnostics"] = diagnostics
        render_spec = export_result.get("render_spec")
        if not isinstance(render_spec, dict):
            render_spec = {}
        template_renderer_summary = render_spec.get("template_renderer_summary")
        if not isinstance(template_renderer_summary, dict):
            template_renderer_summary = {}
        try:
            final_text_qa = audit_textual_slides(
                (export_result.get("input_payload") or {}).get("slides") or slides_data,
                render_spec=render_spec,
            )
        except Exception as exc:
            final_text_qa = {"error": str(exc)[:220]}
        markitdown_enabled = str(
            os.getenv("PPT_TEXT_QA_MARKITDOWN_ENABLED", "true")
        ).strip().lower() not in {"0", "false", "no", "off"}
        if markitdown_enabled:
            markitdown_timeout_sec_raw = str(
                os.getenv("PPT_TEXT_QA_MARKITDOWN_TIMEOUT_SEC", "25")
            ).strip()
            try:
                markitdown_timeout_sec = max(5, min(90, int(markitdown_timeout_sec_raw)))
            except Exception:
                markitdown_timeout_sec = 25
            try:
                markitdown_summary = await asyncio.to_thread(
                    run_markitdown_text_qa,
                    export_result["pptx_bytes"],
                    timeout_sec=markitdown_timeout_sec,
                )
            except Exception as exc:
                markitdown_summary = {
                    "enabled": True,
                    "ok": False,
                    "error": str(exc)[:220],
                    "issue_codes": ["markitdown_extraction_failed"],
                }
            if not isinstance(final_text_qa, dict):
                final_text_qa = {}
            final_text_qa["markitdown"] = markitdown_summary
            text_issue_codes = (
                final_text_qa.get("issue_codes")
                if isinstance(final_text_qa.get("issue_codes"), list)
                else []
            )
            md_issue_codes = (
                markitdown_summary.get("issue_codes")
                if isinstance(markitdown_summary.get("issue_codes"), list)
                else []
            )
            if md_issue_codes:
                final_text_qa["issue_codes"] = sorted(
                    {
                        str(item).strip()
                        for item in [*text_issue_codes, *md_issue_codes]
                        if str(item).strip()
                    }
                )
        final_contract_slides = []
        for idx, slide in enumerate((export_result.get("input_payload") or {}).get("slides") or []):
            if not isinstance(slide, dict):
                continue
            final_contract_slides.append(
                {
                    "index": idx,
                    "slide_id": str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}"),
                    "slide_type": str(slide.get("slide_type") or slide.get("type") or "").strip().lower(),
                    "layout_grid": str(slide.get("layout_grid") or slide.get("layout") or "").strip().lower(),
                    "template_family": str(
                        slide.get("template_family") or slide.get("template_id") or ""
                    ).strip().lower(),
                }
            )
        if final_contract_slides:
            export_data["final_slide_contract"] = final_contract_slides

        slide_image_urls: List[str] = []
        png_bytes_list: List[bytes] = list(final_png_bytes_list or [])
        try:
            if (not png_bytes_list) and route_policy.force_rasterization:
                png_bytes_list = rasterize_pptx_bytes_to_png_bytes(export_result["pptx_bytes"])
            for idx, png_bytes in enumerate(png_bytes_list):
                image_url = await upload_bytes_to_r2(
                    png_bytes,
                    key=f"projects/{project_id}/slides/slide_{idx + 1:03d}.png",
                    content_type="image/png",
                )
                slide_image_urls.append(image_url)
        except Exception as exc:
            logger.warning("[ppt_service] ppt rasterize skipped: %s", exc)

        if route_policy.run_post_render_visual_qa and not final_visual_audit:
            try:
                if not png_bytes_list:
                    png_bytes_list = rasterize_pptx_bytes_to_png_bytes(export_result["pptx_bytes"])
                final_visual_audit = await audit_rendered_slides(
                    png_bytes_list,
                    deck_title=req.title,
                    route_mode=route_policy.mode,
                )
            except Exception as exc:
                final_visual_audit = {"error": str(exc)[:300]}

        if final_quality_score is not None and final_visual_audit:
            final_quality_score = score_deck_quality(
                slides=(export_result.get("input_payload") or {}).get("slides") or slides_data,
                render_spec=render_spec,
                profile=quality_profile,
                content_issues=[*final_content_issues],
                layout_issues=[*final_layout_issues],
                visual_audit=final_visual_audit,
            )

        if final_quality_score is not None:
            effective_threshold = max(
                1.0,
                min(100.0, float(final_quality_score.threshold) + float(route_policy.quality_threshold_offset)),
            )
            effective_warn_threshold = max(
                1.0,
                min(100.0, float(final_quality_score.warn_threshold) + float(route_policy.warn_threshold_offset)),
            )
            export_data["quality_score"] = {
                "score": float(final_quality_score.score),
                "threshold": effective_threshold,
                "warn_threshold": effective_warn_threshold,
                "passed": bool(final_quality_score.score >= effective_threshold and final_quality_score.passed),
                "dimensions": final_quality_score.dimensions,
                "issue_counts": final_quality_score.issue_counts,
                "diagnostics": final_quality_score.diagnostics,
            }
        if final_visual_audit:
            export_data["visual_qa"] = final_visual_audit
        if final_text_qa:
            export_data["text_qa"] = final_text_qa
        export_data["observability_report"] = {
            "route_mode": route_policy.mode,
            "quality_profile": quality_profile,
            "strict_quality_mode": bool(strict_quality_mode),
            "attempts": attempt,
            "generator_mode": export_result.get("generator_mode", generator_mode),
            "export_channel": export_result.get("render_channel", export_channel),
            "has_visual_qa": bool(final_visual_audit),
            "has_text_qa": bool(final_text_qa),
            "has_quality_score": bool(final_quality_score),
            "issue_codes": sorted(
                {
                    str(issue.code)
                    for issue in [*final_content_issues, *final_layout_issues, *final_visual_gate_issues]
                    if getattr(issue, "code", None)
                }
            ),
        }
        if template_renderer_summary:
            export_data["observability_report"]["template_renderer_summary"] = template_renderer_summary
        if final_text_qa:
            export_data["observability_report"]["text_qa"] = final_text_qa
            text_issue_codes = final_text_qa.get("issue_codes") if isinstance(final_text_qa.get("issue_codes"), list) else []
            if text_issue_codes:
                existing_issue_codes = export_data["observability_report"].get("issue_codes")
                if not isinstance(existing_issue_codes, list):
                    existing_issue_codes = []
                export_data["observability_report"]["issue_codes"] = sorted(
                    {str(item) for item in [*existing_issue_codes, *text_issue_codes] if str(item).strip()}
                )
        alerts = _build_export_alerts(
            quality_score=export_data.get("quality_score") if isinstance(export_data.get("quality_score"), dict) else None,
            visual_qa=final_visual_audit,
            diagnostics=diagnostics,
            template_renderer_summary=template_renderer_summary,
            text_qa=final_text_qa,
        )
        if alerts:
            export_data["alerts"] = alerts
            export_data["observability_report"]["alerts"] = alerts
        strict_blockers = (
            _collect_strict_quality_blockers(
                alerts=alerts,
                generator_meta=generator_meta if isinstance(generator_meta, dict) else {},
                template_renderer_summary=template_renderer_summary,
                text_qa=final_text_qa,
            )
            if strict_quality_mode
            else []
        )
        if strict_blockers:
            existing_alert_codes = {
                str(item.get("code") or "").strip().lower()
                for item in alerts
                if isinstance(item, dict)
            }
            for blocker in strict_blockers:
                code = str(blocker.get("code") or "").strip().lower()
                if code and code not in existing_alert_codes:
                    alerts.append(blocker)
                    existing_alert_codes.add(code)
            export_data["alerts"] = alerts
            export_data["observability_report"]["alerts"] = alerts
            export_data["observability_report"]["strict_blockers"] = strict_blockers
        if slide_image_urls:
            export_data["slide_image_urls"] = slide_image_urls
            export_data["video_mode"] = "ppt_image_slideshow"
            export_data["video_slides"] = _build_image_video_slides(slide_image_urls, slides_data)
            export_data["video_slide_count"] = len(slide_image_urls)

        if isinstance(render_spec, dict) and not slide_image_urls:
            video_slides = render_spec.get("slides")
            if isinstance(video_slides, list) and video_slides:
                export_data["video_mode"] = render_spec.get("mode", "minimax_presentation")
                export_data["video_slides"] = video_slides
                export_data["video_slide_count"] = len(video_slides)

        persisted_diagnostics = diagnostics[-20:]
        if template_renderer_summary:
            persisted_diagnostics = [
                *persisted_diagnostics,
                {
                    "status": "template_renderer_summary",
                    "summary": template_renderer_summary,
                },
            ][-20:]
        if final_text_qa:
            persisted_diagnostics = [
                *persisted_diagnostics,
                {
                    "status": "text_qa_summary",
                    "summary": final_text_qa,
                },
            ][-20:]
        if strict_blockers:
            persisted_diagnostics = [
                *persisted_diagnostics,
                {
                    "status": "strict_quality_gate_failed",
                    "blockers": strict_blockers,
                },
            ][-20:]

        if strict_blockers:
            failure_detail = "; ".join(
                f"{item.get('code')}:{item.get('message')}" for item in strict_blockers[:6]
            )[:1200]
            _persist_ppt_retry_diagnostic(
                {
                    "deck_id": deck_id,
                    "failure_code": "strict_quality_gate_failed",
                    "failure_detail": failure_detail,
                    "retry_scope": retry_scope,
                    "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                    "attempt": attempt,
                    "idempotency_key": req.idempotency_key,
                    "render_spec_version": render_spec_version,
                    "route_mode": route_policy.mode,
                    "quality_score": float(final_quality_score.score) if final_quality_score is not None else None,
                    "alert_count": len(alerts),
                    "status": "strict_quality_gate_failed",
                    "created_at": _utc_now(),
                }
            )
            _persist_ppt_observability_report(
                {
                    "deck_id": deck_id,
                    "status": "failed",
                    "failure_code": "strict_quality_gate_failed",
                    "failure_detail": failure_detail,
                    "route_mode": route_policy.mode,
                    "quality_profile": quality_profile,
                    "attempts": attempt,
                    "quality_score": (
                        float(final_quality_score.score) if final_quality_score is not None else None
                    ),
                    "quality_score_threshold": (
                        _to_float((export_data.get("quality_score") or {}).get("threshold"), None)
                        if isinstance(export_data.get("quality_score"), dict)
                        else None
                    ),
                    "alert_count": len(alerts),
                    "alerts": alerts,
                    "issue_codes": export_data.get("observability_report", {}).get("issue_codes", []),
                    "export_channel": export_data.get("export_channel"),
                    "generator_mode": export_data.get("generator_mode"),
                    "diagnostics": persisted_diagnostics,
                    "created_at": _utc_now(),
                }
            )
            raise RuntimeError(f"Strict quality gate failed: {failure_detail}")

        _persist_ppt_retry_diagnostic(
            {
                "deck_id": deck_id,
                "failure_code": None,
                "failure_detail": None,
                "retry_scope": retry_scope,
                "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                "attempt": attempt,
                "idempotency_key": req.idempotency_key,
                "render_spec_version": render_spec_version,
                "route_mode": route_policy.mode,
                "quality_score": float(final_quality_score.score) if final_quality_score is not None else None,
                "alert_count": len(alerts),
                "status": "success",
                "created_at": _utc_now(),
            }
        )
        _persist_ppt_observability_report(
            {
                "deck_id": deck_id,
                "status": "success",
                "failure_code": None,
                "failure_detail": None,
                "route_mode": route_policy.mode,
                "quality_profile": quality_profile,
                "attempts": attempt,
                "quality_score": (
                    float(final_quality_score.score) if final_quality_score is not None else None
                ),
                "quality_score_threshold": (
                    _to_float((export_data.get("quality_score") or {}).get("threshold"), None)
                    if isinstance(export_data.get("quality_score"), dict)
                    else None
                ),
                "alert_count": len(alerts),
                "alerts": alerts,
                "issue_codes": export_data.get("observability_report", {}).get("issue_codes", []),
                "export_channel": export_data.get("export_channel"),
                "generator_mode": export_data.get("generator_mode"),
                "diagnostics": persisted_diagnostics,
                "created_at": _utc_now(),
            }
        )

        return export_data

    async def parse_document(self, file_url: str, file_type: str = "pptx") -> ParsedDocument:
        from src.document_parser import parse_document

        return await parse_document(file_url, file_type)

    async def enhance_slides(
        self,
        slides: List[SlideContent],
        language: str = "zh-CN",
        enhance_narration: bool = True,
        generate_tts: bool = True,
        voice_style: str = "zh-CN-female",
    ) -> List[SlideContent]:
        if enhance_narration:
            slides = await self._enhance_narration(slides, language)
        if generate_tts:
            slides = await self._synthesize_tts(slides, voice_style)
        return slides

    async def _enhance_narration(
        self,
        slides: List[SlideContent],
        language: str,
    ) -> List[SlideContent]:
        import asyncio

        from src.openrouter_client import OpenRouterClient

        client = OpenRouterClient()
        model = os.getenv("CONTENT_LLM_MODEL", "openai/gpt-4o-mini")
        if language == "zh-CN":
            system_prompt = (
                "You are a PPT narration optimizer. Rewrite for spoken delivery in Chinese, "
                "keep key facts, and target around 50-300 Chinese characters."
            )
        else:
            system_prompt = (
                "You are a PPT narration optimizer. Make text conversational, smooth, "
                "and concise while preserving key information."
            )

        semaphore = asyncio.Semaphore(5)

        async def _enhance_one(idx: int, slide: SlideContent) -> tuple[int, str]:
            async with semaphore:
                narration = (slide.narration or "").strip()
                if not narration:
                    text_parts = [
                        el.content
                        for el in slide.elements
                        if getattr(el, "type", "") == "text" and getattr(el, "content", "")
                    ]
                    narration = " ".join(text_parts).strip()[:500]
                if len(narration) < 10:
                    return idx, narration

                raw = await client.chat_completions(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"标题: {slide.title}\n\n讲解稿:\n{narration}"},
                    ],
                    temperature=0.5,
                    max_tokens=1024,
                )
                enhanced = (raw or "").strip() or narration
                return idx, enhanced

        tasks = [_enhance_one(i, s) for i, s in enumerate(slides)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning("[ppt_service] narration enhance failed: %s", result)
                continue
            idx, enhanced = result
            slides[idx] = slides[idx].model_copy(update={"narration": enhanced})

        return slides

    async def _synthesize_tts(
        self,
        slides: List[SlideContent],
        voice_style: str,
    ) -> List[SlideContent]:
        from src.tts_synthesizer import synthesize_batch

        texts = [s.narration for s in slides]
        urls, durations = await synthesize_batch(texts, voice_style)

        for i, url in enumerate(urls):
            if not url:
                continue
            audio_dur = durations[i] if i < len(durations) else 0
            slide_dur = max(3, int(audio_dur + 1))
            slides[i] = slides[i].model_copy(
                update={
                    "narration_audio_url": url,
                    "duration": slide_dur,
                }
            )
            logger.info(
                "[ppt_service] slide %d: audio %.1fs -> video %ss",
                i + 1,
                float(audio_dur),
                slide_dur,
            )

        return slides

    async def start_video_render(
        self,
        slides: List[Dict[str, Any]],
        config: VideoRenderConfig,
    ) -> RenderJob:
        from src.lambda_renderer import start_render

        job = RenderJob(
            project_id=_new_id(),
            status="pending",
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        self._cache_render_job(job)

        sb = _get_supabase()
        if sb:
            try:
                sb.table("ppt_render_jobs").upsert(
                    {
                        "id": job.id,
                        "project_id": job.project_id,
                        "status": job.status,
                        "progress": 0,
                        "config": config.model_dump_json(),
                        "created_at": job.created_at,
                        "updated_at": job.updated_at,
                    }
                ).execute()
            except Exception as exc:
                logger.warning("[ppt_service] failed to persist render job: %s", exc)

        try:
            image_mode = len(slides) > 0 and all(
                _is_image_slide(s.model_dump() if hasattr(s, "model_dump") else s) for s in slides
            )
            slides_data: List[Dict[str, Any]] = []
            for idx, slide in enumerate(slides):
                if isinstance(slide, dict):
                    if image_mode:
                        slides_data.append(_normalize_image_slide_for_renderer(slide))
                    else:
                        slides_data.append(_normalize_slide_for_renderer(slide, idx))
                elif hasattr(slide, "model_dump"):
                    slide_dict = slide.model_dump()  # type: ignore[arg-type]
                    if image_mode:
                        slides_data.append(_normalize_image_slide_for_renderer(slide_dict))
                    else:
                        slides_data.append(_normalize_slide_for_renderer(slide_dict, idx))
                else:
                    raise ValueError(f"Unsupported slide type: {type(slide)!r}")

            config_data = config.model_dump()
            if image_mode:
                config_data["composition"] = "ImageSlideshow"

            result = await start_render(
                slides=slides_data,
                config=config_data,
                prefer_local=not bool(os.getenv("REMOTION_LAMBDA_FUNCTION")),
            )

            job.lambda_job_id = result.get("render_id")
            job.output_url = result.get("video_url")
            if job.output_url:
                job.status = "done"
                job.progress = 100
            else:
                job.status = "rendering"
            job.updated_at = _utc_now()

            if sb:
                try:
                    sb.table("ppt_render_jobs").update(
                        {
                            "status": job.status,
                            "progress": job.progress,
                            "lambda_job_id": job.lambda_job_id,
                            "output_url": job.output_url,
                            "updated_at": job.updated_at,
                        }
                    ).eq("id", job.id).execute()
                except Exception:
                    pass
            self._cache_render_job(job)
        except Exception as exc:
            logger.error("[ppt_service] video render failed: %s", exc)
            job.status = "failed"
            job.error = str(exc)
            job.updated_at = _utc_now()
            if sb:
                try:
                    sb.table("ppt_render_jobs").update(
                        {
                            "status": "failed",
                            "error": job.error,
                            "updated_at": job.updated_at,
                        }
                    ).eq("id", job.id).execute()
                except Exception:
                    pass
            self._cache_render_job(job)

        return job

    async def get_render_status(self, job_id: str) -> Dict[str, Any]:
        sb = _get_supabase()
        if not sb:
            cached = _local_render_jobs.get(job_id)
            if cached:
                return _render_status_from_row(cached)
            return {"job_id": job_id, "status": "not_found"}

        try:
            res = sb.table("ppt_render_jobs").select("*").eq("id", job_id).limit(1).execute()
            if res.data:
                return _render_status_from_row(res.data[0])

            cached = _local_render_jobs.get(job_id)
            if cached:
                return _render_status_from_row(cached)
            return {"job_id": job_id, "status": "not_found"}
        except Exception as exc:
            logger.warning("[ppt_service] get_render_status supabase fallback: %s", exc)
            cached = _local_render_jobs.get(job_id)
            if cached:
                return _render_status_from_row(cached)
            return {"job_id": job_id, "status": "unknown", "error": str(exc)}

    async def get_download_url(self, job_id: str) -> Dict[str, Any]:
        sb = _get_supabase()
        row: Dict[str, Any] | None = None
        if sb:
            try:
                res = (
                    sb.table("ppt_render_jobs")
                    .select("*")
                    .eq("id", job_id)
                    .limit(1)
                    .execute()
                )
                if res.data:
                    row = res.data[0]
            except Exception as exc:
                logger.warning("[ppt_service] get_download_url supabase fallback: %s", exc)

        if row is None:
            row = _local_render_jobs.get(job_id)
        if row is None:
            raise LookupError(f"Render job not found: {job_id}")

        status = row.get("status", "unknown")
        if status not in ("done", "completed"):
            return {
                "job_id": job_id,
                "status": status,
                "message": f"Render not finished: {status}",
                "output_url": None,
            }

        output_url = row.get("output_url")
        if not output_url:
            return {
                "job_id": job_id,
                "status": status,
                "message": "Render finished but output URL is empty",
                "output_url": None,
            }

        try:
            from urllib.parse import urlparse

            from src.r2 import get_r2_client

            r2 = get_r2_client()
            if r2:
                parsed = urlparse(output_url)
                key = parsed.path.lstrip("/")
                bucket = os.getenv("R2_BUCKET", "video")
                presigned = r2.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": key},
                    ExpiresIn=3600,
                )
                return {"job_id": job_id, "status": status, "output_url": presigned}
        except Exception as exc:
            logger.warning("[ppt_service] presign failed, fallback direct URL: %s", exc)

        return {"job_id": job_id, "status": status, "output_url": output_url}
