"""PPT service: generation, export, enhancement and render lifecycle."""

from __future__ import annotations

import asyncio
import html
import hashlib
import json
import logging
import os
import re
import math
import subprocess
import sys
import tempfile
import uuid
import base64
import mimetypes
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote as url_quote, urlparse, unquote as url_unquote
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
    template_capabilities as shared_template_capabilities,
    contract_profile as shared_contract_profile,
    list_template_ids as shared_template_ids,
    quality_profile as shared_quality_profile,
    resolve_template_for_slide,
    template_profiles as shared_template_profiles,
)
from src.ppt_design_decision import (
    attach_design_decision_v1,
    build_design_decision_v1,
    freeze_retry_visual_identity,
    normalize_design_decision_v1,
)
from src.ppt_design_constraints import validate_render_payload_design
from src.ppt_master_design_spec import apply_render_paths, build_design_spec
from src.ppt_master_skill_adapter import (
    is_ppt_master_candidate,
    should_force_ppt_master_hit,
)
from src.ppt_archetype_selector import (
    load_archetype_catalog,
    select_slide_archetype,
)
from src.ppt_layout_solver import solve_slide_layout
from src.ppt_palette_catalog import canonicalize_palette_key
from src.ppt_reference_contract import audit_reference_contract
from src.ppt_content_layout_profiles import build_content_layout_plan
from src.ppt_storyline_planning import (
    build_instructional_topic_points,
    build_research_storyline_notes,
    expand_semantic_support_points,
    is_instructional_context,
)
from src.ppt_visual_identity import canonicalize_theme_recipe, resolve_style_variant, resolve_tone, style_variant_for_theme_recipe, suggest_theme_recipe_from_context
import src.r2 as r2

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


def _normalize_execution_profile(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"dev", "strict", "dev_strict"}:
        return "dev_strict"
    if text in {"prod", "safe", "prod_safe"}:
        return "prod_safe"
    return ""


def _derive_deck_archetype_profile(
    *,
    topic: str = "",
    audience: str = "",
    purpose: str = "",
    quality_profile: str = "",
    theme_recipe: str = "",
) -> str:
    profile = str(quality_profile or "").strip().lower()
    recipe = str(theme_recipe or "").strip().lower()
    blob = " ".join([str(topic or ""), str(audience or ""), str(purpose or "")]).lower()
    if profile == "training_deck" or recipe == "classroom_soft" or any(token in blob for token in ("classroom", "teaching", "lesson", "education", "training", "课堂", "教学", "教育", "课程", "培训", "高中", "学生")):
        return "education_textbook"
    if profile in {"investor_pitch", "marketing_pitch"} or any(token in blob for token in ("investor", "pitch", "融资", "路演", "marketing", "campaign", "品牌")):
        return "consulting_argument"
    if profile == "tech_review" or any(token in blob for token in ("architecture", "engineering", "技术评审", "架构评审", "technical review")):
        return "technical_review"
    return "general_presentation"


def _default_palette_for_archetype(archetype_profile: str, fallback: str = "auto") -> str:
    archetype = str(archetype_profile or "").strip().lower()
    if archetype == "education_textbook":
        return "education_office_classic"
    return str(fallback or "auto").strip() or "auto"


def _enforce_profile_field_ownership(
    payload: Dict[str, Any],
    *,
    quality_profile: str = "",
    hardness_profile: str = "",
    deck_archetype_profile: str = "",
) -> Dict[str, Any]:
    out = dict(payload or {})
    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    normalized_quality = str(quality_profile or "").strip().lower()
    normalized_hardness = str(hardness_profile or "").strip().lower()
    normalized_archetype = str(deck_archetype_profile or "").strip().lower()
    if normalized_quality and normalized_quality != "auto":
        out["quality_profile"] = normalized_quality
    if normalized_hardness and normalized_hardness != "auto":
        out["hardness_profile"] = normalized_hardness
    if normalized_archetype:
        out["deck_archetype_profile"] = normalized_archetype
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        if normalized_quality and normalized_quality != "auto":
            slide["quality_profile"] = normalized_quality
        if normalized_hardness and normalized_hardness != "auto":
            slide["hardness_profile"] = normalized_hardness
        if normalized_archetype:
            slide["deck_archetype_profile"] = normalized_archetype
    out["slides"] = slides
    return out


_VISUAL_DECISION_OWNED_FIELDS = (
    "style_variant",
    "palette_key",
    "theme_recipe",
    "tone",
    "template_family",
    "layout_grid",
    "render_path",
    "skill_profile",
)


def _resolve_slide_identity(slide: Dict[str, Any], index: int) -> str:
    for key in ("slide_id", "id", "page_number"):
        raw = str(slide.get(key) or "").strip()
        if raw:
            return raw
    return f"slide-{index + 1}"


def _collect_visual_owner_conflicts(
    slides: List[Dict[str, Any]],
    decision: Dict[str, Any],
) -> List[str]:
    if not isinstance(decision, dict):
        return []
    normalized = normalize_design_decision_v1(decision)
    deck = normalized.get("deck") if isinstance(normalized.get("deck"), dict) else {}
    rows = normalized.get("slides") if isinstance(normalized.get("slides"), list) else []
    by_slide: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("slide_id") or "").strip()
        if sid and sid not in by_slide:
            by_slide[sid] = row
    conflicts: List[str] = []
    for idx, slide in enumerate(slides or []):
        if not isinstance(slide, dict):
            continue
        sid = _resolve_slide_identity(slide, idx)
        row = by_slide.get(sid, {})
        for field in _VISUAL_DECISION_OWNED_FIELDS:
            target = str(row.get(field) or "").strip() or str(deck.get(field) or "").strip()
            if not target or target.lower() in {"auto", "none", "null", "undefined"}:
                continue
            current = str(slide.get(field) or "").strip()
            if not current or current.lower() in {"auto", "none", "null", "undefined"}:
                continue
            if current != target:
                conflicts.append(f"{sid}:{field}:{current}->{target}")
                if len(conflicts) >= 20:
                    return conflicts
    return conflicts


def _canonicalize_pipeline_palette(
    palette_key: str,
    *,
    context_parts: Optional[List[Any]] = None,
    fallback: str = "auto",
) -> str:
    context_text = " ".join(str(item or "").strip() for item in (context_parts or []) if str(item or "").strip())
    return canonicalize_palette_key(
        str(palette_key or ""),
        context_text=context_text,
        fallback=str(fallback or "auto"),
    )


def _resolve_execution_profile_for_runtime(value: Any) -> str:
    normalized = _normalize_execution_profile(value)
    if normalized:
        return normalized
    default_raw = str(os.getenv("PPT_DEFAULT_EXECUTION_PROFILE", "dev_strict")).strip()
    default_profile = _normalize_execution_profile(default_raw)
    return default_profile or "dev_strict"


def _enforce_dev_fast_fail_profile(execution_profile: str, *, stage: str) -> None:
    """In development, require strict profile instead of silent fallback paths."""
    if not _env_flag("PPT_DEV_FAST_FAIL", "true"):
        return
    profile = str(execution_profile or "").strip().lower()
    if profile != "dev_strict":
        raise ValueError(
            f"{stage}: execution_profile must be dev_strict in development "
            f"(got '{profile or 'unknown'}')"
        )


def _pipeline_export_timeout_sec(
    default: int = 420,
    *,
    slide_count: int = 0,
    route_mode: str = "auto",
) -> int:
    env_raw = os.getenv("PPT_PIPELINE_EXPORT_TIMEOUT_SEC")
    raw = str(env_raw or "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = default
        # Explicit env override keeps wider ceiling for ops tuning.
        return max(120, min(1800, value))
    else:
        # Keep API latency under common client read timeouts while still adapting
        # to larger decks. Previous 30s/slide could exceed 600s client timeout.
        value = max(default, 180 + max(0, int(slide_count)) * 15)
        if str(route_mode or "").strip().lower() == "refine":
            value += 60
    return max(120, min(540, value))


def _pipeline_stage_timeout_sec(stage: str, default: int) -> int:
    """Resolve per-stage timeout with optional env overrides."""
    stage_key = str(stage or "").strip().upper().replace("-", "_")
    specific = os.getenv(f"PPT_PIPELINE_{stage_key}_TIMEOUT_SEC")
    common = os.getenv("PPT_PIPELINE_STAGE_TIMEOUT_SEC")
    raw = str(specific or common or "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = int(default)
    else:
        value = int(default)
    return max(15, min(1800, value))


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


def _normalize_retry_scope(value: Any) -> str:
    scope = str(value or "").strip().lower()
    if scope in {"deck", "slide", "block"}:
        return scope
    return "deck"


def _resolve_retry_budget(*, env_max_attempts: int, route_mode: str, route_policy_max: int) -> int:
    explicit_env = str(os.getenv("PPT_RETRY_MAX_ATTEMPTS", "")).strip()
    if explicit_env:
        return max(1, int(env_max_attempts))

    phase_retry_caps = {
        "fast": 1,
        "standard": 2,
        "refine": 3,
    }
    cap = phase_retry_caps.get(str(route_mode or "").strip().lower(), 2)
    return max(1, min(int(env_max_attempts), int(route_policy_max), int(cap)))


_RELAXED_LAYOUT_ISSUE_CODES_PIPELINE = {
    "layout_homogeneous",
    "layout_top2_homogeneous",
    "layout_adjacent_repeat",
    "template_family_switch_frequent",
    "template_family_abab_repeat",
    "template_family_homogeneous",
    "template_family_top2_homogeneous",
}

_RELAXED_LAYOUT_ISSUE_CODES_EXPORT = {
    "layout_homogeneous",
    "layout_top2_homogeneous",
    "layout_adjacent_repeat",
    "template_family_homogeneous",
    "template_family_top2_homogeneous",
}

_REFERENCE_RECONSTRUCT_RELAXED_LAYOUT_ISSUE_CODES = {
    "layout_variety_low",
    "layout_density_window_missing_breathing",
    "layout_terminal_summary_missing",
}

_ACCURACY_HARD_FAIL_CODES = {
    "placeholder_kpi_data",
    "placeholder_chart_data",
    "placeholder_pollution",
}


def _relaxed_quality_issue_codes(
    *,
    route_mode: str,
    quality_profile: str,
    use_reference_reconstruct: bool,
    requested_execution_profile: str,
    include_template_switch_relaxation: bool,
) -> set[str]:
    if str(requested_execution_profile or "").strip().lower() == "dev_strict":
        return set()
    relaxed_codes: set[str] = set()
    fast_relaxed_set = (
        _RELAXED_LAYOUT_ISSUE_CODES_PIPELINE
        if include_template_switch_relaxation
        else _RELAXED_LAYOUT_ISSUE_CODES_EXPORT
    )
    if str(route_mode or "").strip().lower() == "fast" or str(quality_profile or "").strip().lower() == "lenient_draft":
        relaxed_codes.update(fast_relaxed_set)
    if use_reference_reconstruct:
        relaxed_codes.update(_RELAXED_LAYOUT_ISSUE_CODES_EXPORT)
        relaxed_codes.update(_REFERENCE_RECONSTRUCT_RELAXED_LAYOUT_ISSUE_CODES)
    return {code for code in relaxed_codes if code not in _ACCURACY_HARD_FAIL_CODES}


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
    if any(token in text for token in ("培训", "课程", "教学", "课堂", "高中", "training", "onboarding", "workshop", "classroom")):
        return "training_deck"
    if any(token in text for token in ("技术评审", "架构评审", "tech review", "architecture review", "engineering")):
        return "tech_review"
    if any(token in text for token in ("营销", "品牌", "发布会", "marketing", "campaign", "launch", "brand")):
        return "marketing_pitch"
    if pages >= 14:
        return "high_density_consulting"
    return "default"


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
    execution_profile: str = "",
    force_ppt_master: Any = None,
) -> List[str]:
    slide_type = str(slide.get("slide_type") or "").strip().lower()
    layout_grid = str(slide.get("layout_grid") or "").strip().lower()
    render_path = str(slide.get("render_path") or "").strip().lower()
    template_family = str(slide.get("template_family") or deck_template_family or "").strip().lower()
    has_template_hint = bool(
        template_family and template_family not in {"auto"}
    ) or bool(
        slide.get("template_family_whitelist")
        or slide.get("template_candidates")
        or slide.get("template_whitelist")
    )
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
    if should_force_ppt_master_hit(
        requested_execution_profile=execution_profile,
        requested_force_flag=force_ppt_master,
    ) or is_ppt_master_candidate(slide, {"execution_profile": execution_profile}):
        skills.append("ppt-master")
    if has_template_hint:
        skills.append("ppt-editing-skill")
    existing = slide.get("load_skills") if isinstance(slide.get("load_skills"), list) else []
    skills.extend(str(item) for item in existing)
    return _dedupe_skill_names(skills)


def _apply_skill_planning_to_render_payload(
    render_payload: Dict[str, Any],
    *,
    execution_profile: str = "",
    force_ppt_master: Any = None,
) -> Dict[str, Any]:
    out = dict(render_payload or {})
    slides = out.get("slides")
    if not isinstance(slides, list) or not slides:
        return out
    resolved_execution_profile = _normalize_execution_profile(
        execution_profile or out.get("execution_profile")
    )
    out["execution_profile"] = resolved_execution_profile
    resolved_force_ppt_master = (
        force_ppt_master if force_ppt_master is not None else out.get("force_ppt_master")
    )

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
    enforce_skill_runtime = _require_direct_skill_runtime() or (
        resolved_execution_profile == "dev_strict"
    )
    try:
        from src.installed_skill_executor import execute_installed_skill_request
    except Exception as exc:
        runtime["reason"] = f"skill_planning_runtime_unavailable:{str(exc)[:180]}"
        out["skill_planning_runtime"] = runtime
        return out

    runtime["enabled"] = True
    total = len(slides)
    deck_topic_blob = " ".join(
        part
        for part in [
            str(out.get("title") or "").strip(),
            str(out.get("topic") or "").strip(),
            str(out.get("audience") or "").strip(),
            str(out.get("purpose") or "").strip(),
            str(out.get("style_preference") or "").strip(),
        ]
        if part
    )
    deck_ctx = {
        "title": str(out.get("title") or "").strip(),
        "topic": deck_topic_blob or str(out.get("title") or "").strip(),
        "total_slides": total,
        "style": str((out.get("theme") or {}).get("style") if isinstance(out.get("theme"), dict) else ""),
        "palette_key": str((out.get("theme") or {}).get("palette") if isinstance(out.get("theme"), dict) else ""),
        "theme_recipe": str(
            out.get("theme_recipe")
            or ((out.get("theme") or {}).get("theme_recipe") if isinstance(out.get("theme"), dict) else "")
            or ""
        ).strip().lower(),
        "tone": str(
            out.get("tone")
            or ((out.get("theme") or {}).get("tone") if isinstance(out.get("theme"), dict) else "")
            or ""
        ).strip().lower(),
        "template_family": str(out.get("template_family") or "").strip().lower(),
        "execution_profile": resolved_execution_profile,
        "force_ppt_master": resolved_force_ppt_master,
    }

    planned_slides: List[Dict[str, Any]] = []
    deck_style_variant = str(out.get("style_variant") or "").strip().lower()
    deck_palette_key = str(out.get("palette_key") or "").strip()
    deck_theme_recipe = str(out.get("theme_recipe") or deck_ctx.get("theme_recipe") or "").strip().lower()
    deck_tone = str(out.get("tone") or deck_ctx.get("tone") or "").strip().lower()
    deck_template_family = str(out.get("template_family") or "").strip().lower()
    deck_skill_profile = str(out.get("skill_profile") or "").strip()
    content_layout_history: List[str] = []
    content_template_history: List[str] = []
    content_slide_index = 0

    for idx, raw_slide in enumerate(slides):
        slide = dict(raw_slide if isinstance(raw_slide, dict) else {})
        deck_ctx["content_slide_index"] = content_slide_index
        deck_ctx["used_content_layouts"] = list(content_layout_history[-8:])
        deck_ctx["used_template_families"] = list(content_template_history[-8:])
        requested_skills = _requested_skills_for_slide(
            slide,
            idx,
            total,
            deck_template_family=str(deck_ctx.get("template_family") or ""),
            execution_profile=resolved_execution_profile,
            force_ppt_master=resolved_force_ppt_master,
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
                    "execution_profile": resolved_execution_profile,
                    "force_ppt_master": resolved_force_ppt_master,
                }
            )
        except Exception as exc:
            if enforce_skill_runtime:
                raise RuntimeError(
                    f"skill_executor_exception:slide={row_runtime['slide_id']}:{str(exc)[:220]}"
                ) from exc
            row_runtime["reason"] = f"skill_executor_exception:{str(exc)[:180]}"
            runtime["slides"].append(row_runtime)
            planned_slides.append(slide)
            continue

        if enforce_skill_runtime:
            _assert_skill_runtime_success(
                stage="skill_planning",
                skill_output=skill_output if isinstance(skill_output, dict) else {},
                requested_skills=requested_skills,
                slide_id=row_runtime["slide_id"],
            )

        patch = skill_output.get("patch") if isinstance(skill_output.get("patch"), dict) else {}
        context = skill_output.get("context") if isinstance(skill_output.get("context"), dict) else {}
        trace = skill_output.get("results") if isinstance(skill_output.get("results"), list) else []
        violations = (
            skill_output.get("skill_write_violations")
            if isinstance(skill_output.get("skill_write_violations"), list)
            else []
        )
        conflicts = (
            skill_output.get("skill_write_conflicts")
            if isinstance(skill_output.get("skill_write_conflicts"), list)
            else []
        )
        row_runtime["trace"] = trace
        row_runtime["applied_keys"] = sorted(str(key) for key in patch.keys())
        row_runtime["skill_write_violations"] = violations
        row_runtime["skill_write_conflicts"] = conflicts

        for key in (
            "slide_type",
            "layout_grid",
            "render_path",
            "template_family",
            "skill_profile",
            "style_variant",
            "palette_key",
            "theme_recipe",
            "tone",
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
        if isinstance(context.get("template_candidates"), list):
            template_candidates = [
                str(item or "").strip().lower()
                for item in context.get("template_candidates") or []
                if str(item or "").strip()
            ]
            if template_candidates:
                slide["template_candidates"] = template_candidates
        if isinstance(context.get("template_family_whitelist"), list):
            template_whitelist = [
                str(item or "").strip().lower()
                for item in context.get("template_family_whitelist") or []
                if str(item or "").strip()
            ]
            if template_whitelist:
                slide["template_family_whitelist"] = template_whitelist
        template_selection_mode = str(context.get("template_selection_mode") or "").strip()
        if template_selection_mode:
            slide["template_selection_mode"] = template_selection_mode
        page_design_intent = str(context.get("page_design_intent") or "").strip()
        if page_design_intent:
            slide["page_design_intent"] = page_design_intent

        style_variant = str(patch.get("style_variant") or context.get("style_variant") or "").strip().lower()
        palette_key = str(patch.get("palette_key") or context.get("palette_key") or "").strip()
        theme_recipe = str(patch.get("theme_recipe") or context.get("theme_recipe") or "").strip().lower()
        tone = str(patch.get("tone") or context.get("tone") or "").strip().lower()
        template_family = str(patch.get("template_family") or context.get("template_family") or "").strip().lower()
        skill_profile = str(patch.get("skill_profile") or context.get("skill_profile") or "").strip()
        if not deck_style_variant and style_variant:
            deck_style_variant = style_variant
        if not deck_palette_key and palette_key:
            deck_palette_key = palette_key
        if not deck_theme_recipe and theme_recipe:
            deck_theme_recipe = theme_recipe
        if not deck_tone and tone:
            deck_tone = tone
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
            template_final = str(slide.get("template_family") or "").strip().lower()
            if template_final:
                content_template_history.append(template_final)

        runtime["slides"].append(row_runtime)
        planned_slides.append(slide)

    out["slides"] = planned_slides
    if deck_style_variant:
        out["style_variant"] = deck_style_variant
    if deck_palette_key:
        out["palette_key"] = deck_palette_key
    if deck_theme_recipe:
        out["theme_recipe"] = canonicalize_theme_recipe(deck_theme_recipe, fallback="consulting_clean")
    if deck_tone:
        out["tone"] = resolve_tone(deck_tone, theme_recipe=out.get("theme_recipe") or deck_theme_recipe, fallback="auto")
    if deck_template_family:
        out["template_family"] = deck_template_family
    if deck_skill_profile:
        out["skill_profile"] = deck_skill_profile

    theme_obj = out.get("theme") if isinstance(out.get("theme"), dict) else {}
    if deck_style_variant:
        theme_obj["style"] = deck_style_variant
    if deck_palette_key:
        theme_obj["palette"] = deck_palette_key
    if out.get("theme_recipe"):
        theme_obj["theme_recipe"] = str(out.get("theme_recipe") or "").strip().lower()
    if out.get("tone"):
        theme_obj["tone"] = str(out.get("tone") or "").strip().lower()
    if theme_obj:
        out["theme"] = theme_obj
    out["skill_planning_runtime"] = runtime
    decision_trace = [
        {
            "source": "skill_planning_runtime",
            "detail": (
                f"enabled={bool(runtime.get('enabled'))}; "
                f"slides={len(runtime.get('slides') or [])}"
            ),
            "confidence": 1.0,
        }
    ]
    return attach_design_decision_v1(
        out,
        decision_source="skill_planning",
        decision_trace=decision_trace,
    )


def _run_layer1_design_skill_chain(
    *,
    deck_title: str,
    slides: List[Dict[str, Any]],
    requested_style_variant: str,
    requested_palette_key: str,
    requested_template_family: str,
    requested_skill_profile: str,
    requested_theme_recipe: str = "auto",
    requested_tone: str = "auto",
    context_parts: Optional[List[str]] = None,
    execution_profile: str = "",
    force_ppt_master: Any = None,
) -> Dict[str, Any]:
    """Run Layer1 design decision skills before orchestration.

    This mirrors the architecture doc intent: call design skills directly in
    the main path, then feed decisions into orchestration/render.
    """
    effective_style = str(requested_style_variant or "auto").strip().lower() or "auto"
    effective_palette = str(requested_palette_key or "auto").strip() or "auto"
    effective_theme_recipe = canonicalize_theme_recipe(requested_theme_recipe or "auto", fallback="auto")
    effective_tone = resolve_tone(requested_tone or "auto", theme_recipe=effective_theme_recipe, fallback="auto")
    effective_template = str(requested_template_family or "auto").strip().lower() or "auto"
    effective_skill_profile = str(requested_skill_profile or "auto").strip() or "auto"
    resolved_execution_profile = _normalize_execution_profile(execution_profile)
    resolved_force_ppt_master = force_ppt_master

    requested_skills = [
        "ppt-orchestra-skill",
        "color-font-skill",
        "design-style-skill",
        "pptx",
    ]
    if should_force_ppt_master_hit(
        requested_execution_profile=resolved_execution_profile,
        requested_force_flag=resolved_force_ppt_master,
    ):
        requested_skills.append("ppt-master")
    if effective_template and effective_template not in {"auto"}:
        requested_skills.append("ppt-editing-skill")
    first_slide = dict(slides[0]) if slides and isinstance(slides[0], dict) else {}
    deck_context_blob = " ".join(
        part
        for part in [
            str(deck_title or "").strip(),
            *[str(item or "").strip() for item in (context_parts or [])],
            *[str((slide or {}).get("title") or "").strip() for slide in slides[:4] if isinstance(slide, dict)],
        ]
        if part
    )
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
        "execution_profile": resolved_execution_profile,
        "force_ppt_master": resolved_force_ppt_master,
    }

    runtime: Dict[str, Any] = {
        "enabled": False,
        "requested_skills": requested_skills,
        "results": [],
        "context": {},
        "reason": "",
    }
    enforce_skill_runtime = _require_direct_skill_runtime() or (
        resolved_execution_profile == "dev_strict"
    )
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
                    "topic": deck_context_blob or deck_title,
                    "total_slides": len(slides),
                    "style_variant": effective_style,
                    "palette_key": effective_palette,
                    "theme_recipe": effective_theme_recipe,
                    "tone": effective_tone,
                    "execution_profile": resolved_execution_profile,
                    "force_ppt_master": resolved_force_ppt_master,
                },
                "execution_profile": resolved_execution_profile,
                "force_ppt_master": resolved_force_ppt_master,
            }
        )
        if enforce_skill_runtime:
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
        if enforce_skill_runtime:
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
    suggested_theme_recipe = str(
        patch.get("theme_recipe") or runtime_ctx.get("theme_recipe") or ""
    ).strip().lower()
    suggested_tone = str(
        patch.get("tone") or runtime_ctx.get("tone") or ""
    ).strip().lower()
    suggested_profile = str(
        patch.get("skill_profile") or runtime_ctx.get("skill_profile") or ""
    ).strip()

    if effective_template in {"", "auto"} and suggested_template:
        effective_template = suggested_template
    if effective_style in {"", "auto"} and suggested_style:
        effective_style = suggested_style
    if effective_palette in {"", "auto"} and suggested_palette:
        effective_palette = suggested_palette
    if effective_theme_recipe in {"", "auto"} and suggested_theme_recipe:
        effective_theme_recipe = canonicalize_theme_recipe(suggested_theme_recipe, fallback="consulting_clean")
    if effective_theme_recipe in {"", "auto"}:
        effective_theme_recipe = canonicalize_theme_recipe(
            suggest_theme_recipe_from_context(
                deck_title,
                *(context_parts or []),
                *[str((slide or {}).get("title") or "") for slide in slides[:8] if isinstance(slide, dict)],
            ),
            fallback="consulting_clean",
        )
    if effective_tone in {"", "auto"} and suggested_tone in {"light", "dark"}:
        effective_tone = resolve_tone(suggested_tone, theme_recipe=effective_theme_recipe, fallback="auto")
    effective_style = style_variant_for_theme_recipe(effective_theme_recipe, fallback=effective_style or "soft")
    effective_tone = resolve_tone(effective_tone, theme_recipe=effective_theme_recipe, fallback="auto")
    effective_palette = _canonicalize_pipeline_palette(
        effective_palette,
        context_parts=[
            deck_title,
            requested_template_family,
            requested_skill_profile,
            *[str((slide or {}).get("title") or "") for slide in slides[:4] if isinstance(slide, dict)],
        ],
        fallback="auto",
    )
    if effective_skill_profile in {"", "auto"} and suggested_profile:
        effective_skill_profile = suggested_profile
    if effective_skill_profile in {"", "auto"}:
        if "architecture" in effective_template:
            effective_skill_profile = "architecture"
        elif "hero" in effective_template:
            effective_skill_profile = "cover"
        else:
            effective_skill_profile = "general-content"

    layer1_decision = build_design_decision_v1(
        style_variant=effective_style,
        palette_key=effective_palette,
        theme_recipe=effective_theme_recipe,
        tone=effective_tone,
        template_family=effective_template,
        skill_profile=effective_skill_profile,
        slides=slides,
        decision_source="layer1_design",
        decision_trace=[
            {
                "source": "layer1_design_skill_chain",
                "detail": (
                    f"runtime_enabled={bool(runtime.get('enabled'))}; "
                    f"results={len(runtime.get('results') or [])}"
                ),
                "confidence": 1.0,
            }
        ],
    )

    return {
        "style_variant": effective_style,
        "palette_key": effective_palette,
        "theme_recipe": effective_theme_recipe,
        "tone": effective_tone,
        "template_family": effective_template,
        "skill_profile": effective_skill_profile,
        "runtime": runtime,
        "design_decision_v1": layer1_decision,
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
        slide_archetype = str(raw.get("archetype") or "").strip().lower()
        notes_for_designer = str(raw.get("notes_for_designer") or "")
        template_whitelist: List[str] = [
            str(item or "").strip().lower()
            for item in (raw.get("template_candidates") if isinstance(raw.get("template_candidates"), list) else [])
            if str(item or "").strip()
        ][:4]
        if "TEMPLATE_WHITELIST:" in notes_for_designer:
            marker = notes_for_designer.split("TEMPLATE_WHITELIST:", 1)[1]
            if not template_whitelist:
                template_whitelist = [
                    str(item or "").strip().lower()
                    for item in marker.splitlines()[0].split(",")
                    if str(item or "").strip()
                ][:4]
            notes_for_designer = notes_for_designer.split("TEMPLATE_WHITELIST:", 1)[0].rstrip()

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
            "narration": notes_for_designer,
            "blocks": normalized_blocks,
        }
        if slide_archetype:
            payload_slide["archetype"] = slide_archetype
        if template_whitelist:
            payload_slide["template_family_whitelist"] = template_whitelist
            payload_slide["template_candidates"] = template_whitelist
        if content_strategy:
            payload_slide["content_strategy"] = content_strategy
        slides.append(payload_slide)

    return {
        "title": plan.title,
        "theme": {"palette": plan.theme, "style": plan.style},
        "slides": slides,
    }


def _normalize_reference_slide_type(slide: Dict[str, Any], index: int, total: int) -> str:
    explicit = str(
        slide.get("slide_type")
        or slide.get("page_type")
        or slide.get("subtype")
        or ""
    ).strip().lower()
    if explicit in {"cover", "toc", "summary", "divider", "content"}:
        return explicit
    title = str(slide.get("title") or "").strip().lower()
    if index == 0:
        return "cover"
    if index == max(0, total - 1):
        return "summary"
    if any(token in title for token in ("目录", "contents", "content")):
        return "toc"
    if any(token in title for token in ("part", "section", "章节", "部分")):
        return "divider"
    return "content"


def _build_render_payload_from_reference_desc(
    reference_desc: Dict[str, Any],
    *,
    fallback_title: str,
) -> Dict[str, Any]:
    source_slides = (
        reference_desc.get("slides")
        if isinstance(reference_desc.get("slides"), list)
        else []
    )
    payload_slides: List[Dict[str, Any]] = []
    total = len(source_slides)
    for idx, raw in enumerate(source_slides):
        if not isinstance(raw, dict):
            continue
        slide_id = str(
            raw.get("slide_id")
            or raw.get("id")
            or f"slide-{idx + 1:03d}"
        ).strip()
        title = str(raw.get("title") or f"Slide {idx + 1}").strip() or f"Slide {idx + 1}"
        normalized_slide_type = _normalize_reference_slide_type(raw, idx, total)
        page_type = (
            normalized_slide_type
            if normalized_slide_type in {"cover", "toc", "summary", "divider"}
            else "content"
        )
        layout_grid = str(
            raw.get("layout_grid")
            or raw.get("layout_hint")
            or "template_canvas"
        ).strip() or "template_canvas"

        blocks_raw = raw.get("blocks") if isinstance(raw.get("blocks"), list) else []
        normalized_blocks: List[Dict[str, Any]] = []
        for block_idx, block in enumerate(blocks_raw):
            if not isinstance(block, dict):
                continue
            btype = str(
                block.get("block_type")
                or block.get("type")
                or "body"
            ).strip().lower()
            if btype not in {
                "title",
                "subtitle",
                "body",
                "kpi",
                "chart",
                "image",
                "icon_text",
                "list",
                "quote",
                "table",
            }:
                btype = "body"
            data = block.get("data")
            if btype == "kpi":
                number_value = None
                if isinstance(data, dict):
                    number_value = _to_float(data.get("number"), None)
                if number_value is None:
                    btype = "body"
            position = str(block.get("position") or "center").strip().lower()
            if position not in {
                "top",
                "left",
                "right",
                "center",
                "bottom",
                "top_left",
                "top_right",
                "bottom_left",
                "bottom_right",
            }:
                position = "center"
            content = block.get("content")
            if content is None:
                content = ""
            if not isinstance(content, (str, dict)):
                content = str(content)
            out_block: Dict[str, Any] = {
                "id": str(block.get("id") or f"{slide_id}-block-{block_idx + 1}"),
                "card_id": str(block.get("card_id") or f"card-{block_idx + 1}"),
                "block_type": btype,
                "type": btype,
                "position": position,
                "content": content,
            }
            if isinstance(data, dict):
                out_block["data"] = data
            emphasis = block.get("emphasis")
            if isinstance(emphasis, list):
                out_block["emphasis"] = [str(item) for item in emphasis if str(item).strip()]
            normalized_blocks.append(out_block)

        elements_raw = raw.get("elements") if isinstance(raw.get("elements"), list) else []
        normalized_elements: List[Dict[str, Any]] = []
        for el_idx, element in enumerate(elements_raw):
            if not isinstance(element, dict):
                continue
            copied = dict(element)
            copied.setdefault("id", f"{slide_id}-el-{el_idx + 1}")
            normalized_elements.append(copied)

        shapes_raw = raw.get("shapes") if isinstance(raw.get("shapes"), list) else []
        for shape_idx, shape in enumerate(shapes_raw):
            if not isinstance(shape, dict):
                continue
            subtype = str(shape.get("subtype") or shape.get("type") or "").strip().lower()
            if subtype != "image":
                continue
            image_base64 = str(shape.get("image_base64") or "").strip()
            if not image_base64:
                continue
            image_data_uri = f"data:image/png;base64,{image_base64}"
            normalized_blocks.append(
                {
                    "id": f"{slide_id}-img-block-{shape_idx + 1}",
                    "card_id": f"visual-{shape_idx + 1}",
                    "block_type": "image",
                    "type": "image",
                    "position": "center",
                    "content": {"url": image_data_uri},
                    "data": {"url": image_data_uri},
                }
            )
            normalized_elements.append(
                {
                    "id": f"{slide_id}-img-el-{shape_idx + 1}",
                    "type": "image",
                    "left": float(shape.get("left") or 0.0),
                    "top": float(shape.get("top") or 0.0),
                    "width": float(shape.get("width") or 0.0),
                    "height": float(shape.get("height") or 0.0),
                    "content": image_data_uri,
                    "imageUrl": image_data_uri,
                }
            )

        if not normalized_blocks:
            normalized_blocks = [
                {
                    "id": f"{slide_id}-title",
                    "card_id": "title",
                    "block_type": "title",
                    "type": "title",
                    "position": "top",
                    "content": title,
                },
                {
                    "id": f"{slide_id}-body",
                    "card_id": "body",
                    "block_type": "body",
                    "type": "body",
                    "position": "center",
                    "content": title,
                },
            ]
        normalized_blocks = _assign_layout_card_ids(layout_grid, normalized_blocks)

        payload_slides.append(
            {
                "id": slide_id,
                "slide_id": slide_id,
                "page_number": int(raw.get("page_number") or (idx + 1)),
                "slide_type": normalized_slide_type,
                "page_type": page_type,
                "subtype": (
                    "section"
                    if normalized_slide_type == "divider"
                    else str(raw.get("subtype") or page_type or "content")
                ),
                "layout_grid": layout_grid,
                "bg_style": str(raw.get("bg_style") or "light"),
                "title": title,
                "narration": str(raw.get("notes_for_designer") or raw.get("narration") or ""),
                "image_keywords": [title] if title else [],
                "blocks": normalized_blocks,
                "elements": normalized_elements,
                "shapes": raw.get("shapes") if isinstance(raw.get("shapes"), list) else [],
                "visual": raw.get("visual") if isinstance(raw.get("visual"), dict) else {},
                "render_path": str(raw.get("render_path") or "pptxgenjs"),
                "slide_layout_path": str(raw.get("slide_layout_path") or ""),
                "slide_layout_name": str(raw.get("slide_layout_name") or ""),
                "slide_master_path": str(raw.get("slide_master_path") or ""),
                "slide_theme_path": str(raw.get("slide_theme_path") or ""),
                "media_refs": raw.get("media_refs") if isinstance(raw.get("media_refs"), list) else [],
            }
        )

    theme = (
        reference_desc.get("theme")
        if isinstance(reference_desc.get("theme"), dict)
        else {}
    )
    out: Dict[str, Any] = {
        "title": str(reference_desc.get("title") or fallback_title or "Reference Deck"),
        "theme": {
            "palette": str(theme.get("palette") or "custom"),
            "style": str(theme.get("style") or "sharp"),
            "primary": str(theme.get("primary") or ""),
            "secondary": str(theme.get("secondary") or ""),
            "accent": str(theme.get("accent") or ""),
            "bg": str(theme.get("bg") or ""),
        },
        "anchors": (
            reference_desc.get("anchors")
            if isinstance(reference_desc.get("anchors"), list)
            else []
        ),
        "required_facts": (
            reference_desc.get("required_facts")
            if isinstance(reference_desc.get("required_facts"), list)
            else []
        ),
        "slides": payload_slides,
        "dimensions": (
            reference_desc.get("dimensions")
            if isinstance(reference_desc.get("dimensions"), dict)
            else {}
        ),
        "theme_color_map": (
            reference_desc.get("theme_color_map")
            if isinstance(reference_desc.get("theme_color_map"), dict)
            else {}
        ),
        "media_manifest": (
            reference_desc.get("media_manifest")
            if isinstance(reference_desc.get("media_manifest"), list)
            else []
        ),
        "theme_manifest": (
            reference_desc.get("theme_manifest")
            if isinstance(reference_desc.get("theme_manifest"), list)
            else []
        ),
        "master_layout_manifest": (
            reference_desc.get("master_layout_manifest")
            if isinstance(reference_desc.get("master_layout_manifest"), list)
            else []
        ),
        "fonts": reference_desc.get("fonts") if isinstance(reference_desc.get("fonts"), list) else [],
        "source_pptx_path": str(reference_desc.get("source_pptx_path") or ""),
    }
    return out


def _export_reference_reconstruct_locally(
    reference_desc: Dict[str, Any],
    *,
    timeout_sec: int = 300,
) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    generator_script = repo_root / "scripts" / "generate_ppt_from_desc.py"
    if not generator_script.exists():
        raise FileNotFoundError(f"reference reconstruct script not found: {generator_script}")

    use_source_aligned = _env_flag("PPT_REFERENCE_RECONSTRUCT_SOURCE_ALIGNED", "false")
    with tempfile.TemporaryDirectory(prefix="ppt-ref-reconstruct-") as temp_dir:
        temp_path = Path(temp_dir)
        input_json_path = temp_path / "reference_desc.json"
        output_pptx_path = temp_path / "reference_output.pptx"
        render_output_path = temp_path / "reference_render.json"
        input_json_path.write_text(
            json.dumps(reference_desc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        cmd = [
            sys.executable,
            str(generator_script),
            "--input",
            str(input_json_path),
            "--output",
            str(output_pptx_path),
            "--render-output",
            str(render_output_path),
            "--mode",
            "local",
            "--local-strategy",
            "reconstruct",
            "--reconstruct-template-shell",
            "off",
            "--reconstruct-source-aligned",
            ("on" if use_source_aligned else "off"),
        ]
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=max(60, int(timeout_sec)),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"reference_reconstruct_local_failed: {detail[:500]}")
        if not output_pptx_path.exists():
            raise RuntimeError("reference_reconstruct_local_failed: output pptx missing")

        render_spec: Dict[str, Any] = {}
        if render_output_path.exists():
            try:
                parsed = json.loads(render_output_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    render_spec = parsed
            except Exception:
                render_spec = {}

        return {
            "pptx_bytes": output_pptx_path.read_bytes(),
            "render_spec": render_spec,
            "generator_meta": {
                "generator_mode": "reference_reconstruct_local",
                "source_aligned": bool(use_source_aligned),
                "stdout": (result.stdout or "").strip()[:1000],
            },
            "generator_mode": "reference_reconstruct_local",
            "render_channel": "local",
            "input_payload": {
                "slides": (
                    reference_desc.get("slides")
                    if isinstance(reference_desc.get("slides"), list)
                    else []
                ),
            },
            "is_full_deck": True,
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

_ARCHETYPE_CATALOG = load_archetype_catalog()
_ARCHETYPE_ALLOWED = {
    str(item).strip().lower()
    for item in (_ARCHETYPE_CATALOG.get("archetypes") if isinstance(_ARCHETYPE_CATALOG, dict) else [])
    if str(item).strip()
}
if not _ARCHETYPE_ALLOWED:
    _ARCHETYPE_ALLOWED = {"thesis_assertion", "evidence_cards_3", "comparison_2col"}

_ARCHETYPE_ROLE_DEFAULTS = (
    _ARCHETYPE_CATALOG.get("role_defaults")
    if isinstance(_ARCHETYPE_CATALOG.get("role_defaults"), dict)
    else {"content": "thesis_assertion"}
)
_ARCHETYPE_LAYOUT_OVERRIDES = (
    _ARCHETYPE_CATALOG.get("layout_overrides")
    if isinstance(_ARCHETYPE_CATALOG.get("layout_overrides"), dict)
    else {}
)
_ARCHETYPE_SEMANTIC_OVERRIDES = (
    _ARCHETYPE_CATALOG.get("semantic_overrides")
    if isinstance(_ARCHETYPE_CATALOG.get("semantic_overrides"), dict)
    else {}
)


def _brand_placeholder_svg_data_uri(title: str = "Visual Context") -> str:
    safe = html.escape(str(title or "Visual Context"), quote=True)
    # Stable machine marker for placeholder detection. Do not localize.
    marker = "ppt-placeholder-image-v1"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        f"<desc>{marker}</desc>"
        '<rect width="1200" height="675" rx="28" fill="#0D1630" stroke="#1E335E" stroke-width="3"/>'
        '<rect x="56" y="54" width="8" height="34" rx="4" fill="#2F7BFF"/>'
        f'<text x="80" y="80" fill="#E8F0FF" font-size="36" font-family="Segoe UI, Arial" font-weight="700">{safe}</text>'
        '<text x="80" y="125" fill="#95A8CC" font-size="24" font-family="Segoe UI, Arial">illustrative visual</text>'
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
        candidate = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
        if candidate and _template_family_supports_slide(candidate, slide_type=st, layout_grid=layout):
            requested = candidate
    return resolve_template_for_slide(
        slide=slide if isinstance(slide, dict) else {},
        slide_type=st,
        layout_grid=layout,
        requested_template=requested,
        desired_density=str(slide.get("content_density") or "balanced"),
    )


def _infer_deck_template_family_from_rows(rows: List[Dict[str, Any]]) -> str:
    if not isinstance(rows, list) or not rows:
        return ""

    counts: Dict[str, int] = {}
    first_idx: Dict[str, int] = {}
    for idx, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        family = str(raw.get("template_family") or raw.get("template_id") or "").strip().lower()
        if family in {"", "auto"}:
            try:
                family = _resolve_template_family(raw)
            except Exception:
                family = ""
        if not family or family == "auto":
            continue
        counts[family] = counts.get(family, 0) + 1
        first_idx.setdefault(family, idx)

    if counts:
        return sorted(
            counts.items(),
            key=lambda item: (-int(item[1]), int(first_idx.get(item[0], 0))),
        )[0][0]

    for raw in rows:
        if not isinstance(raw, dict):
            continue
        st = str(raw.get("slide_type") or raw.get("page_type") or "content").strip().lower() or "content"
        layout = str(raw.get("layout_grid") or raw.get("layout") or "split_2").strip().lower() or "split_2"
        try:
            fallback = resolve_template_for_slide(
                slide=raw,
                slide_type=st,
                layout_grid=layout,
                requested_template="",
                desired_density=str(raw.get("content_density") or "balanced"),
            )
        except Exception:
            fallback = ""
        if fallback and fallback != "auto":
            return str(fallback).strip().lower()
    return ""


def _template_profiles(template_family: str) -> Dict[str, str]:
    return shared_template_profiles(template_family)


def _canonical_slide_type_for_template(slide_type: str) -> str:
    normalized = str(slide_type or "").strip().lower()
    if normalized in {"hero_1", "cover"}:
        return "cover"
    if normalized in {"table_of_contents", "contents", "toc"}:
        return "toc"
    if normalized in {"section", "section_divider", "divider"}:
        return "divider"
    if normalized in {"summary", "closing", "conclusion"}:
        return "summary"
    if normalized in {"timeline", "workflow"}:
        return "workflow"
    if normalized in {"comparison", "data"}:
        return normalized
    return "content"


def _is_terminal_template_family(template_family: str) -> bool:
    normalized = str(template_family or "").strip().lower()
    return normalized in {"hero_dark", "hero_tech_cover", "quote_hero_dark"}


def _template_family_supports_slide(
    template_family: str,
    *,
    slide_type: str,
    layout_grid: str,
) -> bool:
    family = str(template_family or "").strip().lower()
    if not family:
        return False
    try:
        cap = shared_template_capabilities(family)
    except Exception:
        return False
    supported_types = {
        str(item or "").strip().lower()
        for item in (cap.get("supported_slide_types") or [])
        if str(item or "").strip()
    }
    supported_layouts = {
        str(item or "").strip().lower()
        for item in (cap.get("supported_layouts") or [])
        if str(item or "").strip()
    }
    normalized_type = _canonical_slide_type_for_template(slide_type)
    normalized_layout = str(layout_grid or "").strip().lower()
    type_ok = normalized_type in supported_types if supported_types else True
    # Cover families often handle toc/divider variants with the same renderer.
    if not type_ok and normalized_type in {"toc", "divider", "summary"} and "cover" in supported_types:
        type_ok = True
    layout_ok = normalized_layout in supported_layouts if supported_layouts else True
    return bool(type_ok and layout_ok)


def _template_supports_block_type(
    template_family: str,
    *,
    block_type: str,
) -> bool:
    family = str(template_family or "").strip().lower()
    btype = str(block_type or "").strip().lower()
    if not family or not btype:
        return False
    try:
        cap = shared_template_capabilities(family)
    except Exception:
        return False
    supported = {
        str(item or "").strip().lower()
        for item in (cap.get("supported_block_types") or [])
        if str(item or "").strip()
    }
    return btype in supported


def _slide_requires_image_anchor(
    slide: Dict[str, Any],
    *,
    require_image_anchor: bool,
) -> bool:
    if not bool(require_image_anchor):
        return False
    slide_type = str(slide.get("slide_type") or "content").strip().lower() or "content"
    if slide_type in {"cover", "summary", "toc", "divider", "hero_1"}:
        return False
    layout_grid = str(slide.get("layout_grid") or slide.get("layout") or "split_2").strip().lower() or "split_2"
    family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
    if not family:
        family = _resolve_template_family(slide)
    if not family:
        return False
    if not _template_family_supports_slide(
        family,
        slide_type=slide_type,
        layout_grid=layout_grid,
    ):
        return False
    return _template_supports_block_type(family, block_type="image")


def _as_block_type(block: Dict[str, Any]) -> str:
    return str(block.get("block_type") or block.get("type") or "").strip().lower()


def _slide_page_role(slide: Dict[str, Any]) -> str:
    role = str(slide.get("page_role") or slide.get("slide_type") or "").strip().lower()
    if role in {"cover", "toc", "divider", "summary"}:
        return role
    return "content"


def _select_slide_archetype_plan(slide: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(slide.get("archetype_plan"), dict):
        existing = slide.get("archetype_plan")
        selected = str(existing.get("selected") or "").strip().lower()
        if selected in _ARCHETYPE_ALLOWED:
            confidence = float(existing.get("confidence") or 0.0)
            candidates = existing.get("candidates") if isinstance(existing.get("candidates"), list) else []
            if candidates:
                return {
                    "selected": selected,
                    "confidence": max(0.0, min(1.0, confidence)),
                    "candidates": candidates[:3],
                    "rerank_version": str(existing.get("rerank_version") or "v1"),
                }
    plan = select_slide_archetype(slide, top_k=3, rerank_window=6)
    selected = str(plan.get("selected") or "").strip().lower()
    if selected not in _ARCHETYPE_ALLOWED:
        role = _slide_page_role(slide)
        fallback = str(_ARCHETYPE_ROLE_DEFAULTS.get(role) or _ARCHETYPE_ROLE_DEFAULTS.get("content") or "thesis_assertion")
        selected = fallback if fallback in _ARCHETYPE_ALLOWED else "thesis_assertion"
        plan["selected"] = selected
    return {
        "selected": selected,
        "confidence": max(0.0, min(1.0, float(plan.get("confidence") or 0.0))),
        "candidates": plan.get("candidates") if isinstance(plan.get("candidates"), list) else [],
        "rerank_version": str(plan.get("rerank_version") or "v1"),
    }


def _choose_slide_archetype(slide: Dict[str, Any]) -> str:
    plan = _select_slide_archetype_plan(slide)
    selected = str(plan.get("selected") or "").strip().lower()
    return selected if selected in _ARCHETYPE_ALLOWED else "thesis_assertion"


def _row_block_text(block: Dict[str, Any]) -> str:
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


def _collect_slide_evidence(slide: Dict[str, Any], limit: int = 4) -> List[str]:
    strategy = slide.get("content_strategy")
    if isinstance(strategy, dict):
        evidence = strategy.get("evidence")
        if isinstance(evidence, list):
            values = [str(item or "").strip() for item in evidence if str(item or "").strip()]
            if values:
                return values[:limit]

    values: List[str] = []
    for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else []):
        if not isinstance(block, dict):
            continue
        block_type = _as_block_type(block)
        if block_type == "title":
            continue
        text = _row_block_text(block)
        if not text:
            continue
        values.append(text)
        if len(values) >= limit:
            break
    return values


def _infer_slide_title_text(slide: Dict[str, Any]) -> str:
    title = str(slide.get("title") or "").strip()
    if title:
        return title
    for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else []):
        if not isinstance(block, dict):
            continue
        if _as_block_type(block) != "title":
            continue
        text = _row_block_text(block)
        if text:
            return text
    return ""


def _collect_slide_data_points(slide: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else []):
        if not isinstance(block, dict):
            continue
        block_type = _as_block_type(block)
        if block_type not in {"chart", "kpi", "table"}:
            continue
        content = block.get("content") if isinstance(block.get("content"), dict) else {}
        if not isinstance(content, dict):
            content = {}
        points.append(
            {
                "block_type": block_type,
                "label": str(content.get("label") or content.get("title") or block.get("card_id") or "").strip(),
                "value": content.get("value"),
            }
        )
        if len(points) >= limit:
            break
    return points


def _infer_slide_media_intent(slide: Dict[str, Any]) -> str:
    keywords = slide.get("image_keywords")
    if isinstance(keywords, list):
        values = [str(item or "").strip() for item in keywords if str(item or "").strip()]
        if values:
            return " ".join(values[:3]).strip()
    semantic = str(
        slide.get("semantic_type")
        or slide.get("semantic_subtype")
        or slide.get("content_subtype")
        or slide.get("subtype")
        or ""
    ).strip()
    if semantic:
        return semantic
    title = str(slide.get("title") or "").strip()
    return title[:64] if title else "visual_context"


def _build_presentation_contract_v2(deck: Dict[str, Any]) -> Dict[str, Any]:
    slides = [
        slide for slide in (deck.get("slides") if isinstance(deck.get("slides"), list) else [])
        if isinstance(slide, dict)
    ]
    design_spec = deck.get("design_spec") if isinstance(deck.get("design_spec"), dict) else {}
    rows: List[Dict[str, Any]] = []
    for idx, slide in enumerate(slides):
        slide_id = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}").strip()
        inferred_title = _infer_slide_title_text(slide)
        archetype_plan = _select_slide_archetype_plan(slide)
        selected_archetype = str(archetype_plan.get("selected") or "thesis_assertion").strip().lower()
        row = {
            "slide_id": slide_id or f"slide-{idx + 1}",
            "page_role": _slide_page_role(slide),
            "archetype": selected_archetype,
            "archetype_confidence": float(archetype_plan.get("confidence") or 0.0),
            "archetype_candidates": (
                archetype_plan.get("candidates")
                if isinstance(archetype_plan.get("candidates"), list)
                else []
            )[:3],
            "archetype_plan": archetype_plan,
            "layout_grid": str(slide.get("layout_grid") or "split_2").strip().lower(),
            "render_path": str(slide.get("render_path") or "pptxgenjs").strip().lower(),
            "component_slots": [
                str((block or {}).get("card_id") or "").strip()
                for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else [])
                if isinstance(block, dict) and str((block or {}).get("card_id") or "").strip()
            ][:8]
            or ["title", "body"],
            "content_channel": {
                "title": inferred_title,
                "assertion": str(
                    (
                        slide.get("content_strategy")
                        if isinstance(slide.get("content_strategy"), dict)
                        else {}
                    ).get("assertion")
                    or inferred_title
                    or ""
                ).strip(),
                "evidence": _collect_slide_evidence(slide),
                "data_points": _collect_slide_data_points(slide),
                "media_intent": _infer_slide_media_intent(slide),
            },
            "visual_channel": {
                "layout": str(slide.get("layout_grid") or "split_2").strip().lower(),
                "render_path": str(slide.get("render_path") or "pptxgenjs").strip().lower(),
                "component_slots": [
                    str((block or {}).get("card_id") or "").strip()
                    for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else [])
                    if isinstance(block, dict) and str((block or {}).get("card_id") or "").strip()
                ][:8]
                or ["title", "body"],
                "animation_rhythm": str(slide.get("animation_rhythm") or "calm").strip().lower() or "calm",
            },
            "semantic_constraints": {
                "media_required": any(
                    _as_block_type(block) == "image"
                    for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else [])
                    if isinstance(block, dict)
                ),
                "chart_required": any(
                    _as_block_type(block) in {"chart", "kpi", "table"}
                    for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else [])
                    if isinstance(block, dict)
                ),
                "diagram_type": (
                    "workflow"
                    if any(
                        _as_block_type(block) in {"workflow", "diagram", "timeline"}
                        for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else [])
                        if isinstance(block, dict)
                    )
                    else "none"
                ),
            },
        }
        row["layout_solution"] = solve_slide_layout(
            slide,
            archetype=row["archetype"],
        )
        rows.append(row)

    return {
        "version": "v2",
        "deck_spec": {
            "topic": str(deck.get("title") or "Presentation"),
            "design_tokens": {
                "color": (
                    design_spec.get("colors")
                    if isinstance(design_spec.get("colors"), dict)
                    else {}
                ),
                "typography": (
                    design_spec.get("typography")
                    if isinstance(design_spec.get("typography"), dict)
                    else {}
                ),
                "spacing": (
                    design_spec.get("spacing")
                    if isinstance(design_spec.get("spacing"), dict)
                    else {}
                ),
            },
            "guardrails": {
                "token_only_mode": True,
                "max_text_only_slide_ratio": 0.2,
                "min_media_coverage_ratio": 0.7,
            },
        },
        "slides": rows,
    }


def _apply_layout_solution_actions(
    slides: List[Dict[str, Any]],
    contract_rows: List[Dict[str, Any]],
) -> Dict[str, int]:
    if not isinstance(slides, list) or not isinstance(contract_rows, list):
        return {"updated_slides": 0, "overflow_fixed": 0, "underflow_fixed": 0}
    slide_map: Dict[str, Dict[str, Any]] = {}
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        sid = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}").strip()
        if sid:
            slide_map[sid] = slide

    updated_slides = 0
    overflow_fixed = 0
    underflow_fixed = 0
    text_types = {"subtitle", "text", "body", "list", "quote", "comparison", "icon_text"}

    for row in contract_rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("slide_id") or "").strip()
        if not sid or sid not in slide_map:
            continue
        solution = row.get("layout_solution")
        if not isinstance(solution, dict):
            continue
        status = str(solution.get("status") or "").strip().lower()
        overflow_actions = (
            solution.get("overflow_actions")
            if isinstance(solution.get("overflow_actions"), list)
            else []
        )
        underflow_actions = (
            solution.get("underflow_actions")
            if isinstance(solution.get("underflow_actions"), list)
            else []
        )
        metrics = solution.get("metrics") if isinstance(solution.get("metrics"), dict) else {}
        slide = slide_map[sid]
        blocks = slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
        blocks = [dict(item) for item in blocks if isinstance(item, dict)]
        changed = False

        if status == "overflow":
            max_text_blocks = max(1, int(metrics.get("max_text_blocks") or 4))
            if "compress_text" in overflow_actions:
                for block in blocks:
                    bt = _as_block_type(block)
                    if bt not in text_types:
                        continue
                    text = _extract_block_text(block)
                    if len(text) <= 180:
                        continue
                    block["content"] = text[:177].rstrip() + "..."
                    changed = True
            # canonical action: downgrade_layout_density
            # compatibility alias: split_slide (legacy runs)
            if "downgrade_layout_density" in overflow_actions or "split_slide" in overflow_actions:
                title_blocks = [b for b in blocks if _as_block_type(b) == "title"]
                text_blocks = [b for b in blocks if _as_block_type(b) in text_types]
                other_blocks = [b for b in blocks if _as_block_type(b) not in (text_types | {"title"})]
                capped_text = text_blocks[:max_text_blocks]
                if len(capped_text) < len(text_blocks):
                    changed = True
                blocks = [*title_blocks[:1], *capped_text, *other_blocks]
            if changed:
                overflow_fixed += 1

        elif status == "underflow":
            if "add_visual_anchor" in underflow_actions:
                slide_type = str(slide.get("slide_type") or "content").strip().lower() or "content"
                has_visual_anchor = any(_as_block_type(block) in _VISUAL_BLOCK_TYPES for block in blocks)
                if slide_type == "content" and not has_visual_anchor and _prefers_text_first_visual_fallback(slide):
                    title_text = str(slide.get("title") or slide.get("slide_id") or "").strip()
                    prefer_zh = _prefer_zh(title_text, slide.get("narration"), slide.get("speaker_notes"))
                    keypoints = _extract_slide_keypoints(slide, title_text) or [title_text]
                    table_rows = _table_data_from_keypoints(keypoints, prefer_zh=prefer_zh)
                    blocks.append(
                        {
                            "block_type": "table",
                            "card_id": f"{sid}-solver-table",
                            "position": "right",
                            "content": {"table_rows": table_rows},
                            "data": {"table_rows": table_rows, "source": "layout_solver"},
                        }
                    )
                    changed = True
                elif slide_type == "content" and not has_visual_anchor:
                    blocks.append(
                        {
                            "block_type": "image",
                            "card_id": f"{sid}-solver-image",
                            "position": "right",
                            "content": {
                                "query": str(slide.get("title") or "business visual"),
                                "source": "layout_solver",
                            },
                        }
                    )
                    changed = True
            if changed:
                underflow_fixed += 1

        if changed:
            slide["blocks"] = blocks
            slide["layout_solver_applied"] = {
                "status": status,
                "overflow_actions": overflow_actions,
                "underflow_actions": underflow_actions,
            }
            updated_slides += 1

    return {
        "updated_slides": updated_slides,
        "overflow_fixed": overflow_fixed,
        "underflow_fixed": underflow_fixed,
    }


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
_PLACEHOLDER_TEXT_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"[?？]{2,}"),
    re.compile(r"\b(?:todo|tbd|placeholder|lorem ipsum)\b", flags=re.IGNORECASE),
    re.compile(r"\b(?:xxxx|xxx)\b", flags=re.IGNORECASE),
    re.compile(r"\b(?:item|module|section|chapter|part|region|highlight)\s*\d+\b", flags=re.IGNORECASE),
    re.compile(r"\bstep\s*\d+\b", flags=re.IGNORECASE),
    re.compile(r"\boption\s*[a-z]\b", flags=re.IGNORECASE),
    re.compile(r"\b(?:table of contents|monitoring view|thank you)\b", flags=re.IGNORECASE),
    re.compile(r"^\[(?:xls|xlsx|pdf|doc|docx|ppt|pptx)\]\s*", flags=re.IGNORECASE),
    re.compile(r"(?:已编辑汇总|编辑汇总)\s*\d+\s*册"),
    re.compile(r"待补充|请填写|占位符"),
]
_PLACEHOLDER_LONE_TOKENS = {
    "slide",
    "topic",
    "focus",
    "tbc",
    "todo",
    "tbd",
    "placeholder",
    "thank you",
    "table of contents",
    "monitoring view",
}


def _normalize_text_key(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%+.-]", "", lowered)


def _split_topic_focus(topic: str, *, prefer_zh: bool) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", str(topic or "").strip())
    if not text:
        return ("slide" if not prefer_zh else "主题", "")
    if prefer_zh:
        parts = re.split(r"[：:]", text, maxsplit=1)
        subject = str(parts[0] if parts else text).strip()
        focus = str(parts[1] if len(parts) > 1 else "").strip()
        subject = re.sub(r"^(解码|理解|认识|解析|探究)\s*", "", subject).strip() or subject
        subject = subject[:28] if subject else "主题"
        focus = focus[:40]
        return subject, focus
    parts = re.split(r"[:|-]", text, maxsplit=1)
    subject = str(parts[0] if parts else text).strip()[:40] or "topic"
    focus = str(parts[1] if len(parts) > 1 else "").strip()[:56]
    return subject, focus


def _collapse_redundant_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"([\u4e00-\u9fff]{4,})(?:[，,。；;\s]+\1)+", r"\1", cleaned)
    cleaned = re.sub(
        r"\b([A-Za-z]+(?:\s+[A-Za-z]+){1,4})\s+\1\b",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _looks_placeholder_like_text(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    lowered = re.sub(r"\s+", " ", value).strip().lower()
    if lowered in _PLACEHOLDER_LONE_TOKENS:
        return True
    if any(pattern.search(value) for pattern in _PLACEHOLDER_TEXT_PATTERNS):
        # Keep real process expressions such as "Step 1: drafting bill".
        if re.search(r"\bstep\s*\d+\s*[:：-]\s*[A-Za-z\u4e00-\u9fff]{2,}", value, flags=re.IGNORECASE):
            return False
        if re.search(r"\bsection\s*\d+\s*[:：-]\s*[A-Za-z\u4e00-\u9fff]{2,}", value, flags=re.IGNORECASE):
            return False
        return True
    return False


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
        for key in ("title", "body", "text", "label", "caption", "description", "query", "subject"):
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


def _looks_non_text_payload_fragment(text: str) -> bool:
    value = str(text or "").strip().lower()
    if not value:
        return False
    if value.startswith(("http://", "https://", "data:image/", "image/")):
        return True
    if "data:image/" in value or "base64," in value:
        return True
    if len(value) >= 240 and re.search(r"[a-z0-9+/=]{120,}", value):
        return True
    return False


def _collect_text_fragments_from_value(value: Any, *, max_items: int = 24) -> List[str]:
    """Collect human-readable text fragments from nested values."""
    out: List[str] = []
    queue: List[Any] = [value]
    while queue and len(out) < max_items:
        current = queue.pop(0)
        if isinstance(current, str):
            text = str(current or "").strip()
            if text:
                if _looks_mojibake(text, allow_repair=False):
                    continue
                if _looks_non_text_payload_fragment(text):
                    continue
                out.append(text)
            continue
        if isinstance(current, (int, float)) and not isinstance(current, bool):
            out.append(str(current))
            continue
        if isinstance(current, list):
            for item in current[:max_items]:
                queue.append(item)
            continue
        if isinstance(current, dict):
            for key in (
                "title",
                "name",
                "label",
                "text",
                "content",
                "summary",
                "description",
                "value",
                "caption",
                "body",
                "assertion",
                "evidence",
                "note",
                "notes",
                "topic",
                "keyword",
                "keywords",
                "point",
                "points",
            ):
                if key in current:
                    queue.append(current.get(key))
            continue
    return out


def _sanitize_placeholder_text(text: str, *, prefer_zh: bool) -> str:
    cleaned = _normalize_unicode_text(text)
    if not cleaned:
        return cleaned
    cleaned = re.sub(r"^\[(?:xls|xlsx|pdf|doc|docx|ppt|pptx)\]\s*", "", cleaned, flags=re.IGNORECASE)
    # Normalize common masked placeholders such as 400-XXX-XXXX.
    cleaned = re.sub(r"(?<![0-9A-Za-z])X{3,}(?![0-9A-Za-z])", lambda m: "0" * len(m.group(0)), cleaned, flags=re.IGNORECASE)
    replacements = [
        (re.compile(r"[?？]{2,}"), ""),
        (re.compile(r"\bxxxx\b", flags=re.IGNORECASE), ""),
        (re.compile(r"\b(?:todo|tbd|placeholder)\b", flags=re.IGNORECASE), ""),
        (
            re.compile(
                r"\b(?:item|module|section|chapter|part|region|highlight|layer|perspective|scenario|node)\s*\d+\b",
                flags=re.IGNORECASE,
            ),
            "",
        ),
        (re.compile(r"\bstep\s*\d+\b", flags=re.IGNORECASE), ""),
        (re.compile(r"\boption\s*[a-z]\b", flags=re.IGNORECASE), ""),
        (re.compile(r"\b(?:table of contents|monitoring view|thank you)\b", flags=re.IGNORECASE), ""),
        (re.compile(r"待补充|请填写|占位符"), ""),
    ]
    for pattern, target in replacements:
        cleaned = pattern.sub(target, cleaned)
    if re.search(r"(?:已编辑汇总|编辑汇总)\s*\d+\s*册", cleaned):
        return ""
    if re.fullmatch(r"\d{6,}", cleaned):
        return ""
    if re.search(r"[A-Za-z]", cleaned) and re.search(r"[\u4e00-\u9fff]", cleaned):
        latin_count = len(re.findall(r"[A-Za-z]", cleaned))
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", cleaned))
        if cjk_count > 0 and cjk_count <= max(4, int(latin_count * 0.18)):
            cleaned = re.sub(r"[\u4e00-\u9fff]+", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -:;,.，。；")
    cleaned = _collapse_redundant_text(cleaned)
    if _looks_mojibake(cleaned, allow_repair=False):
        return ""
    if _looks_placeholder_like_text(cleaned):
        return ""
    return cleaned


def _visual_units_of_text(text: str) -> float:
    units = 0.0
    for ch in str(text or ""):
        if "\u4e00" <= ch <= "\u9fff":
            units += 1.7
        elif ch.isspace():
            units += 0.45
        elif ch in ",.;:!?，。；：！？":
            units += 0.55
        else:
            units += 1.0
    return units


def _clip_text_by_visual_units(text: str, *, max_units: float, suffix: str) -> str:
    if _visual_units_of_text(text) <= max_units:
        return text
    budget = max(2.0, float(max_units) - _visual_units_of_text(suffix))
    out_chars: List[str] = []
    used = 0.0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            step = 1.7
        elif ch.isspace():
            step = 0.45
        elif ch in ",.;:!?，。；：！？":
            step = 0.55
        else:
            step = 1.0
        if (used + step) > budget:
            break
        out_chars.append(ch)
        used += step
    clipped = "".join(out_chars).rstrip(" ,，；;。.!?！？")
    return f"{clipped}{suffix}" if clipped else suffix


def _clip_text_for_visual_budget(
    text: str,
    *,
    prefer_zh: bool,
    slide_type: str,
    role: str,
) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return ""
    normalized_slide_type = str(slide_type or "").strip().lower()
    normalized_role = str(role or "body").strip().lower()
    if normalized_role == "title":
        limit = 34 if prefer_zh else 72
        if normalized_slide_type in {"cover", "summary", "toc", "divider", "hero_1"}:
            limit = 42 if prefer_zh else 90
        # Remove repeated segments in long titles to prevent clipping/crowding.
        title_parts = [part.strip() for part in re.split(r"[：:|-]", cleaned) if part.strip()]
        if len(title_parts) >= 2:
            deduped_parts: List[str] = []
            seen_keys: set[str] = set()
            for part in title_parts:
                key = _normalize_text_key(part)
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                deduped_parts.append(part)
            if deduped_parts:
                cleaned = "：".join(deduped_parts) if prefer_zh else ": ".join(deduped_parts)
    elif normalized_role == "subtitle":
        limit = 40 if prefer_zh else 116
    else:
        limit = 58 if prefer_zh else 176
    if _visual_units_of_text(cleaned) <= float(limit):
        return cleaned
    parts = [str(part or "").strip() for part in re.split(r"[；;。.!?！？\n]+", cleaned) if str(part or "").strip()]
    candidate = parts[0] if parts else cleaned
    if len(parts) >= 2 and _visual_units_of_text(candidate) < float(limit) * 0.62:
        joiner = "，" if prefer_zh else ", "
        candidate = f"{candidate}{joiner}{parts[1]}"
    suffix = "…" if prefer_zh else "..."
    return _clip_text_by_visual_units(candidate, max_units=float(limit), suffix=suffix)


def _extract_slide_keypoints(slide: Dict[str, Any], title_text: str) -> List[str]:
    tokens: List[str] = []

    def _append_tokens(value: Any) -> None:
        for fragment in _collect_text_fragments_from_value(value):
            cleaned = str(fragment or "").strip()
            if cleaned:
                tokens.append(cleaned)

    _append_tokens(title_text)
    for key in (
        "subtitle",
        "narration",
        "speaker_notes",
        "assertion",
        "evidence",
        "summary",
        "topic",
        "core_message",
        "visual_anchor",
        "section_title",
        "description",
    ):
        _append_tokens(slide.get(key))
    for key in (
        "image_keywords",
        "key_data_points",
        "key_takeaways",
        "required_facts",
        "anchors",
        "highlights",
        "domain_terms",
        "keywords",
        "bullet_points",
    ):
        _append_tokens(slide.get(key))
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        block_type = _as_block_type(block)
        _append_tokens(_extract_block_text(block))
        if block_type == "image":
            data = block.get("data") if isinstance(block.get("data"), dict) else {}
            _append_tokens(data.get("keywords"))
            _append_tokens(data.get("semantic_query"))
            continue
        _append_tokens(block.get("content"))
        _append_tokens(block.get("data"))

    phrases: List[str] = []
    seen = set()
    prefer_zh = _prefer_zh(title_text, str(slide.get("narration") or ""))
    min_phrase_len = 2 if prefer_zh else 3
    max_phrase_len = 28 if prefer_zh else 64
    for token in tokens:
        for part in _SPLIT_TEXT_RE.split(str(token or "")):
            phrase = str(part or "").strip()
            if len(phrase) < min_phrase_len:
                continue
            if len(phrase) > max_phrase_len:
                phrase = phrase[:max_phrase_len].rstrip(" ,，；;。")
            key = _normalize_text_key(phrase)
            if not key or key in seen or _is_low_signal_point_text(phrase):
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


def _build_input_derived_point_pool(
    slide: Dict[str, Any],
    *,
    title_text: str,
    prefer_zh: bool,
    slide_type: str,
) -> List[str]:
    pool: List[str] = []
    seen = set()
    subject, focus = _split_topic_focus(title_text, prefer_zh=prefer_zh)
    source_points = [*(_extract_slide_keypoints(slide, title_text) or []), focus, subject, title_text]
    for raw in source_points:
        cleaned = _sanitize_placeholder_text(str(raw or "").strip(), prefer_zh=prefer_zh)
        if not cleaned:
            continue
        clipped = _clip_text_for_visual_budget(
            cleaned,
            prefer_zh=prefer_zh,
            slide_type=slide_type or "content",
            role="body",
        )
        key = _normalize_text_key(clipped)
        if not key or key in seen:
            continue
        seen.add(key)
        pool.append(clipped)
        if len(pool) >= 20:
            break
    return pool


def _pick_input_derived_point(
    *,
    point_pool: List[str],
    title_text: str,
    prefer_zh: bool,
    index: int,
    title_key: str,
    existing_keys: Optional[set[str]] = None,
    slide_type: str = "content",
) -> str:
    blocked = {str(key or "").strip() for key in (existing_keys or set()) if str(key or "").strip()}
    if title_key:
        blocked.add(str(title_key or "").strip())
    for offset in range(len(point_pool)):
        candidate = str(point_pool[(int(index) + offset) % len(point_pool)] or "").strip()
        key = _normalize_text_key(candidate)
        if candidate and key and key not in blocked:
            return candidate

    base = ""
    for candidate in point_pool:
        normalized = str(candidate or "").strip()
        if normalized:
            base = normalized
            break
    if not base:
        base = _clip_text_for_visual_budget(
            _sanitize_placeholder_text(str(title_text or "").strip(), prefer_zh=prefer_zh) or "slide",
            prefer_zh=prefer_zh,
            slide_type=slide_type or "content",
            role="body",
        )
    seq = max(1, int(index) + 1)
    if prefer_zh:
        suffixes = ["关键点", "机制", "案例", "影响", "结论", "行动建议"]
        synthetic_candidates = [f"{base}{suffixes[(seq - 1 + off) % len(suffixes)]}" for off in range(len(suffixes))]
        synthetic_candidates.extend([f"{base}要点", f"{base}启示"])
    else:
        suffixes = ["Key Point", "Mechanism", "Case", "Impact", "Conclusion", "Next Step"]
        synthetic_candidates = [f"{suffixes[(seq - 1 + off) % len(suffixes)]}: {base}" for off in range(len(suffixes))]
        synthetic_candidates.extend([f"Core idea: {base}", f"Action: {base}"])
    for candidate in synthetic_candidates:
        key = _normalize_text_key(candidate)
        if key and key not in blocked:
            return candidate
    return base


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
        base_label = labels[0] if labels else ("指标" if prefer_zh else "Item")
        while len(labels) < 3:
            idx = len(labels) + 1
            candidate = f"{base_label}{idx}" if prefer_zh else f"{base_label} {idx}"
            if candidate in labels:
                candidate = f"{base_label}#{idx}"
            labels.append(candidate)
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
        points.append(float(len(points) + 1))

    return {
        "labels": labels,
        "datasets": [
            {
                "label": "关键指标" if prefer_zh else "Key metric",
                "data": points[: len(labels)],
            }
        ],
    }


def _table_data_from_keypoints(
    keypoints: List[str],
    *,
    prefer_zh: bool,
) -> List[List[str]]:
    rows: List[List[str]] = [["序号", "要点"] if prefer_zh else ["No.", "Point"]]
    seen = set()
    for idx, item in enumerate(keypoints):
        text = str(item or "").strip()
        key = _normalize_text_key(text)
        if not text or not key or key in seen or _is_low_signal_point_text(text):
            continue
        seen.add(key)
        rows.append([str(idx + 1), text[:42]])
        if len(rows) >= 5:
            break
    if len(rows) == 1:
        rows.append(["1", "核心信息" if prefer_zh else "Key idea"])
    return rows


def _is_synthetic_ordinal_chart_block(block: Dict[str, Any]) -> bool:
    if str(block.get("block_type") or "").strip().lower() != "chart":
        return False
    payload = block.get("data") if isinstance(block.get("data"), dict) else block.get("content")
    if not isinstance(payload, dict):
        return False
    datasets = payload.get("datasets") if isinstance(payload.get("datasets"), list) else []
    first = datasets[0] if datasets and isinstance(datasets[0], dict) else {}
    values = first.get("data") if isinstance(first.get("data"), list) else []
    if len(values) < 3:
        return False
    for idx, value in enumerate(values):
        try:
            numeric = float(value)
        except Exception:
            return False
        if numeric != float(idx + 1):
            return False
    return True


_DATA_SEMANTIC_HINTS = {
    "kpi",
    "chart",
    "data",
    "metric",
    "trend",
    "统计",
    "数据",
    "指标",
    "占比",
    "增长",
}
_PROCESS_SEMANTIC_HINTS = {
    "workflow",
    "process",
    "timeline",
    "pipeline",
    "step",
    "phase",
    "流程",
    "步骤",
    "阶段",
    "立法",
    "程序",
}
_EDUCATION_SEMANTIC_HINTS = {
    "education",
    "classroom",
    "lesson",
    "teaching",
    "learning",
    "课程",
    "课堂",
    "教学",
    "高中",
    "学生",
}

_LOW_SIGNAL_POINT_KEYS = {
    "text",
    "trend",
    "roles",
    "role",
    "case",
    "impact",
    "summary",
    "content",
    "topic",
    "body",
    "list",
    "chart",
    "kpi",
    "workflow",
    "diagram",
    "title",
    "subtitle",
    "toc",
    "agenda",
    "hero",
}


def _is_low_signal_point_text(text: str) -> bool:
    key = _normalize_text_key(text)
    if not key:
        return True
    if key in _LOW_SIGNAL_POINT_KEYS:
        return True
    if re.fullmatch(r"[0-9]+", key):
        return True
    return False


def _prefers_text_first_visual_fallback(slide: Dict[str, Any]) -> bool:
    quality_profile = str(slide.get("quality_profile") or "").strip().lower()
    deck_profile = str(slide.get("deck_archetype_profile") or "").strip().lower()
    theme_recipe = str(slide.get("theme_recipe") or "").strip().lower()
    blob = " ".join(
        [
            str(slide.get("title") or ""),
            str(slide.get("narration") or ""),
            str(slide.get("purpose") or ""),
            str(slide.get("audience") or ""),
        ]
    ).lower()
    if quality_profile == "training_deck":
        return True
    if deck_profile == "education_textbook":
        return True
    if theme_recipe == "classroom_soft":
        return True
    return any(token in blob for token in _EDUCATION_SEMANTIC_HINTS)


def _infer_visual_semantic_mode(
    *,
    semantic_text: str,
    keypoints: List[str],
    numeric_values: List[float],
) -> str:
    blob = " ".join([str(semantic_text or ""), *[str(item or "") for item in keypoints[:4]]]).lower()
    has_data_hint = any(token in blob for token in _DATA_SEMANTIC_HINTS)
    has_process_hint = any(token in blob for token in _PROCESS_SEMANTIC_HINTS)
    has_edu_hint = any(token in blob for token in _EDUCATION_SEMANTIC_HINTS)
    has_numeric_signal = len([v for v in numeric_values if abs(float(v)) > 1e-6]) >= 2
    # Process semantics should win over weak numeric signals (for example:
    # timeline slides with years should not be forced into chart mode).
    if has_process_hint and not has_data_hint:
        return "process"
    if has_data_hint:
        return "data"
    if has_numeric_signal and not has_process_hint:
        return "data"
    if has_process_hint:
        return "process"
    if has_edu_hint:
        return "education"
    return "general"


def _make_visual_contract_block(
    *,
    preferred_types: List[str],
    keypoints: List[str],
    numeric_values: List[float],
    prefer_zh: bool,
    semantic_text: str = "",
    card_id: str,
    position: str,
) -> Dict[str, Any]:
    requested = [str(item or "").strip().lower() for item in preferred_types if str(item or "").strip()]
    requested_set = set(requested)
    label = keypoints[0] if keypoints else ("核心指标" if prefer_zh else "Key metric")
    education_like = any(token in str(semantic_text or "").lower() for token in ("classroom", "training", "education", "课程", "课堂", "教学", "培训", "education_textbook"))

    known_types = {"image", "workflow", "diagram", "kpi", "chart", "table"}
    target_type = next((item for item in requested if item in known_types), "")
    semantic_mode = _infer_visual_semantic_mode(
        semantic_text=semantic_text,
        keypoints=keypoints,
        numeric_values=numeric_values,
    )
    if not target_type:
        if semantic_mode == "data":
            target_type = "kpi" if "kpi" in requested_set else ("chart" if "chart" in requested_set else "table")
        elif semantic_mode == "process":
            target_type = "workflow"
        elif "diagram" in requested_set or semantic_mode == "process":
            target_type = "diagram"
        elif "image" in requested_set:
            target_type = "image"
        elif semantic_mode == "education":
            target_type = "table"
        else:
            target_type = "chart" if numeric_values else "image"

    if education_like and not numeric_values:
        if semantic_mode == "process":
            target_type = "workflow"
        else:
            target_type = "table"

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
    if target_type == "kpi" and not numeric_values:
        if semantic_mode == "process":
            target_type = "workflow"
        elif semantic_mode == "education":
            target_type = "table"
        else:
            target_type = "chart"
    if target_type == "chart" and not numeric_values:
        if semantic_mode == "process":
            target_type = "workflow"
        elif semantic_mode == "education":
            target_type = "table"
    if target_type == "table":
        table_rows = _table_data_from_keypoints(keypoints, prefer_zh=prefer_zh)
        return {
            "block_type": "table",
            "card_id": card_id,
            "position": position,
            "content": {"table_rows": table_rows, "source_type": "synthetic_table"},
            "data": {"table_rows": table_rows, "source_type": "synthetic_table"},
            "emphasis": keypoints[:2] or [label[:14]],
        }
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

    if target_type in {"workflow", "diagram"}:
        steps = keypoints[:4]
        if len(steps) < 3:
            seed_steps = _dedup_strings([*steps, label], limit=4)
            while len(seed_steps) < 3:
                idx = len(seed_steps) + 1
                seed = str(label or ("步骤" if prefer_zh else "Step")).strip() or ("步骤" if prefer_zh else "Step")
                seed_steps.append(f"{seed}{idx}" if prefer_zh else f"{seed} {idx}")
            steps = seed_steps[:4]
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


def _normalize_quality_text_key(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%+.-]", "", lowered)


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


def _collect_strict_contract_issues(
    *,
    slide: Dict[str, Any],
    blocks: List[Dict[str, Any]],
    min_content_blocks: int,
    blank_area_max_ratio: float,
    require_image_anchor: bool,
) -> List[str]:
    issues: List[str] = []
    slide_type = str(slide.get("slide_type") or "").strip().lower()
    terminal_slide = slide_type in {"cover", "summary", "toc", "divider", "hero_1"}
    if terminal_slide:
        return issues
    image_anchor_required = _slide_requires_image_anchor(
        slide,
        require_image_anchor=require_image_anchor,
    )
    text_first_contract = _prefers_text_first_visual_fallback(slide)

    has_title = any(_as_block_type(block) == "title" for block in blocks)
    has_body_or_list = any(_as_block_type(block) in {"body", "list"} for block in blocks)
    has_anchor = any(
        _as_block_type(block) in {"image", "chart", "kpi", "workflow", "diagram", "table"}
        for block in blocks
    )
    has_image_anchor = _has_image_block(blocks)
    if not has_title:
        issues.append("missing_title_block")
    if not has_body_or_list:
        issues.append("missing_body_or_list_block")
    if not has_anchor and not text_first_contract:
        issues.append("missing_visual_anchor_block")
    if image_anchor_required and not has_image_anchor:
        issues.append("missing_image_anchor_block")
    title_text = _sanitize_placeholder_text(str(slide.get("title") or "").strip(), prefer_zh=_prefer_zh(str(slide.get("title") or "")))
    if title_text and _looks_placeholder_like_text(title_text):
        issues.append("placeholder_title")

    whitelist = [
        str(item or "").strip().lower()
        for item in (slide.get("template_family_whitelist") or [])
        if str(item or "").strip()
    ] if isinstance(slide.get("template_family_whitelist"), list) else []
    resolved_template = ""
    slide_type_hint = str(slide.get("slide_type") or "content").strip().lower() or "content"
    layout_hint = str(slide.get("layout_grid") or slide.get("layout") or "split_2").strip().lower() or "split_2"
    for candidate in whitelist:
        if _template_family_supports_slide(candidate, slide_type=slide_type_hint, layout_grid=layout_hint):
            resolved_template = candidate
            break
    if not resolved_template:
        resolved_template = _resolve_template_family({**slide, "blocks": blocks})
    profiles = _template_profiles(resolved_template)
    contract = shared_contract_profile(str(profiles.get("contract_profile") or "default"))
    contract_min_text = max(0, int(contract.get("min_text_blocks") or 0))
    contract_min_visual = max(0, int(contract.get("min_visual_blocks") or 0))
    contract_visual_types = {
        str(item or "").strip().lower()
        for item in (contract.get("visual_anchor_types") or [])
        if str(item or "").strip()
    }
    if not contract_visual_types:
        contract_visual_types = set(_VISUAL_BLOCK_TYPES)

    required_groups = [
        [str(item or "").strip().lower() for item in group if str(item or "").strip()]
        for group in (contract.get("required_one_of_groups") or [])
        if isinstance(group, list)
    ]
    for group in required_groups:
        if not group:
            continue
        visual_only_group = all(str(item or "").strip().lower() in set(_VISUAL_BLOCK_TYPES) for item in group)
        if visual_only_group and text_first_contract:
            continue
        if not any(_as_block_type(block) in set(group) for block in blocks):
            issues.append("missing_required_group:" + "|".join(group))

    text_non_visual_count = len(
        [
            b
            for b in blocks
            if _as_block_type(b) in _TEXTUAL_BLOCK_TYPES
            and _as_block_type(b) != "title"
            and _as_block_type(b) not in contract_visual_types
        ]
    )
    visual_count = len([b for b in blocks if _as_block_type(b) in contract_visual_types])
    effective_min_text = contract_min_text
    if contract_min_text > 0 and visual_count > contract_min_visual:
        reduction = max(0, visual_count - contract_min_visual)
        effective_min_text = max(1, contract_min_text - reduction)
    if text_non_visual_count < effective_min_text:
        issues.append(f"insufficient_text_blocks:{text_non_visual_count}<{effective_min_text}")
    if visual_count < contract_min_visual and not text_first_contract:
        issues.append(f"insufficient_visual_blocks:{visual_count}<{contract_min_visual}")

    layout = str(slide.get("layout_grid") or slide.get("layout") or "").strip().lower()
    layout_capacity = int(_LAYOUT_CARD_COUNTS.get(layout, 0))
    non_title_count = len([b for b in blocks if _as_block_type(b) != "title"])
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
    if non_title_count < target_non_title:
        issues.append(f"insufficient_non_title_blocks:{non_title_count}<{target_non_title}")

    for block in blocks:
        btype = _as_block_type(block)
        if btype in {"title", "body", "list", "quote", "icon_text", "subtitle", "workflow", "diagram"}:
            text_value = _sanitize_placeholder_text(
                str(_extract_block_text(block) or "").strip(),
                prefer_zh=_prefer_zh(str(slide.get("title") or ""), str(_extract_block_text(block) or "")),
            )
            if text_value and _looks_placeholder_like_text(text_value):
                issues.append(f"placeholder_text_block:{btype}")
                break
    for block in blocks:
        if _as_block_type(block) != "kpi":
            continue
        payload = block.get("data")
        if not isinstance(payload, dict) and isinstance(block.get("content"), dict):
            payload = block.get("content")
        payload = payload if isinstance(payload, dict) else {}
        number = _to_float(payload.get("number"), None)
        if number is None or abs(float(number)) < 1e-6:
            issues.append("invalid_kpi_payload")
            break

    return issues


def _ensure_content_contract(
    slide: Dict[str, Any],
    *,
    min_content_blocks: int = 2,
    blank_area_max_ratio: float = 0.45,
    require_image_anchor: bool = False,
    strict_contract: bool = False,
) -> Dict[str, Any]:
    out = dict(slide)
    if not str(out.get("content_density") or "").strip():
        out["content_density"] = "dense" if int(min_content_blocks or 2) >= 3 else "balanced"
    slide_type = str(out.get("slide_type") or "").strip().lower()
    terminal_slide = slide_type in {"cover", "summary", "toc", "divider", "hero_1"}
    image_anchor_required = _slide_requires_image_anchor(
        out,
        require_image_anchor=require_image_anchor,
    )

    blocks = out.get("blocks")
    if not isinstance(blocks, list):
        blocks = []
    fixed: List[Dict[str, Any]] = [dict(b) for b in blocks if isinstance(b, dict)]
    fixed = _dedupe_blocks(fixed)

    title_block_text = ""
    for block in fixed:
        if _as_block_type(block) != "title":
            continue
        title_block_text = _sanitize_placeholder_text(
            str(_extract_block_text(block) or "").strip(),
            prefer_zh=_prefer_zh(str(_extract_block_text(block) or ""), out.get("narration"), *(out.get("image_keywords") or [])),
        )
        if title_block_text:
            break

    title_text = str(title_block_text or out.get("title") or "").strip()
    if not title_text:
        title_text = str(out.get("slide_id") or out.get("page_role") or out.get("archetype") or "").strip()
    if not title_text:
        title_text = "slide"
    title_key = _normalize_text_key(title_text)
    prefer_zh = _prefer_zh(title_text, out.get("narration"), *(out.get("image_keywords") or []))
    title_text = _sanitize_placeholder_text(title_text, prefer_zh=prefer_zh)
    topic_hint = ""
    raw_keywords = out.get("image_keywords")
    if isinstance(raw_keywords, list):
        for item in raw_keywords:
            candidate = str(item or "").strip()
            if candidate:
                topic_hint = candidate
                break
    if not topic_hint:
        topic_hint = str(out.get("topic") or "").strip()
    if topic_hint and title_text:
        topic_relevance = _topic_relevance_score(
            topic=topic_hint,
            title=title_text,
            snippet=str(out.get("narration") or ""),
            domain_terms=[],
            required_facts=[],
        )
        title_is_unreliable = (
            _looks_placeholder_like_text(title_text)
            or _looks_mojibake(title_text, allow_repair=False)
            or len(_normalize_text_key(title_text)) < 6
        )
        if title_is_unreliable and topic_relevance < 0.08:
            topic_title = _sanitize_placeholder_text(topic_hint, prefer_zh=prefer_zh)
            if topic_title:
                title_text = topic_title
    title_text = _clip_text_for_visual_budget(
        title_text,
        prefer_zh=prefer_zh,
        slide_type=slide_type,
        role="title",
    )
    title_key = _normalize_text_key(title_text)
    out["title"] = title_text
    if str(out.get("narration") or "").strip():
        narration_text = _sanitize_placeholder_text(str(out.get("narration") or ""), prefer_zh=prefer_zh)
        out["narration"] = _clip_text_for_visual_budget(
            narration_text,
            prefer_zh=prefer_zh,
            slide_type=slide_type,
            role="body",
        )
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
                cleaned_text = _sanitize_placeholder_text(str(el.get("content") or ""), prefer_zh=prefer_zh)
                el["content"] = _clip_text_for_visual_budget(
                    cleaned_text,
                    prefer_zh=prefer_zh,
                    slide_type=slide_type,
                    role="body",
                )
            cleaned_elements.append(el)
        out["elements"] = cleaned_elements
    cleaned_fixed: List[Dict[str, Any]] = []
    for block in fixed:
        b = dict(block)
        block_type = _as_block_type(b)
        text_role = "title" if block_type == "title" else ("subtitle" if block_type == "subtitle" else "body")
        content_obj = b.get("content")
        if isinstance(content_obj, str):
            cleaned_content = _sanitize_placeholder_text(content_obj, prefer_zh=prefer_zh)
            b["content"] = _clip_text_for_visual_budget(
                cleaned_content,
                prefer_zh=prefer_zh,
                slide_type=slide_type,
                role=text_role,
            )
        elif isinstance(content_obj, dict):
            cc = dict(content_obj)
            for key in ("title", "body", "text", "label", "caption", "description"):
                if key in cc and isinstance(cc.get(key), str):
                    cleaned_field = _sanitize_placeholder_text(str(cc.get(key) or ""), prefer_zh=prefer_zh)
                    field_role = "title" if (block_type == "title" and key == "title") else text_role
                    cc[key] = _clip_text_for_visual_budget(
                        cleaned_field,
                        prefer_zh=prefer_zh,
                        slide_type=slide_type,
                        role=field_role,
                    )
            b["content"] = cc
        data_obj = b.get("data")
        if isinstance(data_obj, dict):
            dd = dict(data_obj)
            for key in ("title", "label", "description"):
                if key in dd and isinstance(dd.get(key), str):
                    cleaned_field = _sanitize_placeholder_text(str(dd.get(key) or ""), prefer_zh=prefer_zh)
                    dd[key] = _clip_text_for_visual_budget(
                        cleaned_field,
                        prefer_zh=prefer_zh,
                        slide_type=slide_type,
                        role="body",
                    )
            b["data"] = dd
        cleaned_fixed.append(b)
    fixed = cleaned_fixed
    fixed = _dedupe_blocks(fixed)

    keypoints = [
        point
        for point in _extract_slide_keypoints(out, title_text)
        if _normalize_text_key(point) != title_key
    ]
    point_pool = _build_input_derived_point_pool(
        out,
        title_text=title_text,
        prefer_zh=prefer_zh,
        slide_type=slide_type,
    )

    def _next_text_point(idx: int, *, existing_keys: Optional[set[str]] = None) -> str:
        return _pick_input_derived_point(
            point_pool=point_pool,
            title_text=title_text,
            prefer_zh=prefer_zh,
            index=idx,
            title_key=title_key,
            existing_keys=existing_keys,
            slide_type=slide_type,
        )

    if topic_hint and fixed and (not strict_contract):
        topic_seed = _sanitize_placeholder_text(topic_hint, prefer_zh=prefer_zh) or title_text
        text_like_types = {"subtitle", "body", "list", "quote", "icon_text", "text", "comparison"}
        existing_keys: set[str] = set()
        for block in fixed:
            if not isinstance(block, dict):
                continue
            for frag in _collect_text_fragments_from_value(block.get("content")):
                key = _normalize_text_key(frag)
                if key:
                    existing_keys.add(key)
            for frag in _collect_text_fragments_from_value(block.get("data")):
                key = _normalize_text_key(frag)
                if key:
                    existing_keys.add(key)

        replace_cursor = 0

        def _rewrite_irrelevant_text(raw_text: str, *, role: str = "body") -> str:
            nonlocal replace_cursor
            current = str(raw_text or "").strip()
            if not current:
                return current
            # Only rewrite obviously bad content (placeholder/mojibake), or
            # very short and off-topic snippets. Do not overwrite normal text.
            placeholder_like = _looks_placeholder_like_text(current)
            mojibake_like = _looks_mojibake(current, allow_repair=False)
            current_key = _normalize_text_key(current)
            if not placeholder_like and not mojibake_like and len(current_key) >= 8:
                return current
            relevance = _topic_relevance_score(
                topic=topic_seed,
                title=title_text,
                snippet=current,
                domain_terms=[],
                required_facts=[],
            )
            if (not placeholder_like) and (not mojibake_like) and relevance >= 0.08:
                return current
            candidate = _next_text_point(replace_cursor, existing_keys=existing_keys)
            replace_cursor += 1
            if not candidate:
                candidate = topic_seed
            candidate = _clip_text_for_visual_budget(
                candidate,
                prefer_zh=prefer_zh,
                slide_type=slide_type,
                role=role,
            )
            key = _normalize_text_key(candidate)
            if key:
                existing_keys.add(key)
            return candidate or current

        revised_blocks: List[Dict[str, Any]] = []
        for block in fixed:
            if not isinstance(block, dict):
                continue
            current = dict(block)
            bt = _as_block_type(current)
            if bt not in text_like_types:
                revised_blocks.append(current)
                continue
            role = "subtitle" if bt == "subtitle" else "body"
            content_obj = current.get("content")
            if isinstance(content_obj, str):
                current["content"] = _rewrite_irrelevant_text(content_obj, role=role)
            elif isinstance(content_obj, dict):
                cc = dict(content_obj)
                for key in ("title", "body", "text", "label", "caption", "description"):
                    if key in cc and isinstance(cc.get(key), str):
                        cc[key] = _rewrite_irrelevant_text(str(cc.get(key) or ""), role=role)
                current["content"] = cc
            data_obj = current.get("data")
            if isinstance(data_obj, dict):
                dd = dict(data_obj)
                for key in ("title", "label", "description"):
                    if key in dd and isinstance(dd.get(key), str):
                        dd[key] = _rewrite_irrelevant_text(str(dd.get(key) or ""), role="body")
                current["data"] = dd
            revised_blocks.append(current)
        fixed = _dedupe_blocks(revised_blocks)

    numeric_source = " ".join([title_text, str(out.get("narration") or "")] + keypoints)
    numeric_values = _extract_numeric_values(numeric_source)
    semantic_text = " ".join(
        [
            title_text,
            str(out.get("narration") or ""),
            str(out.get("semantic_type") or ""),
            str(out.get("semantic_subtype") or ""),
            str(out.get("content_subtype") or ""),
            str(out.get("subtype") or ""),
            str(out.get("page_type") or ""),
            str(out.get("page_role") or ""),
            str(out.get("visual_anchor") or ""),
            str(out.get("deck_archetype_profile") or ""),
            str(out.get("quality_profile") or ""),
        ]
    ).strip()
    semantic_mode = _infer_visual_semantic_mode(
        semantic_text=semantic_text,
        keypoints=keypoints,
        numeric_values=numeric_values,
    )

    if strict_contract:
        strict_issues = _collect_strict_contract_issues(
            slide=out,
            blocks=fixed,
            min_content_blocks=min_content_blocks,
            blank_area_max_ratio=blank_area_max_ratio,
            require_image_anchor=image_anchor_required,
        )
        if strict_issues:
            slide_ref = str(out.get("slide_id") or out.get("id") or out.get("page_number") or "unknown")
            raise ValueError(
                f"strict_content_contract_unmet:slide={slide_ref}; " + "; ".join(strict_issues[:8])
            )

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
                synthetic_points = [title_text[:24], str(out.get("narration") or "")[:24], str(out.get("title") or "")[:24]]
                fallback_points.extend([p for p in synthetic_points if str(p or "").strip()][: 3 - len(fallback_points)])
            fixed.append(
                {
                    "block_type": "list",
                    "card_id": "list_main",
                    "position": "left",
                    "content": ";".join(fallback_points[:3]),
                    "emphasis": fallback_points[:2],
                }
            )

        should_force_visual_anchor = image_anchor_required or semantic_mode == "data"
        if not has_anchor and should_force_visual_anchor:
            fixed.append(
                _make_visual_contract_block(
                    preferred_types=["image", "chart", "kpi"] if image_anchor_required else ["chart", "kpi", "image"],
                    keypoints=keypoints,
                    numeric_values=numeric_values,
                    prefer_zh=prefer_zh,
                    semantic_text=semantic_text,
                    card_id="visual_anchor",
                    position="right",
                )
            )
            has_image_anchor = _has_image_block(fixed)

        if image_anchor_required and not has_image_anchor:
            fixed.append(
                _make_visual_contract_block(
                    preferred_types=["image"],
                    keypoints=keypoints,
                    numeric_values=numeric_values,
                    prefer_zh=prefer_zh,
                    semantic_text=semantic_text,
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
            existing_keys = {
                _normalize_text_key(_extract_block_text(block))
                for block in fixed
                if _as_block_type(block) != "title"
            }
            item = _next_text_point(filler_idx, existing_keys=existing_keys)
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
    if (not strict_contract) and (not terminal_slide):
        whitelist = [
            str(item or "").strip().lower()
            for item in (out.get("template_family_whitelist") or [])
            if str(item or "").strip()
        ] if isinstance(out.get("template_family_whitelist"), list) else []
        resolved_template = ""
        slide_type_hint = str(out.get("slide_type") or "content").strip().lower() or "content"
        layout_hint = str(out.get("layout_grid") or out.get("layout") or "split_2").strip().lower() or "split_2"
        for candidate in whitelist:
            if _template_family_supports_slide(candidate, slide_type=slide_type_hint, layout_grid=layout_hint):
                resolved_template = candidate
                break
        if not resolved_template:
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
            if visual_candidates and _prefers_text_first_visual_fallback(out) and semantic_mode in {"education", "general"} and not numeric_values:
                continue
            if visual_candidates:
                fixed.append(
                    _make_visual_contract_block(
                        preferred_types=visual_candidates,
                        keypoints=keypoints,
                        numeric_values=numeric_values,
                        prefer_zh=prefer_zh,
                        semantic_text=semantic_text,
                        card_id=f"contract_visual_{group_idx + 1}",
                        position="right" if group_idx % 2 == 0 else "center",
                    )
                )
                continue
            existing_keys = {
                _normalize_text_key(_extract_block_text(block))
                for block in fixed
                if _as_block_type(block) != "title"
            }
            body_text = _next_text_point(group_idx, existing_keys=existing_keys)
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
        if image_anchor_required and "image" not in ordered_visual_types:
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
                    semantic_text=semantic_text,
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
            existing_keys = {
                _normalize_text_key(_extract_block_text(block))
                for block in fixed
                if _as_block_type(block) != "title"
            }
            text_item = _next_text_point(text_fill_idx, existing_keys=existing_keys)
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
                    semantic_text=semantic_text,
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
    if (not strict_contract) and (not terminal_slide):
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
            existing_keys = {
                _normalize_text_key(_extract_block_text(block))
                for block in fixed
                if _as_block_type(block) != "title"
            }
            item = _next_text_point(filler_idx, existing_keys=existing_keys)
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
            existing_keys = {
                _normalize_text_key(_extract_block_text(block))
                for block in fixed
                if _as_block_type(block) != "title"
            }
            item = _next_text_point(fill_idx, existing_keys=existing_keys)
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
    if (not strict_contract) and (not terminal_slide) and image_anchor_required and not _has_image_block(fixed):
        injected = _make_visual_contract_block(
            preferred_types=["image"],
            keypoints=keypoints,
            numeric_values=numeric_values,
            prefer_zh=prefer_zh,
            semantic_text=semantic_text,
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
        # Image anchor is a soft orchestration hint. If layout
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
    if (not strict_contract) and (not terminal_slide) and contract_min_text > 0:
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
            visual_floor = max(int(contract_min_visual or 0), 1 if image_anchor_required else 0)
            visual_count = _count_visual(fixed)
            if visual_count > visual_floor:
                for i, block in enumerate(fixed):
                    btype = _as_block_type(block)
                    if btype not in visual_type_set or btype == "image":
                        continue
                    if btype in protected_visual_types:
                        continue
                    existing_keys = {
                        _normalize_text_key(_extract_block_text(item))
                        for j, item in enumerate(fixed)
                        if j != i and _as_block_type(item) != "title"
                    }
                    replacement_text = _extract_block_text(block) or _next_text_point(
                        recover_idx + 2,
                        existing_keys=existing_keys,
                    )
                    if _normalize_text_key(replacement_text) in existing_keys or _normalize_text_key(replacement_text) == title_key:
                        replacement_text = _next_text_point(recover_idx + 3, existing_keys=existing_keys)
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
                existing_keys = {
                    _normalize_text_key(_extract_block_text(block))
                    for block in fixed
                    if _as_block_type(block) != "title"
                }
                fill_text = _next_text_point(recover_idx + 4, existing_keys=existing_keys)
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

    if (not strict_contract) and (not terminal_slide):
        # Align with quality gate duplicate_text policy and repair duplicates
        # deterministically instead of letting the pipeline fail downstream.
        rewritten: List[Dict[str, Any]] = []
        seen_quality_keys: set[str] = set()
        rewrite_cursor = 0
        for block in fixed:
            btype = _as_block_type(block)
            if btype == "title":
                rewritten.append(block)
                continue
            quality_key = _normalize_quality_text_key(_extract_block_text(block))
            if not quality_key or quality_key not in seen_quality_keys:
                rewritten.append(block)
                if quality_key:
                    seen_quality_keys.add(quality_key)
                continue
            # Duplicate non-title text: rewrite textual blocks first, drop only if
            # no unique replacement is available.
            if btype in _TEXTUAL_BLOCK_TYPES:
                replacement = ""
                for offset in range(0, 8):
                    existing_keys = {
                        _normalize_text_key(_extract_block_text(item))
                        for item in rewritten
                        if _as_block_type(item) != "title"
                    }
                    candidate = _next_text_point(rewrite_cursor + offset + 1, existing_keys=existing_keys)
                    candidate_key = _normalize_quality_text_key(candidate)
                    if candidate and candidate_key and candidate_key not in seen_quality_keys:
                        replacement = candidate
                        rewrite_cursor += offset + 1
                        break
                if replacement:
                    patched = dict(block)
                    patched["content"] = replacement
                    patched_key = _normalize_quality_text_key(replacement)
                    rewritten.append(patched)
                    if patched_key:
                        seen_quality_keys.add(patched_key)
                    continue
            continue
        fixed = _dedupe_blocks(rewritten)

    for idx, block in enumerate(fixed):
        block["block_type"] = _as_block_type(block) or "text"
        if not str(block.get("card_id") or "").strip():
            block["card_id"] = f"card-{idx + 1}"
        if block["block_type"] != "title":
            block["emphasis"] = _auto_emphasis(block, keypoints)

    out["blocks"] = fixed
    layout_grid = str(out.get("layout_grid") or out.get("layout") or "").strip().lower() or "split_2"
    existing_family = str(out.get("template_family") or out.get("template_id") or "").strip().lower()
    slide_type_for_template = str(slide_type or "content").strip().lower() or "content"
    keep_existing_family = (
        existing_family
        and _template_family_supports_slide(
            existing_family,
            slide_type=slide_type_for_template,
            layout_grid=layout_grid,
        )
        and not (
            slide_type_for_template == "content"
            and _is_terminal_template_family(existing_family)
        )
    )
    if keep_existing_family:
        out["template_family"] = existing_family
    else:
        out["template_family"] = _resolve_template_family(out)
    out.update(_template_profiles(out["template_family"]))
    out["bg_style"] = "light" if str(out["template_family"] or "").strip().lower().endswith("_light") else "dark"
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
    allow_quality_template_unlock = quality_id == "training_deck"
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
    theme_cohesion_cfg = (
        orchestration_cfg.get("theme_cohesion")
        if isinstance(orchestration_cfg.get("theme_cohesion"), dict)
        else {}
    )
    execution_profile = _normalize_execution_profile(out.get("execution_profile"))
    strict_contract_mode = execution_profile == "dev_strict"
    strict_contract = strict_contract_mode
    def _deck_prefers_light_templates() -> bool:
        hint_parts: List[str] = [
            str(out.get("title") or ""),
            str(out.get("topic") or ""),
            str(out.get("subject") or ""),
            str(out.get("audience") or ""),
            str(out.get("purpose") or ""),
            str(out.get("category") or ""),
        ]
        for raw_slide in (slides or [])[:16]:
            if not isinstance(raw_slide, dict):
                continue
            hint_parts.extend(
                [
                    str(raw_slide.get("title") or ""),
                    str(raw_slide.get("narration") or ""),
                    str(raw_slide.get("speaker_notes") or ""),
                    str(raw_slide.get("semantic_type") or ""),
                    str(raw_slide.get("semantic_subtype") or ""),
                    str(raw_slide.get("content_subtype") or ""),
                ]
            )
        blob = " ".join(hint_parts).lower()
        if not blob.strip():
            return False
        return any(
            token in blob
            for token in (
                "classroom",
                "teaching",
                "education",
                "lesson",
                "training",
                "school",
                "student",
                "curriculum",
                "课堂",
                "教学",
                "课程",
                "教育",
                "培训",
                "高中",
                "学生",
                "教师",
                "学科",
            )
        )
    prefer_light_deck = _deck_prefers_light_templates()
    theme_cohesion_enabled = bool(theme_cohesion_cfg.get("enabled", True))
    theme_cohesion_content_only = bool(theme_cohesion_cfg.get("content_only", True))
    theme_cohesion_apply_to_terminal = bool(theme_cohesion_cfg.get("apply_to_terminal", False))
    theme_cohesion_preferred_tone = str(theme_cohesion_cfg.get("preferred_tone") or "auto").strip().lower()
    if theme_cohesion_preferred_tone not in {"light", "dark"}:
        theme_cohesion_preferred_tone = ""
    def _enforce_contract(slide_obj: Dict[str, Any]) -> Dict[str, Any]:
        # In dev_strict we still normalize deterministically first, then validate.
        # This keeps fast-fail semantics while avoiding false schema-invalid from
        # raw upstream drafts that have not passed contract normalization yet.
        normalized = _ensure_content_contract(
            slide_obj,
            min_content_blocks=min_content_blocks,
            blank_area_max_ratio=float(quality_cfg.get("blank_area_max_ratio") or 0.45),
            require_image_anchor=require_image_anchor,
            strict_contract=False if strict_contract_mode else strict_contract,
        )
        if strict_contract_mode:
            normalized_slide_type = str(normalized.get("slide_type") or "").strip().lower()
            if normalized_slide_type not in {"cover", "summary", "toc", "divider", "hero_1"}:
                image_anchor_required = _slide_requires_image_anchor(
                    normalized,
                    require_image_anchor=require_image_anchor,
                )
                blocks = [
                    dict(item)
                    for item in (normalized.get("blocks") or [])
                    if isinstance(item, dict)
                ]
                has_visual_anchor = any(_as_block_type(block) in _VISUAL_BLOCK_TYPES for block in blocks)
                has_image_anchor = _has_image_block(blocks)
                if (not has_visual_anchor) or (image_anchor_required and not has_image_anchor):
                    title_text = str(normalized.get("title") or normalized.get("slide_id") or "slide")
                    prefer_zh = _prefer_zh(title_text, normalized.get("narration"), normalized.get("speaker_notes"))
                    keypoints = _extract_slide_keypoints(normalized, title_text)
                    numeric_values = _extract_numeric_values(
                        " ".join([title_text, str(normalized.get("narration") or ""), *keypoints])
                    )
                    semantic_text = " ".join(
                        [
                            title_text,
                            str(normalized.get("narration") or ""),
                            str(normalized.get("semantic_type") or ""),
                            str(normalized.get("semantic_subtype") or ""),
                            str(normalized.get("content_subtype") or ""),
                            str(normalized.get("subtype") or ""),
                            str(normalized.get("page_type") or ""),
                            str(normalized.get("page_role") or ""),
                            str(normalized.get("visual_anchor") or ""),
                        ]
                    ).strip()
                    if not has_visual_anchor:
                        blocks.append(
                            _make_visual_contract_block(
                                preferred_types=["image", "workflow", "diagram", "chart", "kpi", "table"],
                                keypoints=keypoints,
                                numeric_values=numeric_values,
                                prefer_zh=prefer_zh,
                                semantic_text=semantic_text,
                                card_id="strict_visual_anchor",
                                position="right",
                            )
                        )
                    if image_anchor_required and (not _has_image_block(blocks)):
                        blocks.append(
                            _make_visual_contract_block(
                                preferred_types=["image"],
                                keypoints=keypoints,
                                numeric_values=numeric_values,
                                prefer_zh=prefer_zh,
                                semantic_text=semantic_text,
                                card_id="strict_image_anchor",
                                position="right",
                            )
                        )
                    normalized["blocks"] = _dedupe_blocks(blocks)
            try:
                normalized = _ensure_content_contract(
                    normalized,
                    min_content_blocks=min_content_blocks,
                    blank_area_max_ratio=float(quality_cfg.get("blank_area_max_ratio") or 0.45),
                    require_image_anchor=require_image_anchor,
                    strict_contract=True,
                )
            except ValueError as exc:
                detail = str(exc or "").strip().lower()
                recoverable = (
                    "strict_content_contract_unmet" in detail
                    and (
                        "missing_required_group" in detail
                        or "insufficient_visual_blocks" in detail
                        or "missing_visual_anchor_block" in detail
                    )
                )
                if not recoverable:
                    raise
                # Deterministic strict preflight: repair once with non-strict
                # contract synthesis, then validate under strict rules again.
                normalized = _ensure_content_contract(
                    normalized,
                    min_content_blocks=min_content_blocks,
                    blank_area_max_ratio=float(quality_cfg.get("blank_area_max_ratio") or 0.45),
                    require_image_anchor=require_image_anchor,
                    strict_contract=False,
                )
                normalized = _ensure_content_contract(
                    normalized,
                    min_content_blocks=min_content_blocks,
                    blank_area_max_ratio=float(quality_cfg.get("blank_area_max_ratio") or 0.45),
                    require_image_anchor=require_image_anchor,
                    strict_contract=True,
                )
        return normalized
    family_convergence_enabled = bool(family_cfg.get("enabled", False))
    family_auto_only = bool(family_cfg.get("only_when_deck_template_auto", True))
    family_default = (
        str(family_cfg.get("default_family") or "").strip().lower()
        or _infer_deck_template_family_from_rows([row for row in slides if isinstance(row, dict)])
    )
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
    dev_strict_force_template_homogeneous = bool(
        orchestration_cfg.get("dev_strict_force_template_homogeneous", False)
    )
    dev_strict_template_family = (
        str(orchestration_cfg.get("dev_strict_template_family") or family_default or "")
        .strip()
        .lower()
    )
    require_image_anchor = bool(orchestration_cfg.get("require_image_anchor", True))
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

    out["slides"] = [_enforce_contract(slide) for slide in normalized_seed]
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

    def _layout_supports_tone(layout_grid: str, slide_type: str, tone: str) -> bool:
        normalized_tone = str(tone or "").strip().lower()
        if normalized_tone not in {"light", "dark"}:
            return True
        normalized_layout = str(layout_grid or "").strip().lower() or "split_2"
        normalized_slide_type = str(slide_type or "content").strip().lower() or "content"
        for family in shared_template_ids():
            normalized_family = str(family or "").strip().lower()
            if not normalized_family:
                continue
            family_tone = "light" if normalized_family.endswith("_light") else ("dark" if normalized_family.endswith("_dark") else "")
            if family_tone and family_tone != normalized_tone:
                continue
            if _template_family_supports_slide(
                normalized_family,
                slide_type=normalized_slide_type,
                layout_grid=normalized_layout,
            ):
                return True
        return False

    def _repair_layout_tone_compatibility(preferred_tone: str) -> None:
        tone = str(preferred_tone or "").strip().lower()
        if tone not in {"light", "dark"}:
            return
        base_candidates = ["split_2", "asymmetric_2", "grid_3", "grid_4", "timeline", "bento_5", "bento_6"]
        candidate_pool = []
        for item in [*base_candidates, *dense_cycle]:
            key = str(item or "").strip().lower()
            if key and key not in candidate_pool:
                candidate_pool.append(key)
        for slide in out.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            slide_type = str(slide.get("slide_type") or "").strip().lower() or "content"
            if slide_type in {"cover", "summary", "toc", "divider", "hero_1"}:
                continue
            current_layout = str(slide.get("layout_grid") or "split_2").strip().lower() or "split_2"
            if _layout_supports_tone(current_layout, slide_type, tone):
                continue
            for candidate in candidate_pool:
                if candidate == current_layout:
                    continue
                if _layout_supports_tone(candidate, slide_type, tone):
                    slide["layout_grid"] = candidate
                    break

    def _first_meaningful_text(slide_obj: Dict[str, Any], deck_title_key: str) -> str:
        blocks = slide_obj.get("blocks")
        if not isinstance(blocks, list):
            return ""
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if _as_block_type(block) == "title":
                continue
            text = _sanitize_placeholder_text(
                str(_extract_block_text(block) or "").strip(),
                prefer_zh=_prefer_zh(str(slide_obj.get("title") or "")),
            )
            key = _normalize_text_key(text)
            if (not key) or key == deck_title_key or _looks_placeholder_like_text(text):
                continue
            return _clip_text_for_visual_budget(
                text,
                prefer_zh=_prefer_zh(text, str(slide_obj.get("title") or "")),
                slide_type="content",
                role="title",
            )
        return ""

    def _rebalance_utility_slides() -> None:
        slides_list = out.get("slides") if isinstance(out.get("slides"), list) else []
        total = len(slides_list)
        if total <= 2:
            return
        max_toc = 1 if total >= 12 else 0
        max_divider = 2 if total >= 16 else (1 if total >= 8 else 0)
        density_window_size = max(3, int(quality_cfg.get("density_window_size") or 5))
        density_required_breathing = max(
            1, int(quality_cfg.get("density_require_low_or_breathing_per_window") or 1)
        )
        requires_breathing_slots = total >= density_window_size and density_required_breathing > 0
        if prefer_light_deck and total <= 12:
            if requires_breathing_slots:
                max_toc = max(1, max_toc)
                max_divider = max(1, min(max_divider, 1))
            else:
                max_toc = 0
                max_divider = min(max_divider, 1)
        toc_seen = 0
        divider_seen = 0
        deck_title_key = _normalize_text_key(str(out.get("title") or ""))
        layout_cycle = ["split_2", "grid_3", "asymmetric_2", "timeline", "grid_4"]
        for idx, slide_obj in enumerate(slides_list):
            if not isinstance(slide_obj, dict):
                continue
            if idx == 0 or idx == total - 1:
                continue
            slide_type = str(slide_obj.get("slide_type") or "").strip().lower()
            should_convert = False
            if slide_type == "toc":
                toc_seen += 1
                should_convert = toc_seen > max_toc
            elif slide_type == "divider":
                divider_seen += 1
                should_convert = divider_seen > max_divider
            if not should_convert:
                continue

            slide_obj["slide_type"] = "content"
            if str(slide_obj.get("layout_grid") or "").strip().lower() == "hero_1":
                slide_obj["layout_grid"] = layout_cycle[idx % len(layout_cycle)]
            replacement_title = _first_meaningful_text(slide_obj, deck_title_key)
            if replacement_title:
                slide_obj["title"] = replacement_title
                blocks = slide_obj.get("blocks")
                if isinstance(blocks, list):
                    for block in blocks:
                        if not isinstance(block, dict):
                            continue
                        if _as_block_type(block) == "title":
                            block["content"] = replacement_title
                            break
            blocks = slide_obj.get("blocks")
            if isinstance(blocks, list):
                mutable_blocks = [dict(item) for item in blocks if isinstance(item, dict)]
            else:
                mutable_blocks = []
            text_non_title = [
                block
                for block in mutable_blocks
                if _as_block_type(block) in _TEXTUAL_BLOCK_TYPES and _as_block_type(block) != "title"
            ]
            prefer_zh = _prefer_zh(str(slide_obj.get("title") or ""), str(out.get("title") or ""))
            seed_text = replacement_title or _first_meaningful_text(slide_obj, deck_title_key) or str(slide_obj.get("title") or "")
            seed_text = _sanitize_placeholder_text(seed_text, prefer_zh=prefer_zh)
            while len(text_non_title) < 2:
                idx_hint = len(text_non_title) + 1
                filler = (
                    f"{seed_text}要点{idx_hint}"
                    if prefer_zh
                    else f"{seed_text} key point {idx_hint}"
                ).strip()
                if not filler:
                    filler = "核心要点" if prefer_zh else "Key point"
                mutable_blocks.append(
                    {
                        "block_type": "body",
                        "position": "left",
                        "card_id": f"utility_rebalance_body_{idx_hint}",
                        "content": _clip_text_for_visual_budget(
                            filler,
                            prefer_zh=prefer_zh,
                            slide_type="content",
                            role="body",
                        ),
                        "emphasis": [],
                    }
                )
                text_non_title = [
                    block
                    for block in mutable_blocks
                    if _as_block_type(block) in _TEXTUAL_BLOCK_TYPES and _as_block_type(block) != "title"
                ]
            slide_obj["blocks"] = _assign_layout_card_ids(
                str(slide_obj.get("layout_grid") or "split_2"),
                _dedupe_blocks(mutable_blocks),
            )
            slide_obj["template_lock"] = False

    _rebalance_utility_slides()

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
        assigned_layout = str(layout or "split_2").strip().lower() or "split_2"
        if assigned_layout == "hero_1":
            has_meaningful_content = any(
                _as_block_type(block) in {"body", "list", "chart", "kpi", "image", "workflow", "diagram", "table"}
                for block in (slide.get("blocks") or [])
                if isinstance(block, dict)
            )
            if has_meaningful_content:
                if slide_type not in {"cover", "summary", "toc", "divider"}:
                    slide["slide_type"] = "content"
                current_family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
                if current_family and not _template_family_supports_slide(current_family, slide_type="content", layout_grid="hero_1"):
                    slide["template_family"] = "quote_hero_dark"
                    slide["template_id"] = "quote_hero_dark"
            else:
                slide["slide_type"] = "divider"
        slide["layout_grid"] = assigned_layout

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

    layout_tone_preference = theme_cohesion_preferred_tone
    if not layout_tone_preference:
        deck_family_hint = str(out.get("template_family") or "").strip().lower()
        if deck_family_hint.endswith("_light"):
            layout_tone_preference = "light"
        elif deck_family_hint.endswith("_dark"):
            layout_tone_preference = "dark"
    _repair_layout_tone_compatibility(layout_tone_preference)
    post_tone_sequence = [
        str((slide or {}).get("layout_grid") or "split_2").strip().lower()
        if isinstance(slide, dict)
        else "split_2"
        for slide in out["slides"]
    ]
    post_tone_sequence = enforce_density_rhythm(
        post_tone_sequence,
        max_consecutive_high=int(quality_cfg.get("density_max_consecutive_high") or 2),
        window_size=int(quality_cfg.get("density_window_size") or 5),
        require_low_or_breathing_per_window=int(
            quality_cfg.get("density_require_low_or_breathing_per_window") or 1
        ),
    )
    for idx, layout in enumerate(post_tone_sequence):
        if idx >= len(out["slides"]):
            break
        slide = out["slides"][idx]
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type in {"cover", "summary", "toc", "divider"}:
            continue
        assigned_layout = str(layout or "split_2").strip().lower() or "split_2"
        if assigned_layout == "hero_1":
            has_meaningful_content = any(
                _as_block_type(block) in {"body", "list", "chart", "kpi", "image", "workflow", "diagram", "table"}
                for block in (slide.get("blocks") or [])
                if isinstance(block, dict)
            )
            if has_meaningful_content:
                if slide_type not in {"cover", "summary", "toc", "divider"}:
                    slide["slide_type"] = "content"
                current_family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
                if current_family and not _template_family_supports_slide(current_family, slide_type="content", layout_grid="hero_1"):
                    slide["template_family"] = "quote_hero_dark"
                    slide["template_id"] = "quote_hero_dark"
            else:
                slide["slide_type"] = "divider"
        slide["layout_grid"] = assigned_layout

    # Pagination may create continuation slides with only one textual block
    # (e.g., title + list). Re-apply the contract fixer to keep downstream
    # render-contract constraints (min_text_blocks, emphasis) satisfied.
    out["slides"] = [
        _enforce_contract(slide if isinstance(slide, dict) else {})
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
        slide_title = str(slide.get("title") or "本页主题")
        prefer_zh = _prefer_zh(slide_title, slide.get("narration"), slide.get("speaker_notes"))
        point_pool = _build_input_derived_point_pool(
            slide,
            title_text=slide_title,
            prefer_zh=prefer_zh,
            slide_type=slide_type,
        )
        title_key = _normalize_text_key(slide_title)
        while len([b for b in fixed_blocks if _as_block_type(b) != "title"]) < target_non_title:
            existing_keys = {
                _normalize_text_key(_extract_block_text(block))
                for block in fixed_blocks
                if _as_block_type(block) != "title"
            }
            candidate_no = fill_idx + 1
            fill_text = _pick_input_derived_point(
                point_pool=point_pool,
                title_text=slide_title,
                prefer_zh=prefer_zh,
                index=candidate_no,
                title_key=title_key,
                existing_keys=existing_keys,
                slide_type=slide_type,
            )
            while _normalize_text_key(fill_text) in existing_keys:
                candidate_no += 1
                fill_text = _pick_input_derived_point(
                    point_pool=point_pool,
                    title_text=slide_title,
                    prefer_zh=prefer_zh,
                    index=candidate_no,
                    title_key=title_key,
                    existing_keys=existing_keys,
                    slide_type=slide_type,
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

    def _set_slide_family(slide: Dict[str, Any], family: str) -> None:
        normalized_family = str(family or "").strip().lower()
        if not normalized_family:
            return
        slide["template_family"] = normalized_family
        slide.update(_template_profiles(normalized_family))
        slide["bg_style"] = "light" if normalized_family.endswith("_light") else "dark"

    def _template_family_tone(template_family: str) -> str:
        family = str(template_family or "").strip().lower()
        if family.endswith("_light"):
            return "light"
        if family.endswith("_dark"):
            return "dark"
        return ""

    def _infer_content_preferred_tone(deck_template_preference: str = "") -> str:
        if not theme_cohesion_enabled:
            return ""
        if theme_cohesion_preferred_tone in {"light", "dark"}:
            return theme_cohesion_preferred_tone
        deck_tone = _template_family_tone(deck_template_preference)
        if deck_tone:
            return deck_tone
        content_counter: Counter[str] = Counter()
        for slide in out.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            if str(slide.get("slide_type") or "").strip().lower() != "content":
                continue
            family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
            tone = _template_family_tone(family)
            if tone:
                content_counter[tone] += 1
        if content_counter:
            light_count = int(content_counter.get("light", 0))
            dark_count = int(content_counter.get("dark", 0))
            if light_count > dark_count:
                return "light"
            if dark_count > light_count:
                return "dark"
        if prefer_light_deck:
            return "light"
        return ""

    def _derive_content_family_budget() -> int:
        content_rows = [
            slide
            for slide in (out.get("slides") or [])
            if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip().lower() == "content"
        ]
        content_count = len(content_rows)
        if content_count <= 2:
            return 1
        layout_variety = len(
            {
                str(slide.get("layout_grid") or "").strip().lower()
                for slide in content_rows
                if str(slide.get("layout_grid") or "").strip()
            }
        )
        # Root cause fix: do not hard-pin to two families. Keep enough
        # families to reflect layout diversity, while still bounded for cohesion.
        if content_count >= 8:
            return max(2, min(4, layout_variety if layout_variety > 0 else 3))
        return max(2, min(3, layout_variety if layout_variety > 0 else 2))

    family_sequence: List[str] = []
    family_locked_mask: List[bool] = []
    for slide in out["slides"]:
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        layout_grid = str(slide.get("layout_grid") or "split_2").strip().lower() or "split_2"
        if (
            slide_type in {"toc", "summary", "divider"}
            and not bool(slide.get("template_lock"))
        ):
            canonical_family = resolve_template_for_slide(
                slide=slide,
                slide_type=slide_type,
                layout_grid=layout_grid,
                requested_template="",
                desired_density=str(slide.get("content_density") or "balanced"),
            )
            if canonical_family:
                _set_slide_family(slide, canonical_family)
        family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
        if not family:
            family = _resolve_template_family(slide)
        family_sequence.append(family)
        implicit_lock = slide_type in {"cover", "summary", "toc", "divider", "hero_1"}
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
        _set_slide_family(slide, normalized)

    def _repair_slide_template_compatibility(
        deck_template_preference: str,
        *,
        preferred_tone: str = "",
    ) -> None:
        normalized_deck_preference = str(deck_template_preference or "").strip().lower()
        if normalized_deck_preference in {"", "auto"}:
            normalized_deck_preference = ""
        tone = str(preferred_tone or "").strip().lower()
        if tone not in {"light", "dark"}:
            tone = ""
        if tone and _template_family_tone(normalized_deck_preference) not in {"", tone}:
            normalized_deck_preference = ""
        for slide in out["slides"]:
            if not isinstance(slide, dict):
                continue
            slide_type = str(slide.get("slide_type") or "content").strip().lower() or "content"
            layout_grid = str(slide.get("layout_grid") or "split_2").strip().lower() or "split_2"
            current_family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
            resolved_family = current_family
            if (
                normalized_deck_preference
                and (not bool(slide.get("template_lock")) or not current_family or current_family == "auto")
                and _template_family_supports_slide(
                    normalized_deck_preference,
                    slide_type=slide_type,
                    layout_grid=layout_grid,
                )
            ):
                resolved_family = normalized_deck_preference
            if not _template_family_supports_slide(
                resolved_family,
                slide_type=slide_type,
                layout_grid=layout_grid,
            ):
                requested = (
                    normalized_deck_preference
                    if _template_family_supports_slide(
                        normalized_deck_preference,
                        slide_type=slide_type,
                        layout_grid=layout_grid,
                    )
                    else ""
                )
                resolved_family = resolve_template_for_slide(
                    slide=slide,
                    slide_type=slide_type,
                    layout_grid=layout_grid,
                    requested_template=requested,
                    desired_density=str(slide.get("content_density") or "balanced"),
                    preferred_tone=tone,
                )
            if resolved_family and resolved_family != current_family:
                _set_slide_family(slide, resolved_family)

    def _content_family_switch_ratio() -> float:
        values: List[str] = []
        for slide in out.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            slide_type = str(slide.get("slide_type") or "").strip().lower()
            if slide_type != "content":
                continue
            family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
            if family:
                values.append(family)
        if len(values) <= 1:
            return 0.0
        switches = 0
        for idx in range(1, len(values)):
            if values[idx] != values[idx - 1]:
                switches += 1
        return switches / max(1, len(values) - 1)

    def _smooth_content_family_switches_with_compatibility(max_switch_ratio: float) -> None:
        limit = max(0.0, min(1.0, float(max_switch_ratio)))
        guard = 0
        max_guard = max(8, len(out.get("slides") or []) * 8)
        while _content_family_switch_ratio() > limit and guard < max_guard:
            guard += 1
            changed = False
            content_indices = [
                idx
                for idx, slide in enumerate(out.get("slides") or [])
                if isinstance(slide, dict)
                and str(slide.get("slide_type") or "").strip().lower() == "content"
            ]
            for pos in range(1, len(content_indices)):
                prev_idx = content_indices[pos - 1]
                curr_idx = content_indices[pos]
                previous = out["slides"][prev_idx]
                current = out["slides"][curr_idx]
                prev_family = str(previous.get("template_family") or previous.get("template_id") or "").strip().lower()
                curr_family = str(current.get("template_family") or current.get("template_id") or "").strip().lower()
                if not prev_family or not curr_family or prev_family == curr_family:
                    continue

                current_slide_type = str(current.get("slide_type") or "content").strip().lower() or "content"
                current_layout = str(current.get("layout_grid") or "split_2").strip().lower() or "split_2"
                previous_slide_type = str(previous.get("slide_type") or "content").strip().lower() or "content"
                previous_layout = str(previous.get("layout_grid") or "split_2").strip().lower() or "split_2"

                if (
                    not bool(current.get("template_lock"))
                    and _template_family_supports_slide(
                        prev_family,
                        slide_type=current_slide_type,
                        layout_grid=current_layout,
                    )
                ):
                    _set_slide_family(current, prev_family)
                    changed = True
                    break

                if (
                    not bool(previous.get("template_lock"))
                    and _template_family_supports_slide(
                        curr_family,
                        slide_type=previous_slide_type,
                        layout_grid=previous_layout,
                    )
                ):
                    _set_slide_family(previous, curr_family)
                    changed = True
                    break
            if not changed:
                break

    def _harmonize_content_family_pack(
        *,
        max_unique: int = 2,
        target_switch_ratio: float = 0.55,
        max_top2_ratio: float = 0.85,
    ) -> None:
        # Strict/high-diversity profiles (low top2 limit) should keep original
        # family balancing behavior to avoid over-correction.
        if float(max_top2_ratio) < 0.8:
            return
        content_indices = [
            idx
            for idx, slide in enumerate(out.get("slides") or [])
            if isinstance(slide, dict)
            and str(slide.get("slide_type") or "").strip().lower() == "content"
        ]
        if len(content_indices) <= 2:
            return
        max_allowed_unique = max(1, int(max_unique))
        families = [
            str((out["slides"][idx] or {}).get("template_family") or (out["slides"][idx] or {}).get("template_id") or "")
            .strip()
            .lower()
            for idx in content_indices
        ]
        family_counts = Counter([name for name in families if name])
        if not family_counts:
            return

        unique_count = len(family_counts)
        # Keep at least two families on medium/long decks to prevent visual
        # monotony; do not collapse all content pages into one template.
        min_unique_for_deck = 2 if len(content_indices) >= 4 else 1
        target_unique = max(min_unique_for_deck, min(max_allowed_unique, unique_count))

        allowed_families = [name for name, _ in family_counts.most_common(max(1, target_unique))]
        preferred_tone = _infer_content_preferred_tone(str(out.get("template_family") or ""))
        if preferred_tone in {"light", "dark"}:
            tone_filtered = [
                family
                for family in allowed_families
                if _template_family_tone(family) in {"", preferred_tone}
            ]
            if tone_filtered:
                allowed_families = tone_filtered
        allowed_set = set(allowed_families)
        for idx in content_indices:
            slide = out["slides"][idx]
            if not isinstance(slide, dict) or bool(slide.get("template_lock")):
                continue
            current_family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
            if current_family in allowed_set:
                continue
            slide_type = str(slide.get("slide_type") or "content").strip().lower() or "content"
            layout_grid = str(slide.get("layout_grid") or "split_2").strip().lower() or "split_2"
            reassigned = False
            for candidate in allowed_families:
                candidate_tone = _template_family_tone(candidate)
                if preferred_tone in {"light", "dark"} and candidate_tone and candidate_tone != preferred_tone:
                    continue
                if _template_family_supports_slide(candidate, slide_type=slide_type, layout_grid=layout_grid):
                    _set_slide_family(slide, candidate)
                    reassigned = True
                    break
            if not reassigned:
                fallback_family = resolve_template_for_slide(
                    slide=slide,
                    slide_type=slide_type,
                    layout_grid=layout_grid,
                    requested_template="",
                    desired_density=str(slide.get("content_density") or "balanced"),
                    preferred_tone=_infer_content_preferred_tone(str(out.get("template_family") or "")),
                )
                if fallback_family:
                    _set_slide_family(slide, fallback_family)

        # Recompute after pack limiting.
        families = [
            str((out["slides"][idx] or {}).get("template_family") or (out["slides"][idx] or {}).get("template_id") or "")
            .strip()
            .lower()
            for idx in content_indices
        ]
        switches = 0
        for pos in range(1, len(families)):
            if families[pos] and families[pos - 1] and families[pos] != families[pos - 1]:
                switches += 1
        switch_ratio = switches / max(1, len(families) - 1)
        if len(set([f for f in families if f])) <= target_unique and switch_ratio <= max(
            0.0, min(1.0, float(target_switch_ratio))
        ):
            return

        # Reduce excessive switching without collapsing to one family.
        guard = 0
        while guard < max(6, len(content_indices) * 4):
            guard += 1
            families = [
                str((out["slides"][idx] or {}).get("template_family") or (out["slides"][idx] or {}).get("template_id") or "")
                .strip()
                .lower()
                for idx in content_indices
            ]
            switches = sum(
                1 for pos in range(1, len(families)) if families[pos] and families[pos - 1] and families[pos] != families[pos - 1]
            )
            switch_ratio = switches / max(1, len(families) - 1)
            if switch_ratio <= max(0.0, min(1.0, float(target_switch_ratio))):
                break
            changed = False
            for pos in range(1, len(content_indices)):
                prev_idx = content_indices[pos - 1]
                curr_idx = content_indices[pos]
                previous = out["slides"][prev_idx]
                current = out["slides"][curr_idx]
                if not isinstance(previous, dict) or not isinstance(current, dict):
                    continue
                if bool(current.get("template_lock")):
                    continue
                prev_family = str(previous.get("template_family") or previous.get("template_id") or "").strip().lower()
                curr_family = str(current.get("template_family") or current.get("template_id") or "").strip().lower()
                if not prev_family or not curr_family or prev_family == curr_family:
                    continue
                slide_type = str(current.get("slide_type") or "content").strip().lower() or "content"
                layout_grid = str(current.get("layout_grid") or "split_2").strip().lower() or "split_2"
                if not _template_family_supports_slide(prev_family, slide_type=slide_type, layout_grid=layout_grid):
                    continue
                projected = list(families)
                projected[pos] = prev_family
                projected_unique = len(set([name for name in projected if name]))
                if projected_unique < min_unique_for_deck:
                    continue
                _set_slide_family(current, prev_family)
                changed = True
                break
            if not changed:
                break

    def _dedupe_adjacent_template_repetition() -> None:
        template_ids = [str(item or "").strip().lower() for item in shared_template_ids() if str(item or "").strip()]
        if not template_ids:
            return
        max_switch_ratio = max(0.0, min(1.0, float(quality_cfg.get("template_family_max_switch_ratio") or 0.75)))
        preferred_tone = _infer_content_preferred_tone(str(out.get("template_family") or ""))

        def _content_families() -> List[str]:
            values: List[str] = []
            for slide in out.get("slides") or []:
                if not isinstance(slide, dict):
                    continue
                if str(slide.get("slide_type") or "").strip().lower() != "content":
                    continue
                family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
                if family:
                    values.append(family)
            return values

        def _switch_ratio(values: List[str]) -> float:
            if len(values) <= 1:
                return 0.0
            switches = sum(1 for idx in range(1, len(values)) if values[idx] != values[idx - 1])
            return switches / max(1, len(values) - 1)

        def _run_length_for_index(slide_idx: int) -> int:
            slides = out.get("slides") or []
            if slide_idx < 0 or slide_idx >= len(slides):
                return 0
            current = slides[slide_idx]
            if not isinstance(current, dict):
                return 0
            family = str(current.get("template_family") or current.get("template_id") or "").strip().lower()
            if not family:
                return 0
            length = 1
            left = slide_idx - 1
            while left >= 0:
                prev = slides[left]
                if not isinstance(prev, dict):
                    break
                if str(prev.get("slide_type") or "").strip().lower() != "content":
                    break
                prev_family = str(prev.get("template_family") or prev.get("template_id") or "").strip().lower()
                if prev_family != family:
                    break
                length += 1
                left -= 1
            right = slide_idx + 1
            while right < len(slides):
                nxt = slides[right]
                if not isinstance(nxt, dict):
                    break
                if str(nxt.get("slide_type") or "").strip().lower() != "content":
                    break
                next_family = str(nxt.get("template_family") or nxt.get("template_id") or "").strip().lower()
                if next_family != family:
                    break
                length += 1
                right += 1
            return length

        def _is_light_preferred(slide: Dict[str, Any]) -> bool:
            if preferred_tone == "light":
                return True
            if preferred_tone == "dark":
                return False
            if prefer_light_deck:
                return True
            blob = " ".join(
                [
                    str(out.get("title") or ""),
                    str(out.get("audience") or ""),
                    str(out.get("purpose") or ""),
                    str(slide.get("title") or ""),
                    str(slide.get("narration") or ""),
                    str(slide.get("speaker_notes") or ""),
                ]
            ).lower()
            return any(
                token in blob
                for token in (
                    "classroom",
                    "teaching",
                    "education",
                    "lesson",
                    "training",
                    "课堂",
                    "教学",
                    "课程",
                    "教育",
                    "高中",
                    "学生",
                )
            )

        for idx in range(1, len(out.get("slides") or [])):
            prev = out["slides"][idx - 1]
            curr = out["slides"][idx]
            if not isinstance(prev, dict) or not isinstance(curr, dict):
                continue
            if str(curr.get("slide_type") or "").strip().lower() != "content":
                continue
            prev_family = str(prev.get("template_family") or prev.get("template_id") or "").strip().lower()
            curr_family = str(curr.get("template_family") or curr.get("template_id") or "").strip().lower()
            if not prev_family or curr_family != prev_family:
                continue

            run_len = _run_length_for_index(idx)
            content_family_counts = Counter(_content_families())
            is_dominant = (
                bool(content_family_counts)
                and float(content_family_counts.get(curr_family, 0)) / float(max(1, sum(content_family_counts.values()))) > 0.40
            )
            # Root cause fix: only force dedupe when this family creates visible monotony
            # (adjacent run or dominance), not for every normal repetition.
            if run_len < 2 and not is_dominant:
                continue

            slide_type = str(curr.get("slide_type") or "content").strip().lower() or "content"
            layout_grid = str(curr.get("layout_grid") or "split_2").strip().lower() or "split_2"
            block_types = {
                str((block or {}).get("block_type") or (block or {}).get("type") or "").strip().lower()
                for block in (curr.get("blocks") if isinstance(curr.get("blocks"), list) else [])
                if isinstance(block, dict)
            }
            prefer_light = _is_light_preferred(curr)
            next_family = ""
            best_score = -10_000.0
            for candidate in template_ids:
                if candidate == prev_family:
                    continue
                candidate_tone = _template_family_tone(candidate)
                if preferred_tone in {"light", "dark"} and candidate_tone and candidate_tone != preferred_tone:
                    continue
                if not _template_family_supports_slide(candidate, slide_type=slide_type, layout_grid=layout_grid):
                    continue
                cap = shared_template_capabilities(candidate)
                supported = {
                    str(item or "").strip().lower()
                    for item in (cap.get("supported_block_types") or [])
                    if str(item or "").strip()
                }
                mismatch = len([bt for bt in block_types if bt and bt != "title" and bt not in supported])
                visual_need = len([bt for bt in block_types if bt in _VISUAL_BLOCK_TYPES]) > 0
                score = 0.0
                score -= float(mismatch) * 3.5
                if prefer_light:
                    score += 2.4 if candidate.endswith("_light") else (-1.4 if candidate.endswith("_dark") else 0.0)
                else:
                    score += 0.8 if candidate.endswith("_dark") else 0.0
                if visual_need and int(cap.get("visual_anchor_capacity") or 0) <= 0:
                    score -= 1.8
                if content_family_counts:
                    current_total = float(max(1, sum(content_family_counts.values())))
                    score -= float(content_family_counts.get(candidate, 0)) / current_total
                if score > best_score:
                    best_score = score
                    next_family = candidate
            if next_family:
                before_ratio = _switch_ratio(_content_families())
                old_family = curr_family
                _set_slide_family(curr, next_family)
                after_ratio = _switch_ratio(_content_families())
                if after_ratio > max_switch_ratio and after_ratio > before_ratio:
                    _set_slide_family(curr, old_family)

    def _dedupe_content_sequence_template_repetition() -> None:
        template_ids = [str(item or "").strip().lower() for item in shared_template_ids() if str(item or "").strip()]
        if not template_ids:
            return
        preferred_tone = _infer_content_preferred_tone(str(out.get("template_family") or ""))
        content_indices = [
            idx
            for idx, slide in enumerate(out.get("slides") or [])
            if isinstance(slide, dict)
            and str(slide.get("slide_type") or "").strip().lower() == "content"
        ]
        if len(content_indices) <= 1:
            return
        for pos in range(1, len(content_indices)):
            prev_idx = content_indices[pos - 1]
            curr_idx = content_indices[pos]
            previous = out["slides"][prev_idx]
            current = out["slides"][curr_idx]
            if not isinstance(previous, dict) or not isinstance(current, dict):
                continue
            prev_family = str(previous.get("template_family") or previous.get("template_id") or "").strip().lower()
            curr_family = str(current.get("template_family") or current.get("template_id") or "").strip().lower()
            if not prev_family or curr_family != prev_family:
                continue
            slide_type = str(current.get("slide_type") or "content").strip().lower() or "content"
            layout_grid = str(current.get("layout_grid") or "split_2").strip().lower() or "split_2"
            block_types = {
                str((block or {}).get("block_type") or (block or {}).get("type") or "").strip().lower()
                for block in (current.get("blocks") if isinstance(current.get("blocks"), list) else [])
                if isinstance(block, dict)
            }
            candidate_pool = []
            for key in ("template_candidates", "template_family_whitelist"):
                raw = current.get(key)
                if isinstance(raw, list):
                    candidate_pool.extend(str(item or "").strip().lower() for item in raw if str(item or "").strip())
            candidate_pool.extend(template_ids)
            seen_candidates: set[str] = set()
            for candidate in candidate_pool:
                normalized = str(candidate or "").strip().lower()
                if not normalized or normalized in seen_candidates:
                    continue
                seen_candidates.add(normalized)
                if normalized == prev_family:
                    continue
                candidate_tone = _template_family_tone(normalized)
                if preferred_tone in {"light", "dark"} and candidate_tone and candidate_tone != preferred_tone:
                    continue
                if not _template_family_supports_slide(normalized, slide_type=slide_type, layout_grid=layout_grid):
                    continue
                _set_slide_family(current, normalized)
                break

    def _dedupe_content_global_template_reuse() -> None:
        template_ids = [str(item or "").strip().lower() for item in shared_template_ids() if str(item or "").strip()]
        if not template_ids:
            return
        preferred_tone = _infer_content_preferred_tone(str(out.get("template_family") or ""))
        content_indices = [
            idx
            for idx, slide in enumerate(out.get("slides") or [])
            if isinstance(slide, dict)
            and str(slide.get("slide_type") or "").strip().lower() == "content"
        ]
        if len(content_indices) <= 2:
            return
        seen_families: set[str] = set()
        for pos, curr_idx in enumerate(content_indices):
            current = out["slides"][curr_idx]
            if not isinstance(current, dict):
                continue
            if bool(current.get("template_lock")):
                family_locked = str(current.get("template_family") or current.get("template_id") or "").strip().lower()
                if family_locked:
                    seen_families.add(family_locked)
                continue
            curr_family = str(current.get("template_family") or current.get("template_id") or "").strip().lower()
            if curr_family and curr_family not in seen_families:
                seen_families.add(curr_family)
                continue

            slide_type = str(current.get("slide_type") or "content").strip().lower() or "content"
            layout_grid = str(current.get("layout_grid") or "split_2").strip().lower() or "split_2"
            block_types = {
                str((block or {}).get("block_type") or (block or {}).get("type") or "").strip().lower()
                for block in (current.get("blocks") if isinstance(current.get("blocks"), list) else [])
                if isinstance(block, dict)
            }
            candidate_pool: List[str] = []
            for key in ("template_candidates", "template_family_whitelist"):
                raw = current.get(key)
                if isinstance(raw, list):
                    candidate_pool.extend(str(item or "").strip().lower() for item in raw if str(item or "").strip())
            candidate_pool.extend(template_ids)

            best_candidate = ""
            best_score = -10_000.0
            seen_candidates: set[str] = set()
            for candidate in candidate_pool:
                normalized = str(candidate or "").strip().lower()
                if not normalized or normalized in seen_candidates:
                    continue
                seen_candidates.add(normalized)
                if normalized == curr_family:
                    continue
                candidate_tone = _template_family_tone(normalized)
                if preferred_tone in {"light", "dark"} and candidate_tone and candidate_tone != preferred_tone:
                    continue
                if not _template_family_supports_slide(normalized, slide_type=slide_type, layout_grid=layout_grid):
                    continue
                cap = shared_template_capabilities(normalized)
                supported = {
                    str(item or "").strip().lower()
                    for item in (cap.get("supported_block_types") or [])
                    if str(item or "").strip()
                }
                mismatch = len([bt for bt in block_types if bt and bt != "title" and bt not in supported])
                score = 0.0
                score -= float(mismatch) * 4.0
                if normalized not in seen_families:
                    score += 3.0
                else:
                    score -= 8.0
                if preferred_tone == "light" and normalized.endswith("_light"):
                    score += 1.2
                elif normalized.endswith("_light") and prefer_light_deck:
                    score += 1.2
                if score > best_score:
                    best_score = score
                    best_candidate = normalized
            if best_candidate:
                _set_slide_family(current, best_candidate)
                curr_family = best_candidate
            if curr_family:
                seen_families.add(curr_family)

    def _apply_education_light_template_policy() -> None:
        if not theme_cohesion_enabled:
            return
        deck_profile = str(out.get("deck_archetype_profile") or "").strip().lower()
        preferred_tone = _infer_content_preferred_tone(str(out.get("template_family") or ""))
        if preferred_tone not in {"light", "dark"}:
            return
        skip_types = set(family_skip_types)
        if not theme_cohesion_content_only:
            skip_types = set()
        if theme_cohesion_apply_to_terminal:
            skip_types = {item for item in skip_types if item not in {"cover", "summary", "toc", "divider", "hero_1"}}

        for slide in out.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            if bool(slide.get("template_lock")) and not allow_quality_template_unlock:
                continue
            slide_type = str(slide.get("slide_type") or "").strip().lower() or "content"
            if deck_profile == "education_textbook" and slide_type in {"cover", "toc", "summary", "divider"}:
                _set_slide_family(slide, "hero_dark")
                continue
            if slide_type in skip_types:
                continue
            if deck_profile == "education_textbook" and slide_type == "content":
                _set_slide_family(slide, "education_textbook_light")
                continue
            current_family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
            current_tone = _template_family_tone(current_family)
            if current_tone == preferred_tone:
                continue
            layout_grid = str(slide.get("layout_grid") or "split_2").strip().lower() or "split_2"
            resolved_family = resolve_template_for_slide(
                slide=slide,
                slide_type=slide_type,
                layout_grid=layout_grid,
                requested_template="",
                desired_density=str(slide.get("content_density") or "balanced"),
                preferred_tone=preferred_tone,
            )
            if resolved_family:
                _set_slide_family(slide, resolved_family)

    def _repair_slide_block_capability_mismatch() -> None:
        for idx, slide in enumerate(out.get("slides") or []):
            if not isinstance(slide, dict):
                continue
            family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
            if not family:
                continue
            cap = shared_template_capabilities(family)
            supported = {
                str(item or "").strip().lower()
                for item in (cap.get("supported_block_types") or [])
                if str(item or "").strip()
            }
            if not supported:
                continue
            blocks = slide.get("blocks")
            if not isinstance(blocks, list):
                continue
            title_text = str(slide.get("title") or "")
            prefer_zh = _prefer_zh(title_text, slide.get("narration"), slide.get("speaker_notes"))
            keypoints = _extract_slide_keypoints(slide, title_text)
            point_pool = _build_input_derived_point_pool(
                slide,
                title_text=title_text,
                prefer_zh=prefer_zh,
                slide_type=str(slide.get("slide_type") or "content").strip().lower() or "content",
            )
            title_key = _normalize_text_key(title_text)
            numeric_values = _extract_numeric_values(
                " ".join([title_text, str(slide.get("narration") or ""), *keypoints])
            )
            semantic_text = " ".join(
                [
                    title_text,
                    str(slide.get("narration") or ""),
                    str(slide.get("semantic_type") or ""),
                    str(slide.get("semantic_subtype") or ""),
                    str(slide.get("content_subtype") or ""),
                    str(slide.get("subtype") or ""),
                    str(slide.get("page_type") or ""),
                    str(slide.get("page_role") or ""),
                ]
            ).strip()
            repaired_blocks: List[Dict[str, Any]] = []
            for b_idx, raw in enumerate(blocks):
                if not isinstance(raw, dict):
                    continue
                block = dict(raw)
                block_type = _as_block_type(block) or "body"
                if block_type in supported or block_type == "title":
                    repaired_blocks.append(block)
                    continue

                if block_type in _VISUAL_BLOCK_TYPES:
                    preferred_types = [
                        item
                        for item in ("workflow", "diagram", "image", "chart", "kpi", "table")
                        if item in supported
                    ]
                    if preferred_types:
                        replacement = _make_visual_contract_block(
                            preferred_types=preferred_types,
                            keypoints=keypoints,
                            numeric_values=numeric_values,
                            prefer_zh=prefer_zh,
                            semantic_text=semantic_text,
                            card_id=str(block.get("card_id") or f"compat_{idx + 1}_{b_idx + 1}"),
                            position=str(block.get("position") or "right"),
                        )
                        repaired_blocks.append(replacement)
                        continue

                text_value = _extract_block_text(block)
                if not text_value:
                    existing_keys = {
                        _normalize_text_key(_extract_block_text(item))
                        for item in repaired_blocks
                        if _as_block_type(item) != "title"
                    }
                    text_value = _pick_input_derived_point(
                        point_pool=point_pool,
                        title_text=title_text or str(slide.get("slide_id") or "slide"),
                        prefer_zh=prefer_zh,
                        index=b_idx + 1,
                        title_key=title_key,
                        existing_keys=existing_keys,
                        slide_type=str(slide.get("slide_type") or "content").strip().lower() or "content",
                    )
                fallback_text_type = "body" if "body" in supported else ("list" if "list" in supported else "subtitle")
                repaired_blocks.append(
                    {
                        "block_type": fallback_text_type,
                        "card_id": str(block.get("card_id") or f"compat_text_{idx + 1}_{b_idx + 1}"),
                        "position": str(block.get("position") or "left"),
                        "content": text_value,
                        "emphasis": [text_value[:16]] if text_value else [],
                    }
                )
            if repaired_blocks:
                slide["blocks"] = _dedupe_blocks(repaired_blocks)

    def _collect_contract_gaps(slide: Dict[str, Any]) -> List[str]:
        gaps: List[str] = []
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type in {"cover", "summary", "toc", "divider", "hero_1"}:
            return gaps

        blocks = slide.get("blocks")
        rows = [dict(item) for item in blocks if isinstance(item, dict)] if isinstance(blocks, list) else []
        if not rows:
            return ["missing_blocks"]

        has_title = any(_as_block_type(block) == "title" for block in rows)
        has_text = any(_as_block_type(block) in {"body", "list", "quote", "icon_text"} for block in rows)
        if not has_title:
            gaps.append("missing_title")
        if not has_text:
            gaps.append("missing_text_block")

        template_family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
        if not template_family:
            template_family = _resolve_template_family(slide)
        profiles = _template_profiles(template_family)
        contract = shared_contract_profile(str(profiles.get("contract_profile") or "default"))
        visual_types = {
            str(item or "").strip().lower()
            for item in (contract.get("visual_anchor_types") or [])
            if str(item or "").strip()
        }
        if not visual_types:
            visual_types = {"chart", "kpi", "workflow", "diagram", "image", "table"}

        visual_count = len([block for block in rows if _as_block_type(block) in visual_types])
        min_visual = max(0, int(contract.get("min_visual_blocks") or 0))
        if visual_count < min_visual:
            gaps.append(f"min_visual_blocks<{min_visual}")
        min_text = max(0, int(contract.get("min_text_blocks") or 0))
        text_non_visual_count = len(
            [
                block
                for block in rows
                if _as_block_type(block) in _TEXTUAL_BLOCK_TYPES
                and _as_block_type(block) != "title"
                and _as_block_type(block) not in visual_types
            ]
        )
        effective_min_text = min_text
        if min_text > 0 and visual_count > min_visual:
            reduction = max(0, visual_count - min_visual)
            effective_min_text = max(1, min_text - reduction)
        if text_non_visual_count < effective_min_text:
            gaps.append(f"min_text_blocks<{effective_min_text}")

        required_groups = [
            [str(item or "").strip().lower() for item in group if str(item or "").strip()]
            for group in (contract.get("required_one_of_groups") or [])
            if isinstance(group, list)
        ]
        for group in required_groups:
            if not group:
                continue
            if not any(_as_block_type(block) in set(group) for block in rows):
                gaps.append(f"required_one_of_missing:{'|'.join(group)}")

        if _slide_requires_image_anchor(slide, require_image_anchor=require_image_anchor) and (not _has_image_block(rows)):
            gaps.append("missing_image_anchor")
        return gaps

    def _reconcile_slide_contracts() -> None:
        reconciled: List[Dict[str, Any]] = []
        failures: List[str] = []
        template_ids = [str(item or "").strip().lower() for item in shared_template_ids() if str(item or "").strip()]
        for idx, raw_slide in enumerate(out.get("slides") or []):
            if not isinstance(raw_slide, dict):
                continue
            slide = _enforce_contract(raw_slide)
            gaps = _collect_contract_gaps(slide)
            if gaps and strict_contract_mode:
                slide_type = str(slide.get("slide_type") or "content").strip().lower() or "content"
                layout_grid = str(slide.get("layout_grid") or "split_2").strip().lower() or "split_2"
                best_slide = slide
                best_gaps = list(gaps)
                for candidate in template_ids:
                    if not _template_family_supports_slide(
                        candidate,
                        slide_type=slide_type,
                        layout_grid=layout_grid,
                    ):
                        continue
                    probe = dict(slide)
                    _set_slide_family(probe, candidate)
                    probe = _enforce_contract(probe)
                    probe_gaps = _collect_contract_gaps(probe)
                    if len(probe_gaps) < len(best_gaps):
                        best_slide = probe
                        best_gaps = probe_gaps
                    if not probe_gaps:
                        best_slide = probe
                        best_gaps = []
                        break
                slide = best_slide
                gaps = best_gaps
            if gaps and strict_contract_mode:
                # Deterministic strict repair: synthesize contract-compliant
                # text/visual block composition once, then re-check gaps.
                slide = _ensure_content_contract(
                    slide,
                    min_content_blocks=min_content_blocks,
                    blank_area_max_ratio=float(quality_cfg.get("blank_area_max_ratio") or 0.45),
                    require_image_anchor=require_image_anchor,
                    strict_contract=False,
                )
                gaps = _collect_contract_gaps(slide)
            if gaps and (not strict_contract_mode):
                # One extra deterministic repair pass after final template assignment.
                slide = _enforce_contract(slide)
                gaps = _collect_contract_gaps(slide)
            if gaps and (not strict_contract_mode):
                # Root-cause fallback minimization: when a family keeps violating
                # contract, reroute to a compatible family instead of injecting
                # opaque placeholders.
                fallback_family = resolve_template_for_slide(
                    slide=slide,
                    slide_type=str(slide.get("slide_type") or "content"),
                    layout_grid=str(slide.get("layout_grid") or "split_2"),
                    requested_template="",
                    desired_density=str(slide.get("content_density") or "balanced"),
                    preferred_tone=_infer_content_preferred_tone(str(out.get("template_family") or "")),
                )
                if fallback_family:
                    slide["template_family"] = str(fallback_family).strip().lower()
                    slide.update(_template_profiles(slide["template_family"]))
                    slide = _enforce_contract(slide)
                    gaps = _collect_contract_gaps(slide)
            if gaps:
                failures.append(f"s{idx + 1}:{';'.join(gaps[:4])}")
            reconciled.append(slide)
        out["slides"] = reconciled
        if failures:
            head = "; ".join(failures[:6])
            if strict_contract_mode:
                raise ValueError(f"visual_orchestration_contract_unmet:{head}")
            out["visual_contract_warnings"] = failures[:20]

    deck_template_preference = str(out.get("template_family") or "").strip().lower()
    deck_preferred_tone = _infer_content_preferred_tone(deck_template_preference)
    if not strict_contract_mode:
        _repair_slide_template_compatibility(
            deck_template_preference,
            preferred_tone=deck_preferred_tone,
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
            if bool(slide.get("template_lock")) and not allow_quality_template_unlock:
                # Respect explicitly locked families from upstream inputs.
                continue
            layout_grid = str(slide.get("layout_grid") or "").strip().lower() or "split_2"
            target_family = family_by_layout.get(layout_grid, family_default)
            if not target_family:
                continue
            current_family = str(slide.get("template_family") or "").strip().lower()
            if current_family == target_family:
                continue
            _set_slide_family(slide, target_family)

    # In dev_strict mode, when deck template is still auto, pin non-terminal
    # slides to one family to avoid pathological per-slide family switching.
    if (
        execution_profile == "dev_strict"
        and dev_strict_force_template_homogeneous
        and deck_template_mode not in {"", "auto"}
    ):
        pinned_family = (
            deck_template_mode
            if deck_template_mode not in {"", "auto"}
            else dev_strict_template_family
        )
        for slide in out["slides"]:
            if not isinstance(slide, dict):
                continue
            slide_type = str(slide.get("slide_type") or "").strip().lower()
            if slide_type in family_skip_types:
                continue
            candidate = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
            if candidate and candidate not in {"auto"}:
                pinned_family = candidate
                break
        for slide in out["slides"]:
            if not isinstance(slide, dict):
                continue
            slide_type = str(slide.get("slide_type") or "").strip().lower()
            if slide_type in family_skip_types:
                continue
            _set_slide_family(slide, pinned_family)
            slide["template_lock"] = True
        out["template_family"] = pinned_family

    content_family_budget = _derive_content_family_budget()
    _harmonize_content_family_pack(
        max_unique=content_family_budget,
        target_switch_ratio=float(quality_cfg.get("template_family_max_switch_ratio") or 0.75),
        max_top2_ratio=float(quality_cfg.get("template_family_max_top2_ratio") or 0.8),
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
        implicit_lock = slide_type in {"cover", "summary", "toc", "divider", "hero_1"}
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
        _set_slide_family(slide, normalized)
    _apply_education_light_template_policy()
    _dedupe_adjacent_template_repetition()
    _dedupe_content_sequence_template_repetition()
    _dedupe_content_global_template_reuse()
    _repair_slide_template_compatibility(
        str(out.get("template_family") or "").strip().lower(),
        preferred_tone=_infer_content_preferred_tone(str(out.get("template_family") or "").strip().lower()),
    )
    _repair_slide_block_capability_mismatch()
    for slide in out.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        layout_grid = str(slide.get("layout_grid") or "").strip().lower()
        if slide_type != "content" or layout_grid != "hero_1":
            continue
        current_family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
        if current_family and _template_family_supports_slide(current_family, slide_type="content", layout_grid="hero_1"):
            continue
        _set_slide_family(slide, "quote_hero_dark")
    if strict_contract:
        template_mismatches: List[str] = []
        block_mismatches: List[str] = []
        for idx, slide in enumerate(out.get("slides") or []):
            if not isinstance(slide, dict):
                continue
            slide_ref = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}")
            slide_type = str(slide.get("slide_type") or "content").strip().lower() or "content"
            layout_grid = str(slide.get("layout_grid") or "split_2").strip().lower() or "split_2"
            family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
            if family and not _template_family_supports_slide(
                family,
                slide_type=slide_type,
                layout_grid=layout_grid,
            ):
                template_mismatches.append(
                    f"{slide_ref}:template_family_incompatible:{family}:{slide_type}/{layout_grid}"
                )
            if not family:
                continue
            cap = shared_template_capabilities(family)
            supported = {
                str(item or "").strip().lower()
                for item in (cap.get("supported_block_types") or [])
                if str(item or "").strip()
            }
            if not supported:
                continue
            blocks = slide.get("blocks")
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                block_type = _as_block_type(block) or "body"
                if block_type == "title":
                    continue
                if block_type not in supported:
                    block_mismatches.append(
                        f"{slide_ref}:unsupported_block_type:{block_type}:{family}"
                    )
                    break
        if template_mismatches:
            raise ValueError(
                "visual_orchestration_template_incompatible: "
                + "; ".join(template_mismatches[:8])
            )
        if block_mismatches:
            raise ValueError(
                "visual_orchestration_block_capability_mismatch: "
                + "; ".join(block_mismatches[:8])
            )
    else:
        # Cohesion smoothing can assign visually incompatible families. Repair again
        # before locking templates for Node-side normalization.
        _repair_slide_template_compatibility(
            str(out.get("template_family") or "").strip().lower(),
            preferred_tone=_infer_content_preferred_tone(str(out.get("template_family") or "").strip().lower()),
        )
        # Compatibility repair can re-introduce family jitter for content pages;
        # smooth again with compatibility guards so switch ratio constraints hold.
        _smooth_content_family_switches_with_compatibility(
            max_switch_ratio=float(quality_cfg.get("template_family_max_switch_ratio") or 0.75)
        )
        _harmonize_content_family_pack(
            max_unique=content_family_budget,
            target_switch_ratio=float(quality_cfg.get("template_family_max_switch_ratio") or 0.75),
            max_top2_ratio=float(quality_cfg.get("template_family_max_top2_ratio") or 0.8),
        )
        _dedupe_adjacent_template_repetition()
        _dedupe_content_sequence_template_repetition()
        _dedupe_content_global_template_reuse()
        _repair_slide_template_compatibility(
            str(out.get("template_family") or "").strip().lower(),
            preferred_tone=_infer_content_preferred_tone(str(out.get("template_family") or "").strip().lower()),
        )
        _smooth_content_family_switches_with_compatibility(
            max_switch_ratio=float(quality_cfg.get("template_family_max_switch_ratio") or 0.75)
        )
        _repair_slide_block_capability_mismatch()
    _rebalance_utility_slides()
    _smooth_content_family_switches_with_compatibility(
        max_switch_ratio=float(quality_cfg.get("template_family_max_switch_ratio") or 0.75)
    )
    _harmonize_content_family_pack(
        max_unique=content_family_budget,
        target_switch_ratio=float(quality_cfg.get("template_family_max_switch_ratio") or 0.75),
        max_top2_ratio=float(quality_cfg.get("template_family_max_top2_ratio") or 0.8),
    )
    _reconcile_slide_contracts()
    if not strict_contract_mode:
        _smooth_content_family_switches_with_compatibility(
            max_switch_ratio=float(quality_cfg.get("template_family_max_switch_ratio") or 0.75)
        )
        _apply_education_light_template_policy()
        _dedupe_adjacent_template_repetition()
        _dedupe_content_sequence_template_repetition()
        _dedupe_content_global_template_reuse()
        _repair_slide_template_compatibility(
            str(out.get("template_family") or "").strip().lower(),
            preferred_tone=_infer_content_preferred_tone(str(out.get("template_family") or "").strip().lower()),
        )
        _smooth_content_family_switches_with_compatibility(
            max_switch_ratio=float(quality_cfg.get("template_family_max_switch_ratio") or 0.75)
        )

    final_density_sequence = [
        str((slide or {}).get("layout_grid") or "split_2").strip().lower()
        if isinstance(slide, dict)
        else "split_2"
        for slide in out.get("slides") or []
    ]
    final_density_sequence = enforce_density_rhythm(
        final_density_sequence,
        max_consecutive_high=int(quality_cfg.get("density_max_consecutive_high") or 2),
        window_size=int(quality_cfg.get("density_window_size") or 5),
        require_low_or_breathing_per_window=int(
            quality_cfg.get("density_require_low_or_breathing_per_window") or 1
        ),
    )
    for idx, layout in enumerate(final_density_sequence):
        if idx >= len(out.get("slides") or []):
            break
        slide = (out.get("slides") or [])[idx]
        if not isinstance(slide, dict):
            continue
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        if slide_type in {"cover", "summary", "toc", "divider"}:
            slide["layout_grid"] = "hero_1"
            continue
        assigned_layout = str(layout or "split_2").strip().lower() or "split_2"
        if assigned_layout == "hero_1":
            has_meaningful_content = any(
                _as_block_type(block) in {"body", "list", "chart", "kpi", "image", "workflow", "diagram", "table"}
                for block in (slide.get("blocks") or [])
                if isinstance(block, dict)
            )
            if has_meaningful_content:
                if slide_type not in {"cover", "summary", "toc", "divider"}:
                    slide["slide_type"] = "content"
            else:
                slide["slide_type"] = "divider"
        slide["layout_grid"] = assigned_layout

    theme_obj = out.get("theme") if isinstance(out.get("theme"), dict) else {}
    resolved_theme_recipe = canonicalize_theme_recipe(
        out.get("theme_recipe")
        or theme_obj.get("theme_recipe")
        or "auto",
        fallback="consulting_clean",
    )
    resolved_style_variant = style_variant_for_theme_recipe(
        resolved_theme_recipe,
        fallback=str(
            out.get("style_variant")
            or theme_obj.get("style")
            or out.get("minimax_style_variant")
            or "soft"
        ),
    )
    resolved_deck_tone = resolve_tone(
        out.get("tone")
        or theme_obj.get("tone")
        or "auto",
        theme_recipe=resolved_theme_recipe,
        fallback="auto",
    )
    out["theme_recipe"] = resolved_theme_recipe
    out["style_variant"] = resolved_style_variant
    out["tone"] = resolved_deck_tone
    theme_obj["theme_recipe"] = resolved_theme_recipe
    theme_obj["style"] = resolved_style_variant
    theme_obj["tone"] = resolved_deck_tone

    # Keep per-slide family/profile stable across Node-side normalization.
    for slide in out["slides"]:
        if not isinstance(slide, dict):
            continue
        for block in slide.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            if _as_block_type(block) != "title":
                continue
            block_title = _sanitize_placeholder_text(
                str(_extract_block_text(block) or "").strip(),
                prefer_zh=_prefer_zh(str(_extract_block_text(block) or ""), str(slide.get("narration") or "")),
            )
            if block_title:
                slide["title"] = block_title
            break
        slide_family = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
        resolved_tone = str(
            slide.get("tone")
            or slide.get("theme_tone")
            or out.get("tone")
            or resolve_tone(
                slide.get("theme_recipe")
                or out.get("theme_recipe")
                or theme_obj.get("theme_recipe")
                or "auto",
                theme_recipe=slide.get("theme_recipe")
                or out.get("theme_recipe")
                or theme_obj.get("theme_recipe")
                or "auto",
                fallback="auto",
            )
            or _template_family_tone(slide_family)
            or ""
        ).strip().lower()
        if resolved_tone in {"light", "dark"}:
            slide["tone"] = resolved_tone
            slide["theme_tone"] = resolved_tone
        if not str(slide.get("theme_recipe") or "").strip():
            if str(out.get("theme_recipe") or "").strip():
                slide["theme_recipe"] = str(out.get("theme_recipe")).strip().lower()
        slide["template_lock"] = True if family_lock_after else bool(slide.get("template_lock"))

    svg_mode = str(out.get("svg_mode") or "on").strip().lower()
    if svg_mode not in {"on", "off"}:
        svg_mode = "on"
    out["svg_mode"] = svg_mode
    out["slides"] = apply_render_paths(
        [slide for slide in out.get("slides") or [] if isinstance(slide, dict)],
        svg_mode=svg_mode,
    )
    if str(out.get("deck_archetype_profile") or "").strip().lower() == "education_textbook":
        for slide in out.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            if str(slide.get("slide_type") or "").strip().lower() == "content":
                slide["render_path"] = "pptxgenjs"
    out["design_spec"] = build_design_spec(
        theme=theme_obj,
        template_family=str(out.get("template_family") or ""),
        style_variant=str(theme_obj.get("style") or out.get("minimax_style_variant") or resolved_style_variant or "soft"),
        theme_recipe=str(
            out.get("theme_recipe")
            or theme_obj.get("theme_recipe")
            or "auto"
        ),
        tone=str(
            out.get("tone")
            or theme_obj.get("tone")
            or "auto"
        ),
        visual_preset=str(out.get("visual_preset") or "auto"),
        visual_density=str(out.get("visual_density") or "balanced"),
        visual_priority=bool(out.get("visual_priority", True)),
        topic=str(out.get("title") or ""),
    )
    out["enforce_visual_contract"] = True
    if not str(out.get("template_family") or "").strip():
        out["template_family"] = "auto"
    deck_template = str(out.get("template_family") or "").strip().lower()
    if deck_template in {"", "auto"}:
        deck_template = _infer_deck_template_family_from_rows(
            [row for row in out.get("slides") or [] if isinstance(row, dict)]
        )
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
            theme["style"] = resolved_style_variant
        if not str(theme.get("theme_recipe") or "").strip() or str(theme.get("theme_recipe")).strip().lower() == "auto":
            theme["theme_recipe"] = resolved_theme_recipe
        if not str(theme.get("tone") or "").strip() or str(theme.get("tone")).strip().lower() == "auto":
            theme["tone"] = resolved_deck_tone
        out["theme"] = theme
    normalized_slides = []
    for idx, raw_slide in enumerate(out.get("slides") if isinstance(out.get("slides"), list) else []):
        if not isinstance(raw_slide, dict):
            continue
        slide = raw_slide
        slide_id = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}").strip()
        slide["slide_id"] = slide_id or f"slide-{idx + 1}"
        slide["page_role"] = _slide_page_role(slide)
        archetype_plan = _select_slide_archetype_plan(slide)
        slide["archetype_plan"] = archetype_plan
        slide["archetype"] = str(archetype_plan.get("selected") or "thesis_assertion").strip().lower()
        slide["archetype_confidence"] = float(archetype_plan.get("confidence") or 0.0)
        slide["archetype_candidates"] = (
            archetype_plan.get("candidates")
            if isinstance(archetype_plan.get("candidates"), list)
            else []
        )[:3]
        slide_type = str(slide.get("slide_type") or "").strip().lower()
        layout_grid = str(slide.get("layout_grid") or "").strip().lower()
        if slide_type not in {"cover", "summary", "toc", "divider", "hero_1", "section"} and layout_grid == "hero_1":
            slide["slide_type"] = "section"
        normalized_slides.append(slide)
    if str(out.get("deck_archetype_profile") or "").strip().lower() == "education_textbook":
        for slide in normalized_slides:
            if not isinstance(slide, dict):
                continue
            slide_type = str(slide.get("slide_type") or "").strip().lower()
            if slide_type == "content":
                _set_slide_family(slide, "education_textbook_light")
                slide["render_path"] = "pptxgenjs"
                blocks = slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    if not _is_synthetic_ordinal_chart_block(block):
                        continue
                    payload = block.get("data") if isinstance(block.get("data"), dict) else block.get("content")
                    labels = payload.get("labels") if isinstance(payload, dict) and isinstance(payload.get("labels"), list) else []
                    prefer_zh = _prefer_zh(slide.get("title"), slide.get("narration"), labels)
                    table_rows = _table_data_from_keypoints([str(item or "").strip() for item in labels if str(item or "").strip()], prefer_zh=prefer_zh)
                    block["block_type"] = "table"
                    block["data"] = {"table_rows": table_rows, "source_type": "synthetic_table"}
                    block["content"] = {"table_rows": table_rows, "source_type": "synthetic_table"}
    out["slides"] = normalized_slides
    out["presentation_contract_v2"] = _build_presentation_contract_v2(out)
    contract_rows = (
        out["presentation_contract_v2"].get("slides")
        if isinstance(out.get("presentation_contract_v2"), dict)
        else []
    )
    layout_solver_actions = {"updated_slides": 0, "overflow_fixed": 0, "underflow_fixed": 0}
    if isinstance(contract_rows, list):
        layout_solver_actions = _apply_layout_solution_actions(out["slides"], contract_rows)
        if int(layout_solver_actions.get("updated_slides") or 0) > 0:
            out["presentation_contract_v2"] = _build_presentation_contract_v2(out)
            contract_rows = (
                out["presentation_contract_v2"].get("slides")
                if isinstance(out.get("presentation_contract_v2"), dict)
                else []
            )
    if isinstance(contract_rows, list):
        overflow_count = 0
        underflow_count = 0
        for row in contract_rows:
            if not isinstance(row, dict):
                continue
            layout_solution = row.get("layout_solution")
            if not isinstance(layout_solution, dict):
                continue
            status = str(layout_solution.get("status") or "").strip().lower()
            if status == "overflow":
                overflow_count += 1
            elif status == "underflow":
                underflow_count += 1
        out["layout_solver_summary"] = {
            "evaluated_slides": len(contract_rows),
            "overflow_slides": overflow_count,
            "underflow_slides": underflow_count,
            "updated_slides": int(layout_solver_actions.get("updated_slides") or 0),
            "overflow_fixed": int(layout_solver_actions.get("overflow_fixed") or 0),
            "underflow_fixed": int(layout_solver_actions.get("underflow_fixed") or 0),
        }
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
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
    except (
        urllib_error.URLError,
        urllib_error.HTTPError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
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


def _prepare_pipeline_contract_inputs(
    req: PPTPipelineRequest,
    *,
    execution_profile: str,
) -> Dict[str, Any]:
    """Normalize and enforce phase-1 pipeline contract fields."""
    normalized_required_facts = _dedup_strings(list(req.required_facts or []), limit=20)
    normalized_anchors = _dedup_strings(list(req.anchors or []), limit=20)

    if bool(req.reconstruct_from_reference):
        strict = str(execution_profile or "").strip().lower() == "dev_strict"
        audit = audit_reference_contract(
            reference_desc=req.reference_desc if isinstance(req.reference_desc, dict) else None,
            required_facts=normalized_required_facts or None,
            anchors=normalized_anchors or None,
            strict=strict,
        )
        if audit.errors:
            raise ValueError("Input contract invalid: " + "; ".join(audit.errors[:4]))
        req.reference_desc = audit.reference_desc
        normalized_required_facts = audit.required_facts
        normalized_anchors = audit.anchors

    anchor_constraints = [f"锚点约束:{item}" for item in normalized_anchors[:8]]
    normalized_constraints = _dedup_strings(
        [*(req.constraints or []), *anchor_constraints],
        limit=20,
    )

    req.required_facts = normalized_required_facts
    req.anchors = normalized_anchors
    req.constraints = normalized_constraints

    return {
        "required_facts": normalized_required_facts,
        "anchors": normalized_anchors,
        "constraints": normalized_constraints,
    }


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
                query_hint="目标受众 分层" if is_zh else "target audience segmentation",
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
                query_hint="商业目标 KPI" if is_zh else "business objective KPI",
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
                query_hint="品牌视觉 风格" if is_zh else "brand visual style",
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
                query_hint="核心指标 数据" if is_zh else "core metrics data",
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
                query_hint="近3年 趋势" if is_zh else "last 3 years trend",
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
                query_hint="中国 市场" if is_zh else "regional market",
            )
        )
    return gaps


def _normalize_research_topic(topic: str, *, is_zh: bool) -> str:
    raw = _normalize_unicode_text(topic)
    if not raw:
        return ""
    text = (
        raw.replace("“", "\"")
        .replace("”", "\"")
        .replace("‘", "'")
        .replace("’", "'")
        .strip()
    )
    if is_zh:
        for marker in ("主题为", "主题是", "主题:", "主题："):
            if marker not in text:
                continue
            candidate = text.split(marker, 1)[1].strip().strip("\"' ")
            candidate = re.split(r"[。！？!?]", candidate)[0].strip()
            if candidate:
                return candidate[:120]
    quoted = re.findall(r"[\"']([^\"']{3,160})[\"']", text)
    if quoted:
        candidate = max((item.strip() for item in quoted), key=len, default="")
        if candidate:
            return candidate[:120]
    text = re.sub(r"^(请|帮我)?\s*(制作|生成|创建|做)\s*(一份|一个|一套)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"(课堂展示)?课件|演示课件|演示文稿|ppt", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+", " ", text).strip("，,。:：;；")
    return text[:120] if text else raw[:120]


def _build_fallback_topic_points(topic: str, *, is_zh: bool, instructional_context: bool = False) -> List[str]:
    seed = str(topic or "").strip()
    if not seed:
        return []
    subject, focus = _split_topic_focus(seed, prefer_zh=is_zh)
    if instructional_context:
        scaffold = build_instructional_topic_points(seed, prefer_zh=is_zh)
        if scaffold:
            return _dedup_strings(scaffold, limit=8)
    if is_zh:
        impact = focus or f"{subject}的核心议题"
        return _dedup_strings([
            f"{subject}的背景与定义",
            f"{subject}的关键机制与结构",
            f"{subject}的主要参与方与职责",
            f"{subject}的流程步骤与关键节点",
            f"{subject}在国际关系中的影响路径",
            f"{subject}的代表性案例与数据证据",
            f"{subject}面临的争议、风险与约束",
            f"{impact}的案例与启示",
        ], limit=8)
    impact = focus or f"core agenda of {subject}"
    return _dedup_strings([
        f"Background and definition of {subject}",
        f"Key mechanisms and structure of {subject}",
        f"Main stakeholders and roles in {subject}",
        f"Process steps and decision checkpoints for {subject}",
        f"How {subject} influences international relations",
        f"Representative cases and supporting evidence for {subject}",
        f"Risks, tradeoffs, and controversies around {subject}",
        f"Cases and implications of {impact}",
    ], limit=8)


def _build_research_queries(
    req: ResearchRequest,
    *,
    is_zh: bool,
    gaps: List[ResearchGap],
) -> List[str]:
    topic_seed = _normalize_research_topic(str(req.topic or "").strip(), is_zh=is_zh) or str(req.topic or "").strip()
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
            q = " ".join(part for part in [topic_seed, fact, extras] if part).strip()
            if q:
                queries.append(q)
    for gap in gaps:
        if gap.query_hint:
            hint = str(gap.query_hint or "").strip()
            if topic_seed and hint and topic_seed.lower() in hint.lower():
                q = " ".join(part for part in [hint, extras] if part).strip()
            else:
                q = " ".join(part for part in [topic_seed, hint, extras] if part).strip()
            queries.append(q)

    if not queries:
        default_queries = (
            [
                f"{topic_seed} 背景 定义",
                f"{topic_seed} 关键机制 流程",
                f"{topic_seed} 数据 案例 证据",
            ]
            if is_zh
            else [
                f"{topic_seed} background definition",
                f"{topic_seed} key mechanism process",
                f"{topic_seed} data case evidence",
            ]
        )
        queries.extend(default_queries)

    return _dedup_strings(queries, limit=max(1, req.max_web_queries))


def _build_fallback_research_evidence(
    *,
    topic: str,
    key_points: List[str],
    references: List[Dict[str, str]],
    is_zh: bool,
    instructional_context: bool,
) -> List[ResearchEvidence]:
    fallback_url = "https://www.google.com/search?q=" + url_quote(str(topic or "").strip() or "topic")
    source_title = (
        str((references[0] or {}).get("title") or "").strip()
        if references and isinstance(references[0], dict)
        else ("Fallback topic synthesis" if not is_zh else "主题推导补充")
    )
    source_url = (
        str((references[0] or {}).get("url") or "").strip()
        if references and isinstance(references[0], dict)
        else fallback_url
    ) or fallback_url
    evidence_rows: List[ResearchEvidence] = []
    for idx, point in enumerate(key_points[:6]):
        related = [item for item in key_points if str(item or "").strip() and item != point]
        expanded = expand_semantic_support_points(
            core_message=point,
            related_points=related,
            instructional_context=instructional_context,
        )
        if not expanded:
            continue
        claim = str(expanded[0] or point).strip()[:500]
        snippet = "；".join(str(item or "").strip() for item in expanded[1:3] if str(item or "").strip()) if is_zh else "; ".join(str(item or "").strip() for item in expanded[1:3] if str(item or "").strip())
        evidence_rows.append(
            ResearchEvidence(
                claim=claim,
                source_title=source_title[:300] or ("Fallback synthesis" if not is_zh else "补充推导"),
                source_url=source_url,
                snippet=snippet[:800],
                confidence=0.46,
                provenance="fallback",
                tags=[str(point)[:60]],
            )
        )
        if idx >= 5:
            break
    return evidence_rows


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


_RELEVANCE_EN_STOPWORDS = {
    "about",
    "with",
    "from",
    "this",
    "that",
    "their",
    "your",
    "presentation",
    "slides",
}
_RELEVANCE_ZH_NOISE = {
    "我们",
    "你们",
    "他们",
    "这个",
    "那个",
    "相关",
    "内容",
    "主题",
    "问题",
}
_MOJIBAKE_MARKERS = ("Ã", "Â", "â€", "ï¼", "æ", "ç", "è", "é", "ð")
_MOJIBAKE_CJK_MARKERS = (
    "鍙",
    "鐨",
    "銆",
    "锛",
    "闄",
    "鏁",
    "璇",
    "鎹",
    "澶",
    "涓€",
)
_MOJIBAKE_CJK_TOKENS = (
    "忙聹",
    "盲禄",
    "聯氓",
    "潞聯",
    "莽職",
    "盲赂",
    "猫娄",
    "猫麓",
    "聙聟",
    "澶ф暟",
    "鍏虫暟",
    "鏍稿績",
    "鍥介檯",
    "绔嬫硶",
    "鐮旂┒",
)
_MOJIBAKE_CJK_CHARS = set("聹禄聯潞莽職聞赂娄聛麓聦庐聙聟鍙鐨銆锛闄鏁璇鎹澶涓鏄鏈")
_COMMON_ZH_FUNCTION_CHARS = "的一是在不了和对与其将由及中而可也"
_TOPIC_ZH_HINT_CHARS = "背景目标策略机制流程案例数据趋势方法实践应用教育商业技术政策"
_SOFTWARE_TOPIC_HINTS = {
    "ai",
    "github",
    "开源",
    "代码",
    "编程",
    "软件",
    "框架",
    "python",
    "agent",
}
_RESEARCH_NOISE_TERMS = {
    "prompt",
    "github",
    "gitee",
    "pptagent",
    "pypi",
    "开源",
    "仓库",
    "贡献者",
    "速速收藏",
}


def _text_naturalness_score(text: str, *, prefer_zh: bool) -> float:
    value = str(text or "").strip()
    if not value:
        return -1.0
    cjk_chars = [ch for ch in value if "\u4e00" <= ch <= "\u9fff"]
    if prefer_zh or len(cjk_chars) >= 4:
        cjk_len = float(max(1, len(cjk_chars)))
        common_hits = sum(value.count(ch) for ch in _COMMON_ZH_FUNCTION_CHARS)
        topic_hits = sum(value.count(ch) for ch in _TOPIC_ZH_HINT_CHARS)
        punct_hits = sum(value.count(ch) for ch in "，。；：、！？（）《》“”")
        marker_hits = sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)
        token_hits = sum(1 for token in _MOJIBAKE_CJK_TOKENS if token in value)
        return (
            (common_hits * 1.0)
            + (topic_hits * 1.2)
            + (punct_hits * 0.6)
            - (marker_hits * 2.0)
            - (token_hits * 3.0)
        ) / cjk_len
    words = re.findall(r"[A-Za-z]{3,}", value)
    marker_hits = sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)
    return float(len(words)) - float(marker_hits * 2)


def _normalize_unicode_text(text: str) -> str:
    value = str(text or "")
    if not value:
        return ""
    normalized = unicodedata.normalize("NFC", value).replace("\ufeff", "")
    return normalized.strip()


def _repair_mojibake_text(text: str, *, prefer_zh: bool) -> str:
    # Root-cause policy: keep source text in Unicode and do not perform
    # cross-encoding re-decode heuristics in the main pipeline.
    _ = prefer_zh
    return _normalize_unicode_text(text)


def _extract_relevance_terms(*texts: object) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()

    def _push(token: str) -> None:
        t = str(token or "").strip().lower()
        if not t:
            return
        if t in seen:
            return
        seen.add(t)
        out.append(t)

    for text in texts:
        raw = str(text or "").strip().lower()
        if not raw:
            continue
        for word in re.findall(r"[a-z0-9]{4,}", raw):
            if word in _RELEVANCE_EN_STOPWORDS:
                continue
            _push(word)
        for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", raw):
            if chunk in _RELEVANCE_ZH_NOISE:
                continue
            _push(chunk)
            if len(chunk) >= 5:
                for n in (2, 3, 4):
                    if len(chunk) < n:
                        continue
                    for idx in range(0, len(chunk) - n + 1):
                        token = chunk[idx : idx + n]
                        if token in _RELEVANCE_ZH_NOISE:
                            continue
                        _push(token)
    return out[:80]


def _topic_relevance_score(
    *,
    topic: str,
    title: str,
    snippet: str,
    domain_terms: List[str] | None = None,
    required_facts: List[str] | None = None,
) -> float:
    haystack = f"{title}\n{snippet}".lower()
    terms = _extract_relevance_terms(
        topic,
        *(domain_terms or []),
        *(required_facts or []),
    )
    if not terms:
        return 1.0
    weighted_total = 0.0
    weighted_hit = 0.0
    for term in terms:
        weight = 1.0 + min(1.0, float(len(term)) / 6.0)
        weighted_total += weight
        if term and term in haystack:
            weighted_hit += weight
    if weighted_total <= 0:
        return 0.0
    return max(0.0, min(1.0, weighted_hit / weighted_total))


def _looks_mojibake(text: str, *, allow_repair: bool = True) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    length = max(1, len(value))
    latin_extended = sum(1 for ch in value if 0x00C0 <= ord(ch) <= 0x00FF)
    replacement_hits = value.count("\ufffd")
    marker_hits = sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)
    if replacement_hits > 0:
        return True
    if latin_extended / float(length) >= 0.08 and marker_hits >= 2:
        return True
    token_hits = sum(1 for token in _MOJIBAKE_CJK_TOKENS if token in value)
    if token_hits >= 2:
        return True
    cjk_chars = [ch for ch in value if "\u4e00" <= ch <= "\u9fff"]
    cjk_marker_hits = sum(value.count(marker) for marker in _MOJIBAKE_CJK_MARKERS)
    if len(cjk_chars) >= 8 and cjk_marker_hits >= 3:
        return True
    if len(cjk_chars) >= 8:
        cjk_marker_hits = sum(1 for ch in cjk_chars if ch in _MOJIBAKE_CJK_CHARS)
        common_zh_hits = sum(value.count(ch) for ch in "的了是在和对与及为中")
        if (
            cjk_marker_hits / float(len(cjk_chars)) >= 0.18
            and common_zh_hits / float(len(cjk_chars)) <= 0.06
        ):
            return True
        if cjk_marker_hits >= 2 and common_zh_hits == 0:
            return True
        _ = allow_repair
    return False


def _is_research_noise_hit(*, topic: str, title: str, snippet: str) -> bool:
    topic_text = str(topic or "").strip().lower()
    if any(marker in topic_text for marker in _SOFTWARE_TOPIC_HINTS):
        return False
    haystack = f"{title}\n{snippet}".lower()
    noise_hits = sum(1 for marker in _RESEARCH_NOISE_TERMS if marker in haystack)
    if noise_hits <= 0:
        return False
    if "prompt" in haystack:
        return True
    if "github" in haystack or "gitee" in haystack or "pypi" in haystack:
        return True
    return noise_hits >= 3


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
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
    except (
        urllib_error.URLError,
        urllib_error.HTTPError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
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
    legacy_hints = (
        "brand%20visual%20placeholder",
        "brand visual placeholder",
        "illustrative%20visual",
        "illustrative visual",
    )
    if any(hint in s for hint in legacy_hints):
        return True
    if "ppt-placeholder-image-v1" in s:
        return True
    if s.startswith("data:image/svg+xml"):
        # Decode data-uri body for stable marker detection.
        decoded = s
        comma_idx = s.find(",")
        if comma_idx >= 0:
            decoded = s[comma_idx + 1 :]
        try:
            decoded = url_unquote(decoded)
        except Exception:
            pass
        if "ppt-placeholder-image-v1" in decoded:
            return True
    return False


_DEFAULT_STOCK_IMAGE_DOMAIN_HINTS = (
    "unsplash.com",
    "images.unsplash.com",
    "pexels.com",
    "images.pexels.com",
    "pixabay.com",
    "cdn.pixabay.com",
    "freepik.com",
    "i.ibb.co",
    "picsum.photos",
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


_BUILTIN_STOCK_GALLERY: List[Dict[str, Any]] = [
    {"seed": "business-meeting", "title": "business meeting collaboration", "tags": ["business", "meeting", "team", "office", "collaboration"]},
    {"seed": "analytics-dashboard", "title": "analytics dashboard data visualization", "tags": ["analytics", "dashboard", "data", "chart", "kpi"]},
    {"seed": "industrial-factory", "title": "industrial manufacturing factory", "tags": ["industrial", "factory", "manufacturing", "production", "workshop"]},
    {"seed": "cnc-workshop", "title": "cnc machining workshop equipment", "tags": ["cnc", "machining", "equipment", "machine", "factory"]},
    {"seed": "technology-server", "title": "technology server room infrastructure", "tags": ["technology", "cloud", "server", "infrastructure", "architecture"]},
    {"seed": "finance-report", "title": "finance growth report chart", "tags": ["finance", "growth", "report", "revenue", "investment"]},
    {"seed": "marketing-campaign", "title": "marketing campaign strategy", "tags": ["marketing", "campaign", "strategy", "brand", "promotion"]},
    {"seed": "product-showcase", "title": "product showcase hero image", "tags": ["product", "showcase", "gallery", "brand", "display"]},
    {"seed": "education-classroom", "title": "education classroom learning", "tags": ["education", "learning", "training", "knowledge", "course"]},
    {"seed": "healthcare-lab", "title": "healthcare laboratory research", "tags": ["healthcare", "medical", "lab", "research", "science"]},
    {"seed": "city-night", "title": "modern city skyline", "tags": ["city", "urban", "future", "growth", "market"]},
    {"seed": "supply-chain", "title": "logistics supply chain", "tags": ["logistics", "supply", "chain", "warehouse", "transport"]},
    {"seed": "customer-service", "title": "customer support service", "tags": ["customer", "service", "support", "experience", "retention"]},
    {"seed": "startup-team", "title": "startup team brainstorming", "tags": ["startup", "team", "brainstorm", "innovation", "planning"]},
    {"seed": "automation-workflow", "title": "automation workflow process", "tags": ["workflow", "automation", "process", "pipeline", "orchestration"]},
]


def _search_builtin_stock_gallery(
    *,
    query: str,
    num: int = 6,
    allow_fallback: bool = True,
) -> List[Dict[str, str]]:
    """Rank images from a lightweight built-in stock gallery (no web search)."""
    tokens = _tokenize_semantic_terms(query)
    query_blob = str(query or "").strip().lower()
    semantic_alias = {
        "工业": "industrial",
        "制造": "manufacturing",
        "产线": "production",
        "机床": "machine",
        "设备": "equipment",
        "工厂": "factory",
        "数据": "data",
        "图表": "chart",
        "分析": "analytics",
        "营销": "marketing",
        "品牌": "brand",
        "教育": "education",
        "学习": "learning",
        "医疗": "medical",
        "健康": "healthcare",
        "物流": "logistics",
        "供应链": "supply",
        "工作流": "workflow",
        "流程": "process",
        "自动化": "automation",
        "城市": "city",
        "金融": "finance",
        "团队": "team",
    }
    for key, alias in semantic_alias.items():
        if key in query_blob and alias not in tokens:
            tokens.append(alias)
    scored: List[tuple[float, Dict[str, Any]]] = []

    for item in _BUILTIN_STOCK_GALLERY:
        tags = [str(t).strip().lower() for t in item.get("tags", []) if str(t).strip()]
        blob = " ".join([str(item.get("title") or "").lower(), *tags])
        score = 0.0
        for token in tokens[:16]:
            if token in tags:
                score += 2.0
            elif token in blob:
                score += 0.8
        if not tokens:
            score = 0.1
        scored.append((score, item))

    scored.sort(key=lambda row: row[0], reverse=True)
    out: List[Dict[str, str]] = []
    wanted = max(3, min(10, int(num)))
    for score, item in scored:
        if tokens and score <= 0:
            continue
        seed = str(item.get("seed") or "").strip()
        if not seed:
            continue
        out.append(
            {
                "title": str(item.get("title") or "").strip(),
                "url": f"https://picsum.photos/seed/ppt-{url_quote(seed)}/1600/900",
                "source": "https://picsum.photos/",
            }
        )
        if len(out) >= wanted:
            break

    # Optional deterministic fallback when semantic overlap is weak.
    if not out and allow_fallback:
        for item in _BUILTIN_STOCK_GALLERY[:wanted]:
            seed = str(item.get("seed") or "").strip()
            if not seed:
                continue
            out.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "url": f"https://picsum.photos/seed/ppt-{url_quote(seed)}/1600/900",
                    "source": "https://picsum.photos/",
                }
            )
    return out


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


def _collect_image_asset_issues(render_payload: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    slides = render_payload.get("slides")
    if not isinstance(slides, list):
        return issues
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        slide_ref = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}")
        blocks = slide.get("blocks")
        if not isinstance(blocks, list):
            continue
        for b_idx, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            if str(block.get("block_type") or block.get("type") or "").strip().lower() != "image":
                continue
            content_obj = block.get("content")
            data_obj = block.get("data")
            content = dict(content_obj) if isinstance(content_obj, dict) else {}
            data = dict(data_obj) if isinstance(data_obj, dict) else {}
            url = ""
            for key in ("url", "src", "imageUrl", "image_url"):
                url = str(content.get(key) or data.get(key) or block.get(key) or "").strip()
                if url:
                    break
            source_type = str(data.get("source_type") or "").strip().lower()
            if not url:
                issues.append(f"{slide_ref}:image[{b_idx}]:missing_url")
                continue
            if _is_placeholder_image_url(url):
                issues.append(f"{slide_ref}:image[{b_idx}]:placeholder_url")
                continue
            if source_type in {"placeholder", "missing", "icon_bg"}:
                issues.append(f"{slide_ref}:image[{b_idx}]:fallback_source:{source_type}")
    return issues


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
    provider_raw = str(os.getenv("PPT_IMAGE_ASSET_PROVIDER", "auto")).strip().lower()
    if provider_raw not in {"auto", "serper", "gallery"}:
        provider_raw = "auto"
    image_asset_provider = provider_raw
    auto_builtin_gallery_enabled = (
        str(os.getenv("PPT_IMAGE_BUILTIN_AUTO_ENABLED", "false")).strip().lower()
        not in {"0", "false", "no", "off"}
    )
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

    async def _search_ranked_serper_candidates(keyword: str) -> List[Dict[str, str]]:
        if not serper_enabled:
            return []
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
        return _dedupe_image_candidates([*stock_candidates, *generic_candidates])

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
            serper_keyword_limit_raw = str(
                os.getenv("PPT_IMAGE_SERPER_KEYWORD_LIMIT", "5")
            ).strip()
            try:
                serper_keyword_limit = int(serper_keyword_limit_raw)
            except ValueError:
                serper_keyword_limit = 5
            serper_keyword_limit = max(3, min(5, serper_keyword_limit))
            query_candidates = _dedupe_terms(
                [search_query, *keywords],
                limit=serper_keyword_limit if image_asset_provider == "serper" else 5,
            )
            for keyword in query_candidates:
                if keyword not in image_search_cache:
                    ranked_candidates: List[Dict[str, str]] = []
                    if image_asset_provider == "gallery":
                        ranked_candidates = _search_builtin_stock_gallery(
                            query=keyword,
                            num=8,
                            allow_fallback=True,
                        )
                    elif image_asset_provider == "serper":
                        ranked_candidates = await _search_ranked_serper_candidates(keyword)
                    else:
                        ranked_candidates = await _search_ranked_serper_candidates(keyword)
                        if (not ranked_candidates) and auto_builtin_gallery_enabled:
                            ranked_candidates = _search_builtin_stock_gallery(
                                query=keyword,
                                num=8,
                                allow_fallback=True,
                            )
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
        raw_topic = _normalize_unicode_text(req.topic)
        required_facts = _dedup_strings(list(req.required_facts or []), limit=12)
        is_zh = req.language == "zh-CN" or _prefer_zh(
            raw_topic,
            req.audience,
            req.purpose,
            req.style_preference,
            req.constraints,
            req.required_facts,
        )
        topic = _normalize_research_topic(raw_topic, is_zh=is_zh) or raw_topic
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
            fallback_key_data_points = _dedup_strings(
                [
                    *required_facts,
                    *[str(item or "").strip() for item in (req.domain_terms or [])],
                    *[str(item or "").strip() for item in (req.constraints or [])],
                    *_build_fallback_topic_points(
                        topic,
                        is_zh=True,
                        instructional_context=is_instructional_context(
                            " ".join([
                                str(req.topic or ""),
                                str(req.audience or ""),
                                str(req.purpose or ""),
                                str(req.style_preference or ""),
                            ])
                        ),
                    ),
                ],
                limit=8,
            )
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
            fallback_key_data_points = _dedup_strings(
                [
                    *required_facts,
                    *[str(item or "").strip() for item in (req.domain_terms or [])],
                    *[str(item or "").strip() for item in (req.constraints or [])],
                    *_build_fallback_topic_points(
                        topic,
                        is_zh=False,
                        instructional_context=is_instructional_context(
                            " ".join([
                                str(req.topic or ""),
                                str(req.audience or ""),
                                str(req.purpose or ""),
                                str(req.style_preference or ""),
                            ])
                        ),
                    ),
                ],
                limit=8,
            )
        if not fallback_key_data_points:
            fallback_key_data_points = [topic]
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
        relevance_min_score = float(
            _to_float(
                _env_value(
                    "PPT_RESEARCH_MIN_RELEVANCE_SCORE",
                    "0.18" if is_zh else "0.14",
                ),
                0.18 if is_zh else 0.14,
            )
            or (0.18 if is_zh else 0.14)
        )

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
                    if _looks_mojibake(title) or _looks_mojibake(snippet):
                        continue
                    if _is_research_noise_hit(topic=topic, title=title, snippet=snippet):
                        continue
                    relevance_score = _topic_relevance_score(
                        topic=topic,
                        title=title,
                        snippet=snippet,
                        domain_terms=list(req.domain_terms or []),
                        required_facts=required_facts,
                    )
                    if relevance_score < relevance_min_score:
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
                            confidence=max(confidence, round(relevance_score, 2)),
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
                        cleaned_snippet = _sanitize_placeholder_text(snippet[:180], prefer_zh=is_zh)
                        if cleaned_snippet and not _looks_mojibake(cleaned_snippet):
                            key_data_points.append(cleaned_snippet)
                    cleaned_title = _sanitize_placeholder_text(title[:140], prefer_zh=is_zh)
                    if cleaned_title and not _looks_mojibake(cleaned_title):
                        key_data_points.append(cleaned_title)
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
        research_point_pool = _dedup_strings(
            [*fallback_key_data_points, *required_facts, topic],
            limit=8,
        )
        guard = 0
        while len(dedup_points) < 3:
            seed = research_point_pool[guard % len(research_point_pool)] if research_point_pool else topic
            candidate = str(seed or "").strip() or str(topic or "").strip() or "topic"
            if guard >= max(1, len(research_point_pool)):
                candidate = f"{candidate} #{guard + 1}"
            dedup_points.append(candidate)
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

        if len(evidence) < 4:
            fallback_rows = _build_fallback_research_evidence(
                topic=topic,
                key_points=dedup_points,
                references=dedup_refs,
                is_zh=is_zh,
                instructional_context=is_instructional_context(
                    " ".join(
                        [
                            str(topic or ""),
                            str(req.audience or ""),
                            str(req.purpose or ""),
                            str(req.style_preference or ""),
                        ]
                    ).lower()
                ),
            )
            for row in fallback_rows:
                key = f"{row.claim.strip().lower()}|{row.source_url.strip().lower()}"
                if any(f"{item.claim.strip().lower()}|{item.source_url.strip().lower()}" == key for item in evidence):
                    continue
                evidence.append(row)
                if len(evidence) >= 8:
                    break

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
        context_blob = " ".join(
            [
                str(req.research.topic or ""),
                str(req.research.audience or ""),
                str(req.research.purpose or ""),
                str(req.research.style_preference or ""),
            ]
        ).lower()
        instructional_context = is_instructional_context(context_blob)

        def _parse_anchor_entry(text: str) -> tuple[int, str] | None:
            raw = str(text or "").strip()
            if not raw:
                return None
            # Format: S01:content:Title
            m = re.search(r"^S0*([1-9]\d*)\s*:[^:]*:\s*(.+)$", raw, flags=re.IGNORECASE)
            if m:
                page_no = int(m.group(1))
                title = str(m.group(2) or "").strip()
                if page_no >= 1 and title:
                    return page_no, title[:120]
            # Format: 第3页必须体现：标题 / 第3页主题锚点：标题
            m = re.search(r"第\s*([1-9]\d*)\s*页[^：:]{0,20}[：:]\s*(.+)$", raw, flags=re.IGNORECASE)
            if m:
                page_no = int(m.group(1))
                title = str(m.group(2) or "").strip()
                if page_no >= 1 and title:
                    return page_no, title[:120]
            # Format: slide 3: title
            m = re.search(r"\bslide\s*([1-9]\d*)\b[^:]{0,20}:\s*(.+)$", raw, flags=re.IGNORECASE)
            if m:
                page_no = int(m.group(1))
                title = str(m.group(2) or "").strip()
                if page_no >= 1 and title:
                    return page_no, title[:120]
            return None

        page_anchors: Dict[int, str] = {}
        for candidate in [*(req.research.constraints or []), *(req.research.required_facts or [])]:
            parsed = _parse_anchor_entry(str(candidate or ""))
            if not parsed:
                continue
            page_no, title = parsed
            if 1 <= page_no <= total_pages and title:
                page_anchors[page_no] = title

        notes = build_research_storyline_notes(
            topic=str(req.research.topic or ""),
            total_pages=total_pages,
            data_points=data_points,
            page_anchors=page_anchors,
            instructional_context=instructional_context,
        )
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
        if instructional_context:
            classroom_cycle = ["split_2", "asymmetric_2", "grid_3", "timeline", "grid_4", "split_2"]
            classroom_cursor = 0
            adjusted_notes = []
            for idx, note in enumerate(notes):
                current_layout = str(note.layout_hint or "").strip().lower()
                if 0 < idx < max(0, total_pages - 1) and current_layout not in {"toc", "summary", "cover", "divider"}:
                    current_layout = classroom_cycle[classroom_cursor % len(classroom_cycle)]
                    classroom_cursor += 1
                adjusted_notes.append(note.model_copy(update={"layout_hint": current_layout}))
            notes = adjusted_notes
            fixed_layouts = enforce_layout_diversity([note.layout_hint for note in notes])
            notes = [
                note.model_copy(update={"layout_hint": fixed_layouts[idx]})
                for idx, note in enumerate(notes)
            ]

        return OutlinePlan(
            title=req.research.topic,
            total_pages=total_pages,
            theme_suggestion="education_charts" if instructional_context else "business_authority",
            style_suggestion="rounded" if instructional_context else "soft",
            notes=notes,
            logic_flow=("先建立内容导航，再依次展开关键问题、证据与结论。" if is_zh else "Open with navigation, then build key issues, evidence, and conclusions."),
        )

    async def generate_presentation_plan(
        self, req: PresentationPlanRequest
    ) -> PresentationPlan:
        is_zh = _prefer_zh(req.outline.title, req.research.topic if req.research else "")
        total_outline_pages = len(req.outline.notes)
        plan_context_blob = " ".join(
            [
                str(req.outline.title or ""),
                str(req.research.topic if req.research else ""),
                str(req.research.audience if req.research else ""),
                str(req.research.purpose if req.research else ""),
            ]
        ).lower()
        classroom_context = is_instructional_context(plan_context_blob)

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

        def _needs_semantic_expansion(points: List[str], title_text: str) -> bool:
            normalized_title = _normalize_text_key(title_text)
            meaningful = [str(item or "").strip() for item in points if str(item or "").strip()]
            if len(meaningful) < 2:
                return True
            overlap_like = 0
            short_heading_like = 0
            for item in meaningful:
                key = _normalize_text_key(item)
                if key and normalized_title and (key in normalized_title or normalized_title in key):
                    overlap_like += 1
                if len(item) <= (18 if is_zh else 32) and not re.search(r"[，。；;,.!?：:]", item):
                    short_heading_like += 1
            if len(meaningful) >= 3 and overlap_like < len(meaningful):
                return False
            return overlap_like >= max(1, len(meaningful) - 1) or short_heading_like == len(meaningful)

        placeholder_patterns = (
            r"[?？]{2,}",
            r"\bxxxx\b",
            r"\btodo\b",
            r"\btbd\b",
            r"lorem ipsum",
            r"\bplaceholder\b",
            r"\bitem\s*\d+\b",
            r"指标[a-eA-E]",
            r"待补充",
            r"占位文案",
            r"默认文案",
            r"示例文案",
            r"请替换",
            r"to be filled",
            r"replace me",
            r"default copy",
        )

        def _has_placeholder(text: str) -> bool:
            value = str(text or "")
            for pattern in placeholder_patterns:
                if re.search(pattern, value, flags=re.IGNORECASE):
                    return True
            return False

        def _sanitize_block_text(
            text: str,
            *,
            fallback: str,
            max_chars: int,
        ) -> str:
            topic_seed = _sanitize_placeholder_text(
                str(req.outline.title or (req.research.topic if req.research else "") or "").strip(),
                prefer_zh=is_zh,
            )
            if topic_seed:
                default_fallback = (
                    f"{topic_seed}要点" if is_zh else f"Key point: {topic_seed}"
                )
            else:
                default_fallback = "核心观点" if is_zh else "Key insight"

            def _normalize_candidate(value: str) -> str:
                normalized = re.sub(r"\s+", " ", str(value or "").strip())
                normalized = normalized.replace("\ufffd", " ")
                normalized = re.sub(
                    r"^(?:核心问题|课堂提示|关键主体|角色分工|互动关系|起点|推进|转折点|传导起点|外部影响|反馈效应|案例背景|关键证据|课堂结论|争议焦点|现实约束|延伸思考|核心信息|逻辑关系|结论提示)\s*[:：-]\s*",
                    "",
                    normalized,
                    flags=re.IGNORECASE,
                )
                normalized = re.sub(r"[?？]{2,}", " ", normalized)
                normalized = re.sub(r"\b(?:xxxx|todo|tbd|placeholder)\b", " ", normalized, flags=re.IGNORECASE)
                normalized = re.sub(
                    r"(待补充|占位文案|默认文案|示例文案|请替换|to be filled|replace me|default copy)",
                    " ",
                    normalized,
                    flags=re.IGNORECASE,
                )
                normalized = re.sub(r"\bitem\s*\d+\b", " ", normalized, flags=re.IGNORECASE)
                normalized = re.sub(r"指标[a-eA-E]", "指标", normalized)
                normalized = re.sub(r"\s{2,}", " ", normalized).strip(" -:;,.，。；")
                return normalized

            safe_fallback = _normalize_candidate(fallback)
            if not safe_fallback or _has_placeholder(safe_fallback):
                safe_fallback = default_fallback

            value = _normalize_candidate(text)
            if not value or _has_placeholder(value):
                value = safe_fallback
            value = _normalize_candidate(value)
            if not value or _has_placeholder(value):
                value = default_fallback

            clipped = value[:max_chars].strip()
            if clipped:
                return clipped
            return (safe_fallback[:max_chars].strip() or default_fallback)

        def _build_cover_support_note(title_text: str) -> str:
            title_key = _normalize_text_key(title_text)
            candidates: List[str] = []
            research = req.research if isinstance(req.research, ResearchContext) else None
            if research:
                audience_blob = str(research.audience or "").strip().lower()
                if classroom_context:
                    if is_zh and any(token in audience_blob for token in {"high school", "高中"}):
                        candidates.append("高中课堂 · 展示课件")
                    elif is_zh:
                        candidates.append("课堂展示课件")
                    else:
                        candidates.append("Classroom presentation")
                audience = _sanitize_block_text(
                    str(research.audience or ""),
                    fallback="",
                    max_chars=48,
                ) if str(research.audience or "").strip() else ""
                purpose = _sanitize_block_text(
                    str(research.purpose or ""),
                    fallback="",
                    max_chars=48,
                ) if str(research.purpose or "").strip() else ""
                geography = _sanitize_block_text(
                    str(research.geography or ""),
                    fallback="",
                    max_chars=28,
                ) if str(research.geography or "").strip() else ""
                time_range = _sanitize_block_text(
                    str(research.time_range or ""),
                    fallback="",
                    max_chars=28,
                ) if str(research.time_range or "").strip() else ""
                primary_meta = [item for item in [audience, purpose] if item and _normalize_text_key(item) not in {"", title_key}]
                secondary_meta = [item for item in [geography, time_range] if item and _normalize_text_key(item) not in {"", title_key}]
                if primary_meta:
                    candidates.append((" · ".join(primary_meta[:2]))[:72])
                if secondary_meta:
                    candidates.append((" · ".join(secondary_meta[:2]))[:72])
            for candidate in candidates:
                key = _normalize_text_key(candidate)
                if not key or key == title_key or key in title_key or title_key in key:
                    continue
                return candidate[:72]
            return ""

        def _build_learning_goal_note(points: List[str], title_text: str) -> str:
            normalized = [str(item or "").strip() for item in points if str(item or "").strip()]
            primary = normalized[0] if normalized else (title_text[:20] or ("核心概念" if is_zh else "core concept"))
            secondary = normalized[1] if len(normalized) > 1 else (title_text[:20] or ("关键问题" if is_zh else "key issue"))
            if is_zh:
                return f"学习目标：你将能够识别{primary}，并分析{secondary}。"[:96]
            return f"Learning goal: you will be able to identify {primary} and analyze {secondary}."[:120]

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
            if (not classroom_context) and total_outline_pages >= 12 and ("section" in elements or "transition" in elements):
                return "divider"
            return _layout_to_slide_type(note.layout_hint)

        slides: List[SlidePlan] = []
        research_key_points = [
            str(item or "").strip()
            for item in [
                *[
                    str(e.claim or "").strip()
                    for e in ((req.research.evidence if req.research else []) or [])
                    if str(getattr(e, "claim", "") or "").strip()
                ],
                *[
                    str(e.snippet or "").strip()
                    for e in ((req.research.evidence if req.research else []) or [])
                    if str(getattr(e, "snippet", "") or "").strip()
                ],
                *((req.research.key_data_points if req.research else []) or []),
            ]
            if str(item or "").strip()
        ]
        for note_idx, note in enumerate(req.outline.notes):
            note_slide_type = _resolve_note_slide_type(note, note_idx)
            lower_elements = [str(item).strip().lower() for item in note.data_elements]
            strategy = build_slide_content_strategy(
                note,
                is_zh=is_zh,
                research_points=research_key_points,
            )
            title_text = _sanitize_block_text(
                str(strategy.assertion or note.core_message),
                fallback=(str(note.core_message or "").strip() or str(req.outline.title or "").strip()[:24]),
                max_chars=220,
            )
            outline_title = _sanitize_block_text(
                str(req.outline.title or "").strip(),
                fallback=title_text,
                max_chars=220,
            )
            if note_slide_type == "cover" and outline_title:
                title_text = outline_title
            elif (not classroom_context) and note_slide_type in {"toc", "summary"} and outline_title:
                title_text = outline_title
            elif (
                (not is_zh)
                and len(title_text) <= 30
                and re.search(r"[A-Za-z]{2,}$", title_text)
                and len(outline_title) >= len(title_text) + 8
            ):
                title_text = outline_title
            title_text = _clip_text_for_visual_budget(
                title_text,
                prefer_zh=is_zh,
                slide_type=note_slide_type,
                role="title",
            )
            compact_points = _compact_points(strategy.evidence or note.key_points, max_points=4, max_chars=96)
            if not compact_points:
                compact_points = _compact_points(
                    [
                        str(note.core_message or "").strip(),
                        *[str(item or "").strip() for item in (note.key_points or [])],
                        *[str(item or "").strip() for item in (note.data_elements or [])],
                        *[str(item or "").strip() for item in research_key_points[:3]],
                    ],
                    max_points=4,
                    max_chars=96,
                )
            if not compact_points:
                compact_points = [title_text[:24] or str(req.outline.title or "")[:24]]
            if note_slide_type not in {"cover", "toc", "summary"} and _needs_semantic_expansion(compact_points, title_text):
                compact_points = expand_semantic_support_points(
                    core_message=title_text,
                    related_points=[*compact_points, *(strategy.evidence or []), *(note.key_points or [])],
                    instructional_context=classroom_context,
                )
            compact_points = [
                _sanitize_block_text(
                    point,
                    fallback=(title_text[:24] or str(req.outline.title or "")[:24]),
                    max_chars=96,
                )
                for point in compact_points
            ]
            outline_title_key = _normalize_text_key(str(req.outline.title or ""))
            title_key = _normalize_text_key(title_text)
            compact_points = [
                point
                for point in compact_points
                if _normalize_text_key(point) not in {"", outline_title_key, title_key}
            ] or compact_points
            if classroom_context and note_slide_type not in {"cover", "toc", "summary"}:
                expanded_points = expand_semantic_support_points(
                    core_message=title_text,
                    related_points=[*compact_points, *(strategy.evidence or []), *(note.key_points or [])],
                    instructional_context=True,
                )
                merged_points = _compact_points(
                    [*expanded_points, *compact_points],
                    max_points=4,
                    max_chars=96,
                )
                compact_points = [
                    point
                    for point in merged_points
                    if _normalize_text_key(point) not in {"", outline_title_key, title_key}
                    and not _is_low_signal_point_text(point)
                ] or compact_points
            layout_plan = build_content_layout_plan(
                title=title_text,
                evidence=compact_points,
                visual_anchor=note.visual_anchor,
                data_elements=note.data_elements,
                layout_hint=note.layout_hint,
            )
            block_flags = dict(layout_plan.get("block_flags") or {})
            template_whitelist = [
                str(item or "").strip().lower()
                for item in (layout_plan.get("template_whitelist") or [])
                if str(item or "").strip()
            ][:4]
            selected_archetype = str(layout_plan.get("archetype") or "").strip().lower()
            need_chart = bool(block_flags.get("chart"))
            need_kpi = bool(block_flags.get("kpi"))
            need_image = bool(block_flags.get("image"))
            need_comparison = bool(block_flags.get("comparison"))
            use_dual_text = bool(block_flags.get("dual_text", True))

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
                            content=_sanitize_block_text(
                                (
                                    str(note.core_message or "")
                                    or str(req.outline.title or "")
                                ),
                                fallback=(title_text[:24] or str(req.outline.title or "")[:24]),
                                max_chars=240,
                            ),
                            emphasis=["value"],
                        )
                    )
            elif classroom_context and note_slide_type == "toc":
                blocks.append(
                    ContentBlock(
                        block_type="subtitle",
                        position="top_right",
                        content=_sanitize_block_text(
                            _build_learning_goal_note(compact_points, title_text),
                            fallback=(title_text[:24] or str(req.outline.title or "")[:24]),
                            max_chars=160,
                        ),
                        emphasis=["学习目标"] if is_zh else ["learning goal"],
                    )
                )
            elif note.layout_hint == "summary":
                blocks.append(
                    ContentBlock(
                        block_type="list",
                        position="center",
                        content=_sanitize_block_text(
                            "; ".join(compact_points[:3]),
                            fallback="; ".join(compact_points[:2]) or title_text[:24],
                            max_chars=320,
                        ),
                        emphasis=["conclusion", "action"] if not is_zh else ["结论", "行动"],
                    )
                )
            else:
                left_points, right_points = _split_points_for_two_columns(compact_points)
                if not left_points:
                    left_points = compact_points[:1]
                if not right_points:
                    right_points = compact_points[-1:] or left_points[:1]
                left_joined = "; ".join(left_points).strip().lower()
                right_joined = "; ".join(right_points).strip().lower()
                if (not right_joined) or right_joined == left_joined:
                    alt_candidates = [
                        item
                        for item in compact_points
                        if str(item or "").strip().lower() not in {str(p or "").strip().lower() for p in left_points}
                    ]
                    if alt_candidates:
                        right_points = alt_candidates[: max(1, min(2, len(alt_candidates)))]
                    else:
                        fallback_seed = _sanitize_block_text(
                            str(strategy.data_anchor or note.visual_anchor or title_text),
                            fallback=(title_text[:24] or str(req.outline.title or "")[:24]),
                            max_chars=64,
                        )
                        if fallback_seed:
                            right_points = [fallback_seed]
                classroom_anchor = str(note.visual_anchor or "").strip().lower()
                if classroom_context and note_slide_type == "content":
                    if classroom_anchor == "roles":
                        blocks.append(
                            ContentBlock(
                                block_type="comparison",
                                position="center",
                                content={
                                    "left_title": "关键角色" if is_zh else "Key actors",
                                    "left_items": left_points[:3],
                                    "right_title": "核心职能" if is_zh else "Core functions",
                                    "right_items": right_points[:3],
                                    "summary": compact_points[-1] if compact_points else title_text,
                                },
                                emphasis=["角色"] if is_zh else ["actors"],
                            )
                        )
                        need_chart = need_kpi = need_image = False
                        need_comparison = False
                        use_dual_text = False
                    elif classroom_anchor == "impact":
                        blocks.append(
                            ContentBlock(
                                block_type="comparison",
                                position="center",
                                content={
                                    "left_title": "内部变化" if is_zh else "Internal change",
                                    "left_items": left_points[:3],
                                    "right_title": "外部影响" if is_zh else "External impact",
                                    "right_items": right_points[:3],
                                    "summary": compact_points[-1] if compact_points else title_text,
                                },
                                emphasis=["影响"] if is_zh else ["impact"],
                            )
                        )
                        need_chart = need_kpi = need_image = False
                        need_comparison = False
                        use_dual_text = False
                    elif classroom_anchor == "process":
                        blocks.append(
                            ContentBlock(
                                block_type="workflow",
                                position="center",
                                content=" -> ".join((compact_points[:4] or [title_text])[:4]),
                                emphasis=compact_points[:2] or [title_text[:16]],
                            )
                        )
                        need_chart = need_kpi = need_image = False
                        need_comparison = False
                        use_dual_text = False
                    elif classroom_anchor == "case":
                        blocks.append(
                            ContentBlock(
                                block_type="quote",
                                position="right",
                                content=right_points[0] if right_points else (compact_points[-1] if compact_points else title_text),
                                emphasis=["案例"] if is_zh else ["case"],
                            )
                        )
                        need_chart = need_kpi = need_image = False
                    elif classroom_anchor == "trend":
                        blocks.append(
                            ContentBlock(
                                block_type="quote",
                                position="right",
                                content=right_points[0] if right_points else (compact_points[-1] if compact_points else title_text),
                                emphasis=["趋势"] if is_zh else ["trend"],
                            )
                        )
                        need_chart = need_kpi = need_image = False
                if need_kpi:
                    kpi_value = _kpi_seed(note.page_number)
                    blocks.append(
                        ContentBlock(
                            block_type="kpi",
                            position="left",
                            content=title_text[:24],
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
                            content=title_text[:24],
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
                            content=title_text[:24],
                            data={
                                "title": title_text,
                                "keywords": [
                                    title_text,
                                    *compact_points[:2],
                                    str(note.visual_anchor or "").strip(),
                                ],
                            },
                            emphasis=["visual_anchor"],
                        )
                    )
                if need_comparison:
                    left_title = _sanitize_block_text(
                        left_points[0] if left_points else ("当前方案" if is_zh else "Current model"),
                        fallback=(title_text[:24] or str(req.outline.title or "")[:24]),
                        max_chars=40,
                    )
                    right_title = _sanitize_block_text(
                        right_points[0] if right_points else ("目标方案" if is_zh else "Target model"),
                        fallback=(title_text[:24] or str(req.outline.title or "")[:24]),
                        max_chars=40,
                    )
                    left_items = [
                        _sanitize_block_text(
                            item,
                            fallback=left_title,
                            max_chars=72,
                        )
                        for item in (left_points[1:] or left_points[:2] or [left_title])
                    ][:3]
                    right_items = [
                        _sanitize_block_text(
                            item,
                            fallback=right_title,
                            max_chars=72,
                        )
                        for item in (right_points[1:] or right_points[:2] or [right_title])
                    ][:3]
                    summary_text = _sanitize_block_text(
                        str(strategy.data_anchor or compact_points[-1] or title_text),
                        fallback=(title_text[:24] or str(req.outline.title or "")[:24]),
                        max_chars=120,
                    )
                    blocks.append(
                        ContentBlock(
                            block_type="comparison",
                            position="center",
                            content={
                                "left_title": left_title,
                                "left_items": left_items,
                                "right_title": right_title,
                                "right_items": right_items,
                                "summary": summary_text,
                            },
                            emphasis=["contrast"] if not is_zh else ["对比"],
                        )
                    )
                    blocks.append(
                        ContentBlock(
                            block_type="body",
                            position="bottom",
                            content=summary_text,
                            emphasis=["focus"] if not is_zh else ["重点"],
                        )
                    )
                else:
                    blocks.append(
                        ContentBlock(
                            block_type="body",
                            position="left",
                            content=_sanitize_block_text(
                                "; ".join(left_points),
                                fallback=(title_text[:24] or str(req.outline.title or "")[:24]),
                                max_chars=320,
                            ),
                            emphasis=["focus"] if not is_zh else ["重点"],
                        )
                    )
                if (not need_comparison) and (use_dual_text or (not need_chart and not need_image)):
                    blocks.append(
                        ContentBlock(
                            block_type="list",
                            position="right",
                            content=_sanitize_block_text(
                                "; ".join(right_points),
                                fallback=(title_text[:24] or str(req.outline.title or "")[:24]),
                                max_chars=320,
                            ),
                            emphasis=["evidence"] if not is_zh else ["证据"],
                        )
                    )

            slides.append(
                SlidePlan(
                    page_number=note.page_number,
                    slide_type=note_slide_type,  # type: ignore[arg-type]
                    layout_grid=note.layout_hint,
                    blocks=blocks,
                    bg_style="light",
                    archetype=selected_archetype,
                    template_candidates=template_whitelist,
                    image_keywords=[
                        title_text,
                        *compact_points[:2],
                        str(note.visual_anchor or "").strip(),
                    ],
                    content_strategy=SlideContentStrategy(
                        assertion=title_text[:220],
                        evidence=compact_points[:6],
                        data_anchor=str(strategy.data_anchor or "")[:160],
                        page_role=str(strategy.page_role or "argument"),
                        density_hint=str(strategy.density_hint or "medium"),
                        render_path=str(strategy.render_path or "pptxgenjs"),
                    ),
                    notes_for_designer=(
                        _build_cover_support_note(title_text)
                        if note_slide_type == "cover"
                        else (
                            ("先看整体结构，再进入核心概念、机制、案例与总结。" if is_zh else "Start with the full lesson map, then move into concepts, mechanisms, cases, and summary.")
                            if note_slide_type == "toc" and classroom_context
                            else str(note.speaker_notes or title_text[:80])
                        )
                    ),
                )
            )
            if template_whitelist:
                slide_payload = slides[-1]
                slide_payload.notes_for_designer = (
                    f"{slide_payload.notes_for_designer}\nTEMPLATE_WHITELIST: {','.join(template_whitelist[:4])}"
                )[:500]

        return PresentationPlan(
            title=req.outline.title,
            theme=req.outline.theme_suggestion,
            style=req.outline.style_suggestion,
            slides=slides,
            global_notes=str(req.outline.logic_flow or req.outline.title),
        )

    async def run_ppt_pipeline(self, req: PPTPipelineRequest) -> PPTPipelineResult:
        from src.minimax_exporter import export_minimax_pptx
        from src.ppt_quality_gate import (
            score_visual_professional_metrics,
            score_deck_quality,
            validate_deck,
            validate_layout_diversity,
            validate_visual_audit,
        )
        from src.ppt_route_strategy import resolve_route_policy

        run_id = _new_id()
        stages: List[PPTPipelineStageStatus] = []
        requested_execution_profile = _resolve_execution_profile_for_runtime(
            req.execution_profile
        )
        _enforce_dev_fast_fail_profile(
            requested_execution_profile,
            stage="run_ppt_pipeline",
        )
        _prepare_pipeline_contract_inputs(
            req,
            execution_profile=requested_execution_profile,
        )
        requested_quality_profile = _resolve_quality_profile_id(
            req.quality_profile,
            topic=req.topic,
            purpose=req.purpose,
            audience=req.audience,
            total_pages=req.total_pages,
        )
        requested_template_family = str(getattr(req, "template_family", "auto") or "auto").strip().lower() or "auto"
        requested_skill_profile = str(getattr(req, "skill_profile", "auto") or "auto").strip() or "auto"
        requested_theme_recipe = str(getattr(req, "theme_recipe", "auto") or "auto").strip().lower() or "auto"
        requested_tone = str(getattr(req, "tone", "auto") or "auto").strip().lower() or "auto"
        requested_deck_archetype_profile = _derive_deck_archetype_profile(
            topic=req.topic,
            audience=req.audience,
            purpose=req.purpose,
            quality_profile=requested_quality_profile,
            theme_recipe=requested_theme_recipe,
        )
        if requested_tone not in {"auto", "light", "dark"}:
            requested_tone = "auto"
        requested_template_file_url = str(getattr(req, "template_file_url", "") or "").strip()
        has_explicit_template = (
            requested_template_family not in {"", "auto"} or bool(requested_template_file_url)
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
            has_explicit_template=has_explicit_template,
            visual_density="balanced",
        )
        requested_force_ppt_master = req.force_ppt_master

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
        research_timeout = _pipeline_stage_timeout_sec("research", 120)
        try:
            research = await asyncio.wait_for(
                self.generate_research_context(research_req),
                timeout=research_timeout,
            )
        except asyncio.TimeoutError as exc:
            diag = [f"timeout>{research_timeout}s", "stage=research"]
            _append_stage("research", research_started, False, diag)
            raise ValueError(
                f"Research stage timeout after {research_timeout}s"
            ) from exc
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
        if requested_execution_profile == "dev_strict":
            strategy = str(research.enrichment_strategy or "").strip().lower()
            if bool(req.web_enrichment):
                if strategy in {"", "none"} or "fallback" in strategy:
                    failures.append(f"research_strategy_not_strict({strategy or 'none'})")
            elif "fallback" in strategy:
                failures.append(f"research_strategy_not_strict({strategy or 'none'})")
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
        outline_timeout = _pipeline_stage_timeout_sec("outline", 120)
        try:
            outline_plan = await asyncio.wait_for(
                self.generate_outline_plan(
                    OutlinePlanRequest(
                        research=research,
                        total_pages=req.total_pages,
                    )
                ),
                timeout=outline_timeout,
            )
        except asyncio.TimeoutError as exc:
            diag = [f"timeout>{outline_timeout}s", "stage=outline_plan"]
            _append_stage("outline_plan", outline_started, False, diag)
            raise ValueError(
                f"Outline stage timeout after {outline_timeout}s"
            ) from exc
        _append_stage("outline_plan", outline_started, True)
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-2-outline-plan", outline_plan.model_dump())

        # Stage 3: wireframe presentation plan
        presentation_started = _utc_now()
        presentation_timeout = _pipeline_stage_timeout_sec("presentation", 180)
        try:
            presentation_plan = await asyncio.wait_for(
                self.generate_presentation_plan(
                    PresentationPlanRequest(outline=outline_plan, research=research)
                ),
                timeout=presentation_timeout,
            )
        except asyncio.TimeoutError as exc:
            diag = [f"timeout>{presentation_timeout}s", "stage=presentation_plan"]
            _append_stage("presentation_plan", presentation_started, False, diag)
            raise ValueError(
                f"Presentation-plan stage timeout after {presentation_timeout}s"
            ) from exc
        _append_stage("presentation_plan", presentation_started, True)
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-3-presentation-plan", presentation_plan.model_dump())

        use_reference_reconstruct = bool(
            req.reconstruct_from_reference and isinstance(req.reference_desc, dict)
        )
        pipeline_image_asset_enrichment = bool(getattr(req, "image_asset_enrichment", True))

        def _apply_pipeline_template_hints(payload: Dict[str, Any]) -> Dict[str, Any]:
            out = dict(payload or {})
            if requested_template_family not in {"", "auto"}:
                out["template_family"] = requested_template_family
                out["template_id"] = requested_template_family
            if requested_skill_profile not in {"", "auto"}:
                out["skill_profile"] = requested_skill_profile
            if requested_theme_recipe not in {"", "auto"}:
                out["theme_recipe"] = requested_theme_recipe
            if requested_tone in {"light", "dark"}:
                out["tone"] = requested_tone
            if isinstance(out.get("theme"), dict):
                theme_obj = dict(out.get("theme") or {})
                if requested_theme_recipe not in {"", "auto"}:
                    theme_obj["theme_recipe"] = requested_theme_recipe
                if requested_tone in {"light", "dark"}:
                    theme_obj["tone"] = requested_tone
                out["theme"] = theme_obj
            if requested_template_file_url:
                out["template_file_url"] = requested_template_file_url
            return out

        if use_reference_reconstruct:
            base_render_payload = _build_render_payload_from_reference_desc(
                req.reference_desc or {},
                fallback_title=req.title or presentation_plan.title,
            )
            base_render_payload = _apply_pipeline_template_hints(base_render_payload)
            if str(req.quality_profile or "").strip() and str(req.quality_profile).strip().lower() != "auto":
                base_render_payload["quality_profile"] = str(req.quality_profile).strip()
            render_payload = base_render_payload
        else:
            base_render_payload = _presentation_plan_to_render_payload(presentation_plan)
            base_render_payload["topic"] = req.topic
            base_render_payload["audience"] = req.audience
            base_render_payload["purpose"] = req.purpose
            base_render_payload["style_preference"] = req.style_preference
            base_render_payload["deck_archetype_profile"] = requested_deck_archetype_profile
            base_render_payload = _apply_pipeline_template_hints(base_render_payload)
            base_render_payload = _apply_skill_planning_to_render_payload(
                base_render_payload,
                execution_profile=requested_execution_profile,
                force_ppt_master=requested_force_ppt_master,
            )
            if str(req.quality_profile or "").strip() and str(req.quality_profile).strip().lower() != "auto":
                base_render_payload["quality_profile"] = str(req.quality_profile).strip()
            render_payload = _apply_visual_orchestration(base_render_payload)
            render_payload = _apply_pipeline_template_hints(render_payload)
            if pipeline_image_asset_enrichment:
                render_payload = await _hydrate_image_assets(render_payload)
        if requested_execution_profile == "dev_strict" and bool(req.with_export):
            image_issues = _collect_image_asset_issues(render_payload)
            if image_issues:
                if requested_quality_profile in _STRICT_QUALITY_PROFILES or route_policy.mode == "refine":
                    raise ValueError(
                        "Image asset stage failed (dev_strict): "
                        + "; ".join(image_issues[:8])
                    )
                render_payload["image_asset_warnings"] = image_issues[:8]
        else:
            render_payload = _ensure_image_block_placeholders(render_payload)

        # Stage 4: strict quality gate before any render/export
        quality_started = _utc_now()
        quality_issues = []
        design_constraint_report = validate_render_payload_design(render_payload)
        render_payload["design_constraint_report"] = design_constraint_report
        preflight_issue_codes = [
            *[str(code or "").strip() for code in (design_constraint_report.get("deck_issues") or []) if str(code or "").strip()],
            *[
                f"{str(row.get('slide_id') or 'slide')}:{str(code or '').strip()}"
                for row in (design_constraint_report.get("slides") or [])
                if isinstance(row, dict)
                for code in (row.get("issues") or [])
                if str(code or "").strip()
            ],
        ]
        render_payload = _enforce_profile_field_ownership(
            render_payload,
            quality_profile=requested_quality_profile,
            deck_archetype_profile=requested_deck_archetype_profile,
        )
        if requested_execution_profile == "dev_strict" and bool(req.with_export) and preflight_issue_codes:
            _append_stage(
                "quality_gate",
                quality_started,
                False,
                ["design_preflight_failed", *preflight_issue_codes[:8]],
            )
            raise ValueError("Design preflight failed: " + "; ".join(preflight_issue_codes[:6]))
        quality_profile = requested_quality_profile
        pipeline_strict_quality_mode = _is_strict_quality_mode(
            constraint_hardness="minimal",
            hardness_profile=render_payload.get("hardness_profile"),
            route_mode=route_policy.mode,
            quality_profile=quality_profile,
        )
        pipeline_constraint_hardness = "strict" if pipeline_strict_quality_mode else "minimal"
        quality_score = None
        quality_score_failed = False
        quality_attempts = (
            1
            if requested_execution_profile == "dev_strict"
            else max(1, int(route_policy.max_retry_attempts))
        )
        for _attempt in range(1, quality_attempts + 1):
            content_gate = validate_deck(
                render_payload.get("slides") or [],
                profile=quality_profile,
            )
            layout_gate = validate_layout_diversity(
                render_payload,
                profile=quality_profile,
                enforce_terminal_slide_types=True,
            )
            content_issues = list(content_gate.issues)
            layout_issues = list(layout_gate.issues)
            relaxed_codes = _relaxed_quality_issue_codes(
                route_mode=route_policy.mode,
                quality_profile=quality_profile,
                use_reference_reconstruct=use_reference_reconstruct,
                requested_execution_profile=requested_execution_profile,
                include_template_switch_relaxation=True,
            )
            if relaxed_codes:
                content_issues = [
                    issue
                    for issue in content_issues
                    if str(getattr(issue, "code", "")).strip() not in relaxed_codes
                ]
                layout_issues = [
                    issue
                    for issue in layout_issues
                    if str(getattr(issue, "code", "")).strip() not in relaxed_codes
                ]
            quality_issues = [*content_issues, *layout_issues]
            if preflight_issue_codes:
                render_payload["design_constraint_report"] = design_constraint_report
            quality_score = score_deck_quality(
                slides=render_payload.get("slides") or [],
                render_spec=render_payload,
                profile=quality_profile,
                content_issues=content_issues,
                layout_issues=layout_issues,
            )
            score_passed = bool(quality_score.passed) if route_policy.require_weighted_quality_score else True
            quality_score_failed = not score_passed
            if (not quality_issues) and score_passed:
                break
            # Stage 2 repair: enforce visual contract and asset placeholders before retrying.
            if use_reference_reconstruct:
                break
            if requested_execution_profile == "dev_strict":
                break
            render_payload = _apply_pipeline_template_hints(render_payload)
            render_payload = _apply_skill_planning_to_render_payload(
                render_payload,
                execution_profile=requested_execution_profile,
                force_ppt_master=requested_force_ppt_master,
            )
            render_payload = _apply_visual_orchestration(render_payload)
            render_payload = _apply_pipeline_template_hints(render_payload)
            if pipeline_image_asset_enrichment:
                render_payload = await _hydrate_image_assets(render_payload)
            render_payload = _ensure_image_block_placeholders(render_payload)
            if _attempt >= quality_attempts:
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
        if preflight_issue_codes:
            quality_success_diag.append(f"design_preflight_issues={len(preflight_issue_codes)}")
        if quality_score is not None:
            quality_success_diag.append(f"score={quality_score.score:.1f}/{quality_score.threshold:.1f}")
        _append_stage("quality_gate", quality_started, True, quality_success_diag)
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-4-render-payload", render_payload)

        export_data: Optional[Dict[str, Any]] = None
        export_started = _utc_now()
        if req.with_export:
            export_channel = _resolve_export_channel(req.export_channel)
            layer1_runtime: Dict[str, Any] = {}
            pipeline_style_variant = str(req.minimax_style_variant or "auto")
            pipeline_palette_key = _canonicalize_pipeline_palette(
                _default_palette_for_archetype(
                    requested_deck_archetype_profile,
                    str(req.minimax_palette_key or "auto"),
                ),
                context_parts=[
                    req.title or presentation_plan.title,
                    req.topic,
                    req.audience,
                    req.purpose,
                ],
                fallback="auto",
            )
            if requested_deck_archetype_profile == "education_textbook":
                pipeline_palette_key = "education_office_classic"
            pipeline_theme_recipe = str(
                req.theme_recipe
                or render_payload.get("theme_recipe")
                or "auto"
            ).strip().lower() or "auto"
            pipeline_tone = str(
                req.tone
                or render_payload.get("tone")
                or render_payload.get("theme_tone")
                or "auto"
            ).strip().lower() or "auto"
            if pipeline_tone not in {"auto", "light", "dark"}:
                pipeline_tone = "auto"
            pipeline_template_family = (
                requested_template_family
                if requested_template_family not in {"", "auto"}
                else str(render_payload.get("template_family") or "auto")
            )
            pipeline_skill_profile = str(
                render_payload.get("skill_profile")
                or (requested_skill_profile if requested_skill_profile not in {"", "auto"} else "")
            )
            pipeline_design_decision = normalize_design_decision_v1(
                render_payload.get("design_decision_v1")
            )
            export_timeout = _pipeline_export_timeout_sec(
                slide_count=len(list(render_payload.get("slides") or [])),
                route_mode=route_policy.mode,
            )
            if use_reference_reconstruct:
                try:
                    export_data = await asyncio.wait_for(
                        asyncio.to_thread(
                            _export_reference_reconstruct_locally,
                            req.reference_desc or {},
                            timeout_sec=export_timeout,
                        ),
                        timeout=export_timeout + 30,
                    )
                except asyncio.TimeoutError as exc:
                    diag = [f"timeout>{export_timeout + 30}s", "stage=export", "mode=reference_reconstruct"]
                    _append_stage("export", export_started, False, diag)
                    raise ValueError(
                        f"Export stage timeout after {export_timeout + 30}s (reference reconstruct)"
                    ) from exc
            else:
                pipeline_template_file_url = str(
                    render_payload.get("template_file_url") or requested_template_file_url or ""
                ).strip()
                if pipeline_template_file_url:
                    from src.pptx_engine import fill_template_pptx

                    template_bytes = await _download_remote_file_bytes(
                        pipeline_template_file_url,
                        suffix=".pptx",
                    )
                    template_result = await asyncio.to_thread(
                        fill_template_pptx,
                        template_bytes=template_bytes,
                        slides=[dict(item) for item in (render_payload.get("slides") or []) if isinstance(item, dict)],
                        deck_title=req.title or presentation_plan.title,
                        author=req.author,
                    )
                    template_pptx_bytes = template_result.get("pptx_bytes")
                    if not isinstance(template_pptx_bytes, (bytes, bytearray)):
                        raise ValueError("template_edit_missing_pptx_bytes")
                    export_data = {
                        "skill": "pptx_template_editor",
                        "generator_mode": "template_edit",
                        "template_edit": {
                            "template_file_url": pipeline_template_file_url,
                            "replacement_count": int(template_result.get("replacement_count") or 0),
                            "slides_used": int(template_result.get("slides_used") or 0),
                            "template_slide_count": int(template_result.get("template_slide_count") or 0),
                            "engine": str(template_result.get("engine") or "unknown"),
                            "cleaned_resource_count": int(template_result.get("cleaned_resource_count") or 0),
                            "markitdown_used": bool(template_result.get("markitdown_used")),
                            "markitdown_ok": bool(template_result.get("markitdown_ok")),
                            "markitdown_issue": str(template_result.get("markitdown_issue") or ""),
                        },
                        "pptx_bytes": bytes(template_pptx_bytes),
                    }
                else:
                    pipeline_layer1_design = _run_layer1_design_skill_chain(
                        deck_title=req.title or presentation_plan.title,
                        slides=list(render_payload.get("slides") or []),
                        requested_style_variant=req.minimax_style_variant,
                        requested_palette_key=req.minimax_palette_key,
                        requested_theme_recipe=req.theme_recipe,
                        requested_tone=req.tone,
                        context_parts=[req.topic, req.audience, req.purpose, req.style_preference],
                        requested_template_family=(
                            requested_template_family
                            if requested_template_family not in {"", "auto"}
                            else str(render_payload.get("template_family") or "auto")
                        ),
                        requested_skill_profile=(
                            requested_skill_profile
                            if requested_skill_profile not in {"", "auto"}
                            else str(render_payload.get("skill_profile") or "auto")
                        ),
                        execution_profile=requested_execution_profile,
                        force_ppt_master=requested_force_ppt_master,
                    )
                    pipeline_style_variant = str(
                        render_payload.get("style_variant")
                        or pipeline_layer1_design.get("style_variant")
                        or req.minimax_style_variant
                    )
                    pipeline_palette_key = _canonicalize_pipeline_palette(
                        str(
                            render_payload.get("palette_key")
                            or pipeline_layer1_design.get("palette_key")
                            or _default_palette_for_archetype(
                                requested_deck_archetype_profile,
                                str(req.minimax_palette_key or "auto"),
                            )
                        ),
                        context_parts=[
                            req.title or presentation_plan.title,
                            req.topic,
                            req.audience,
                            req.purpose,
                            *[str((s or {}).get("title") or "") for s in (render_payload.get("slides") or [])[:4] if isinstance(s, dict)],
                        ],
                        fallback="auto",
                    )
                    if requested_deck_archetype_profile == "education_textbook":
                        pipeline_palette_key = "education_office_classic"
                    pipeline_template_family = str(
                        render_payload.get("template_family")
                        or pipeline_layer1_design.get("template_family")
                        or pipeline_template_family
                        or "auto"
                    )
                    pipeline_theme_recipe = str(
                        render_payload.get("theme_recipe")
                        or pipeline_layer1_design.get("theme_recipe")
                        or pipeline_theme_recipe
                        or "auto"
                    ).strip().lower() or "auto"
                    pipeline_tone = str(
                        render_payload.get("tone")
                        or pipeline_layer1_design.get("tone")
                        or pipeline_tone
                        or "auto"
                    ).strip().lower() or "auto"
                    if pipeline_tone not in {"auto", "light", "dark"}:
                        pipeline_tone = "auto"
                    pipeline_skill_profile = str(
                        render_payload.get("skill_profile")
                        or pipeline_layer1_design.get("skill_profile")
                        or pipeline_skill_profile
                        or ""
                    )
                    pipeline_design_decision = normalize_design_decision_v1(
                        render_payload.get("design_decision_v1")
                        or pipeline_layer1_design.get("design_decision_v1")
                    )
                    if not isinstance(pipeline_design_decision.get("deck"), dict) or not pipeline_design_decision.get("deck"):
                        pipeline_design_decision = build_design_decision_v1(
                            style_variant=pipeline_style_variant,
                            palette_key=pipeline_palette_key,
                            theme_recipe=pipeline_theme_recipe,
                            tone=pipeline_tone,
                            template_family=pipeline_template_family,
                            quality_profile=quality_profile,
                            route_mode=route_policy.mode,
                            skill_profile=pipeline_skill_profile,
                            slides=list(render_payload.get("slides") or []),
                            decision_source="pipeline_export",
                        )
                    try:
                        export_data = await asyncio.wait_for(
                            asyncio.to_thread(
                                export_minimax_pptx,
                                slides=render_payload["slides"],
                                title=req.title or presentation_plan.title,
                                author=req.author,
                                render_channel=export_channel,
                                route_mode=route_policy.mode,
                                style_variant=pipeline_style_variant,
                                palette_key=pipeline_palette_key,
                                theme_recipe=pipeline_theme_recipe,
                                tone=pipeline_tone,
                                deck_id=run_id,
                                generator_mode="official",
                                verbatim_content=bool(use_reference_reconstruct),
                                original_style=False,
                                disable_local_style_rewrite=False,
                                visual_priority=True,
                                visual_preset=str(req.visual_preset or "auto"),
                                visual_density="balanced",
                                deck_archetype_profile=requested_deck_archetype_profile,
                                constraint_hardness=pipeline_constraint_hardness,
                                svg_mode="on",
                                template_family=pipeline_template_family,
                                template_id=(
                                    str(render_payload.get("template_id") or "")
                                    or (
                                        pipeline_template_family
                                        if pipeline_template_family not in {"", "auto"}
                                        else ""
                                    )
                                ),
                                skill_profile=(
                                    pipeline_skill_profile
                                    or (
                                        requested_skill_profile
                                        if requested_skill_profile not in {"", "auto"}
                                        else ""
                                    )
                                ),
                                hardness_profile=str(render_payload.get("hardness_profile") or ""),
                                schema_profile=str(render_payload.get("schema_profile") or ""),
                                contract_profile=str(render_payload.get("contract_profile") or ""),
                                quality_profile=quality_profile,
                                enforce_visual_contract=True,
                                design_decision=pipeline_design_decision,
                                timeout=export_timeout,
                            ),
                            timeout=export_timeout + 30,
                        )
                    except asyncio.TimeoutError as exc:
                        diag = [f"timeout>{export_timeout + 30}s", "stage=export", "mode=minimax_export"]
                        _append_stage("export", export_started, False, diag)
                        raise ValueError(
                            f"Export stage timeout after {export_timeout + 30}s"
                        ) from exc
                    layer1_runtime = (
                        pipeline_layer1_design.get("runtime")
                        if isinstance(pipeline_layer1_design.get("runtime"), dict)
                        else {}
                    )
            if isinstance(export_data, dict):
                pptx_bytes = export_data.pop("pptx_bytes", None)
                if isinstance(pptx_bytes, (bytes, bytearray)):
                    if export_channel == "remote":
                        try:
                            pptx_url = await r2.upload_bytes_to_r2(
                                bytes(pptx_bytes),
                                key=f"projects/{run_id}/pptx/pipeline.pptx",
                                content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            )
                            export_data["pptx_url"] = pptx_url
                            export_data["url"] = pptx_url
                            export_data["inline_delivery"] = "r2_url"
                        except Exception as exc:
                            if requested_execution_profile == "dev_strict":
                                raise RuntimeError(
                                    "pipeline_export_remote_upload_failed:"
                                    + str(exc)[:220]
                                ) from exc
                            logger.warning("[ppt_service] pipeline export R2 upload failed: %s", exc)
                            export_data["pptx_base64"] = base64.b64encode(bytes(pptx_bytes)).decode("ascii")
                            export_data["inline_delivery"] = "base64"
                    else:
                        export_data["pptx_base64"] = base64.b64encode(bytes(pptx_bytes)).decode("ascii")
                        export_data["inline_delivery"] = "base64"
                export_data["style_variant"] = pipeline_style_variant
                export_data["palette_key"] = pipeline_palette_key
                export_data["theme_recipe"] = pipeline_theme_recipe
                export_data["tone"] = pipeline_tone
                export_data["template_family"] = pipeline_template_family
                export_data["skill_profile"] = pipeline_skill_profile
                export_data["slide_count"] = len(list(render_payload.get("slides") or []))
                export_data["design_decision_v1"] = pipeline_design_decision
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
        from src.ppt_export_pipeline import ExportPipelineTimeline
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
        from src.ppt_visual_critic import (
            apply_visual_critic_patch,
            build_visual_critic_patch,
        )
        from src.pptx_engine import fill_template_pptx
        from src.pptx_rasterizer import rasterize_pptx_bytes_to_png_bytes

        pipeline_timeline = ExportPipelineTimeline()

        with pipeline_timeline.stage(
            "prepare_input",
            {"slide_count": len(list(req.slides or [])), "route_mode": str(req.route_mode or "auto")},
        ):
            raw_slides_data = [s.model_dump() for s in req.slides]
            slides_data = [dict(item) for item in raw_slides_data]
        requested_execution_profile = _resolve_execution_profile_for_runtime(
            req.execution_profile
        )
        _enforce_dev_fast_fail_profile(
            requested_execution_profile,
            stage="export_pptx",
        )
        requested_force_ppt_master = req.force_ppt_master
        dev_fast_fail = requested_execution_profile == "dev_strict"
        enforce_skill_runtime = _require_direct_skill_runtime() or (
            requested_execution_profile == "dev_strict"
        )
        with pipeline_timeline.stage("build_decision", {}) as build_decision_meta:
            layer1_design = _run_layer1_design_skill_chain(
                deck_title=req.title,
                slides=slides_data,
                requested_style_variant=req.minimax_style_variant,
                requested_palette_key=req.minimax_palette_key,
                requested_theme_recipe=req.theme_recipe,
                requested_tone=req.tone,
                context_parts=[req.author, req.retry_hint],
                requested_template_family=req.template_family,
                requested_skill_profile=req.skill_profile,
                execution_profile=requested_execution_profile,
                force_ppt_master=requested_force_ppt_master,
            )
            requested_quality_profile = _resolve_quality_profile_id(
                req.quality_profile,
                topic=req.title,
                purpose=req.retry_hint,
                audience=req.author,
                total_pages=len(slides_data),
            )
            effective_theme_recipe = str(layer1_design.get("theme_recipe") or req.theme_recipe or "auto")
            requested_deck_archetype_profile = _derive_deck_archetype_profile(
                topic=req.title,
                audience=req.author,
                purpose=req.retry_hint,
                quality_profile=requested_quality_profile,
                theme_recipe=effective_theme_recipe,
            )
            effective_style_variant = str(layer1_design.get("style_variant") or req.minimax_style_variant)
            effective_palette_key = _canonicalize_pipeline_palette(
                str(layer1_design.get("palette_key") or _default_palette_for_archetype(requested_deck_archetype_profile, str(req.minimax_palette_key or "auto"))),
                context_parts=[
                    req.title,
                    req.author,
                    req.retry_hint,
                    *[str((slide or {}).get("title") or "") for slide in slides_data[:4] if isinstance(slide, dict)],
                ],
                fallback="auto",
            )
            if requested_deck_archetype_profile == "education_textbook":
                effective_palette_key = "education_office_classic"
            effective_template_family = str(layer1_design.get("template_family") or req.template_family)
            effective_skill_profile = str(layer1_design.get("skill_profile") or req.skill_profile)
            effective_tone = str(layer1_design.get("tone") or req.tone or "auto").strip().lower()
            if effective_tone not in {"auto", "light", "dark"}:
                effective_tone = "auto"
            visual_seed = await _hydrate_image_assets(
                _apply_visual_orchestration(
                    _apply_skill_planning_to_render_payload(
                        {
                            "title": req.title,
                            "theme": {
                                "palette": effective_palette_key,
                                "style": effective_style_variant,
                                "theme_recipe": effective_theme_recipe,
                                "tone": effective_tone,
                            },
                            "theme_recipe": effective_theme_recipe,
                            "tone": effective_tone,
                            "slides": slides_data,
                            "template_family": effective_template_family,
                            "template_id": effective_template_family if effective_template_family != "auto" else "",
                            "skill_profile": effective_skill_profile,
                            "hardness_profile": req.hardness_profile,
                            "schema_profile": req.schema_profile,
                            "contract_profile": req.contract_profile,
                            "quality_profile": requested_quality_profile,
                            "deck_archetype_profile": requested_deck_archetype_profile,
                            "svg_mode": req.svg_mode,
                            "execution_profile": requested_execution_profile,
                        },
                        execution_profile=requested_execution_profile,
                        force_ppt_master=requested_force_ppt_master,
                        )
                )
            )
            if dev_fast_fail and not str(req.template_file_url or "").strip():
                image_issues = _collect_image_asset_issues(visual_seed)
                if image_issues:
                    build_decision_meta["image_asset_issues"] = image_issues[:8]
            build_decision_meta["decision_source"] = "layer1+skill_planning"
            build_decision_meta["requested_quality_profile"] = requested_quality_profile
            build_decision_meta["style_variant"] = effective_style_variant
            build_decision_meta["palette_key"] = effective_palette_key
            build_decision_meta["theme_recipe"] = effective_theme_recipe
            build_decision_meta["tone"] = effective_tone
            build_decision_meta["template_family"] = effective_template_family
        orchestrated_slides = visual_seed.get("slides")
        if isinstance(orchestrated_slides, list):
            slides_data = orchestrated_slides
        effective_design_decision = normalize_design_decision_v1(
            visual_seed.get("design_decision_v1")
            or layer1_design.get("design_decision_v1")
        )
        if not isinstance(effective_design_decision.get("deck"), dict) or not effective_design_decision.get("deck"):
            effective_design_decision = build_design_decision_v1(
                style_variant=effective_style_variant,
                palette_key=effective_palette_key,
                theme_recipe=effective_theme_recipe,
                tone=effective_tone,
                template_family=effective_template_family,
                quality_profile=requested_quality_profile,
                route_mode=str(req.route_mode or "auto"),
                skill_profile=effective_skill_profile,
                slides=slides_data,
                decision_source="export_entry",
            )
        owner_conflicts = _collect_visual_owner_conflicts(slides_data, effective_design_decision)
        if owner_conflicts:
            if dev_fast_fail:
                raise RuntimeError(
                    "visual_decision_owner_conflict:" + ";".join(owner_conflicts[:8])
                )
            logger.warning(
                "[ppt_service] visual decision owner conflict auto-corrected count=%s sample=%s",
                len(owner_conflicts),
                owner_conflicts[:5],
            )
        slides_data = freeze_retry_visual_identity(slides_data, effective_design_decision)
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
        visual_critic_repair_enabled = _env_flag("PPT_VISUAL_CRITIC_REPAIR_ENABLED", "true")
        try:
            visual_critic_max_target_slides = max(
                1,
                min(12, int(str(os.getenv("PPT_VISUAL_CRITIC_MAX_TARGET_SLIDES", "6")).strip())),
            )
        except Exception:
            visual_critic_max_target_slides = 6
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
        max_retry_attempts = _resolve_retry_budget(
            env_max_attempts=max_retry_attempts,
            route_mode=route_policy.mode,
            route_policy_max=route_policy.max_retry_attempts,
        )
        partial_retry_enabled = partial_retry_enabled and route_policy.partial_retry_enabled
        env_generator_mode = str(os.getenv("PPT_GENERATOR_MODE", "official")).strip().lower()
        if env_generator_mode not in {"official", "legacy"}:
            env_generator_mode = "official"
        allow_legacy_mode = _env_flag("PPT_ALLOW_LEGACY_MODE", "false")
        enable_legacy_fallback = _env_flag("PPT_ENABLE_LEGACY_FALLBACK", "false") and allow_legacy_mode
        if dev_fast_fail:
            enable_legacy_fallback = False

        retry_scope = _normalize_retry_scope(req.retry_scope)
        target_slide_ids = list(req.target_slide_ids or [])
        target_block_ids = list(req.target_block_ids or [])
        retry_hint = req.retry_hint
        deck_id = req.deck_id or _new_id()
        export_channel = _resolve_export_channel(req.export_channel)
        quality_profile = requested_quality_profile
        requested_constraint_hardness = _normalize_constraint_hardness(req.constraint_hardness)
        strict_quality_mode = _is_strict_quality_mode(
            constraint_hardness=requested_constraint_hardness,
            hardness_profile=req.hardness_profile,
            route_mode=route_policy.mode,
            quality_profile=quality_profile,
        )
        if strict_quality_mode and requested_constraint_hardness != "strict":
            requested_constraint_hardness = "strict"
        visual_seed = _enforce_profile_field_ownership(
            visual_seed,
            quality_profile=quality_profile,
            hardness_profile=requested_constraint_hardness,
            deck_archetype_profile=requested_deck_archetype_profile,
        )
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
                if enforce_skill_runtime:
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
                if enforce_skill_runtime:
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
            url = await r2.upload_bytes_to_r2(
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
            export_data["design_decision_v1"] = effective_design_decision
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
            pipeline_timeline.record(
                stage="render",
                ok=True,
                meta={"mode": "template_edit", "attempts": 1},
            )
            pipeline_timeline.record(
                stage="evaluate",
                ok=True,
                meta={"quality_profile": quality_profile, "route_mode": route_policy.mode},
            )
            pipeline_timeline.record(
                stage="persist",
                ok=True,
                meta={"status": "success"},
            )
            export_data["pipeline_timeline"] = pipeline_timeline.to_dict()
            return export_data

        async def _reorchestrate_retry_slides(seed_slides: List[Dict[str, Any]]) -> None:
            nonlocal slides_data, effective_design_decision
            repaired = await _hydrate_image_assets(
                _apply_visual_orchestration(
                    _apply_skill_planning_to_render_payload(
                        {
                            "title": req.title,
                            "theme": {
                                "palette": effective_palette_key,
                                "style": effective_style_variant,
                                "theme_recipe": effective_theme_recipe,
                                "tone": effective_tone,
                            },
                            "theme_recipe": effective_theme_recipe,
                            "tone": effective_tone,
                            "slides": seed_slides,
                            "template_family": effective_template_family,
                            "template_id": effective_template_family if effective_template_family != "auto" else "",
                            "skill_profile": effective_skill_profile,
                            "hardness_profile": req.hardness_profile,
                            "schema_profile": req.schema_profile,
                            "contract_profile": req.contract_profile,
                            "quality_profile": quality_profile,
                            "svg_mode": req.svg_mode,
                        },
                        execution_profile=requested_execution_profile,
                        force_ppt_master=requested_force_ppt_master,
                    )
                )
            )
            repaired_slides = repaired.get("slides")
            if isinstance(repaired_slides, list) and repaired_slides:
                critic_repair_by_slide: Dict[str, Dict[str, Any]] = {}
                for idx, raw_slide in enumerate(seed_slides):
                    if not isinstance(raw_slide, dict):
                        continue
                    raw_visual = raw_slide.get("visual")
                    critic_repair = raw_visual.get("critic_repair") if isinstance(raw_visual, dict) else None
                    if not isinstance(critic_repair, dict) or not critic_repair:
                        continue
                    slide_id = str(raw_slide.get("slide_id") or raw_slide.get("id") or f"slide-{idx + 1}").strip()
                    if slide_id:
                        critic_repair_by_slide[slide_id] = dict(critic_repair)
                if critic_repair_by_slide:
                    for idx, repaired_slide in enumerate(repaired_slides):
                        if not isinstance(repaired_slide, dict):
                            continue
                        slide_id = str(repaired_slide.get("slide_id") or repaired_slide.get("id") or f"slide-{idx + 1}").strip()
                        critic_repair = critic_repair_by_slide.get(slide_id)
                        if not isinstance(critic_repair, dict):
                            continue
                        visual = repaired_slide.get("visual")
                        if not isinstance(visual, dict):
                            visual = {}
                            repaired_slide["visual"] = visual
                        visual["critic_repair"] = dict(critic_repair)
                next_decision = normalize_design_decision_v1(
                    repaired.get("design_decision_v1")
                    or effective_design_decision
                )
                if not isinstance(next_decision.get("deck"), dict) or not next_decision.get("deck"):
                    next_decision = build_design_decision_v1(
                        style_variant=effective_style_variant,
                        palette_key=effective_palette_key,
                        theme_recipe=effective_theme_recipe,
                        tone=effective_tone,
                        template_family=effective_template_family,
                        quality_profile=quality_profile,
                        route_mode=route_policy.mode,
                        skill_profile=effective_skill_profile,
                        slides=repaired_slides,
                        decision_source="retry_reorchestrate",
                    )
                effective_design_decision = next_decision
                slides_data = freeze_retry_visual_identity(repaired_slides, effective_design_decision)

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
                slides_data = freeze_retry_visual_identity(slides_data, effective_design_decision)
                effective_visual_preset = str(req.visual_preset or "auto").strip() or "auto"
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
                    theme_recipe=str(visual_seed.get("theme_recipe") or req.theme_recipe or "auto"),
                    tone=str(visual_seed.get("tone") or req.tone or "auto"),
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
                    deck_archetype_profile=requested_deck_archetype_profile,
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
                    design_decision=effective_design_decision,
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
                        theme_recipe=str(visual_seed.get("theme_recipe") or req.theme_recipe or "auto"),
                        tone=str(visual_seed.get("tone") or req.tone or "auto"),
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
                        deck_archetype_profile=requested_deck_archetype_profile,
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
                        design_decision=effective_design_decision,
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
                relaxed_codes = _relaxed_quality_issue_codes(
                    route_mode=route_policy.mode,
                    quality_profile=quality_profile,
                    use_reference_reconstruct=False,
                    requested_execution_profile=requested_execution_profile,
                    include_template_switch_relaxation=False,
                )
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
                        seed_slides = (current_result.get("input_payload") or {}).get("slides")
                        if not isinstance(seed_slides, list) or not seed_slides:
                            seed_slides = slides_data
                        visual_issue_codes_by_slide: Dict[str, List[str]] = {}
                        for issue in gate_issues:
                            issue_code = str(getattr(issue, "code", "") or "").strip()
                            if not issue_code:
                                continue
                            raw_targets = getattr(issue, "retry_target_ids", None)
                            target_ids = [
                                str(item).strip()
                                for item in (raw_targets if isinstance(raw_targets, list) else [getattr(issue, "slide_id", "")])
                                if str(item).strip() and str(item).strip().lower() != "deck"
                            ]
                            for slide_id in target_ids:
                                bucket = visual_issue_codes_by_slide.setdefault(slide_id, [])
                                if issue_code not in bucket:
                                    bucket.append(issue_code)
                        if visual_issue_codes_by_slide:
                            for idx, slide in enumerate(seed_slides):
                                if not isinstance(slide, dict):
                                    continue
                                slide_id = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}").strip()
                                issue_codes = visual_issue_codes_by_slide.get(slide_id)
                                if not issue_codes:
                                    continue
                                visual = slide.get("visual")
                                if not isinstance(visual, dict):
                                    visual = {}
                                    slide["visual"] = visual
                                if any(
                                    str(code).strip().lower() in {"low_contrast", "visual_low_contrast_ratio_high"}
                                    for code in issue_codes
                                ):
                                    visual["force_high_contrast"] = True
                                visual["critic_repair"] = {
                                    "enabled": True,
                                    "issue_codes": list(issue_codes),
                                }
                            slides_data = freeze_retry_visual_identity(
                                seed_slides,
                                effective_design_decision,
                            )
                        critic_patch: Dict[str, Any] = {}
                        critic_apply: Dict[str, Any] = {"applied": False}
                        if visual_critic_repair_enabled and isinstance(visual_audit, dict):
                            critic_patch = build_visual_critic_patch(
                                visual_audit=visual_audit,
                                gate_issues=gate_issues,
                                slides=seed_slides,
                                max_target_slides=visual_critic_max_target_slides,
                            )
                            critic_apply = apply_visual_critic_patch(
                                slides=seed_slides,
                                patch=critic_patch,
                            )
                            diagnostics.append(
                                {
                                    "attempt": attempt,
                                    "status": "visual_critic_patch",
                                    "patch": critic_patch,
                                    "apply_result": critic_apply,
                                }
                            )
                            if bool(critic_patch.get("enabled")):
                                target_rows = critic_patch.get("targets") if isinstance(critic_patch.get("targets"), list) else []
                                critic_targets_by_slide = {
                                    str(row.get("slide_id") or "").strip(): row
                                    for row in target_rows
                                    if isinstance(row, dict) and str(row.get("slide_id") or "").strip()
                                }
                                if critic_targets_by_slide:
                                    for idx, slide in enumerate(seed_slides):
                                        if not isinstance(slide, dict):
                                            continue
                                        slide_id = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}").strip()
                                        target_row = critic_targets_by_slide.get(slide_id)
                                        if not isinstance(target_row, dict):
                                            continue
                                        issue_codes = list(target_row.get("issue_codes") or [])
                                        actions = target_row.get("actions") if isinstance(target_row.get("actions"), dict) else {}
                                        visual = slide.get("visual")
                                        if not isinstance(visual, dict):
                                            visual = {}
                                            slide["visual"] = visual
                                        visual_patch = actions.get("visual_patch") if isinstance(actions.get("visual_patch"), dict) else {}
                                        for key, value in visual_patch.items():
                                            visual[key] = value
                                        visual["critic_repair"] = {
                                            "enabled": True,
                                            "issue_codes": list(issue_codes),
                                        }
                                        render_path = str(actions.get("render_path") or "").strip().lower()
                                        if render_path:
                                            slide["render_path"] = render_path
                                    slides_data = freeze_retry_visual_identity(
                                        seed_slides,
                                        effective_design_decision,
                                    )
                            if bool(critic_apply.get("applied")):
                                slides_data = freeze_retry_visual_identity(
                                    seed_slides,
                                    effective_design_decision,
                                )
                                if partial_retry_enabled:
                                    repair_targets = [
                                        str(item).strip()
                                        for item in (critic_apply.get("updated_slide_ids") or [])
                                        if str(item).strip()
                                    ]
                                    if repair_targets:
                                        retry_scope = "slide"
                                        target_slide_ids = repair_targets
                                        target_block_ids = []
                                retry_hint = (
                                    f"{str(retry_hint or '').strip()} | "
                                    f"visual_critic_patch:{len(critic_apply.get('updated_slide_ids') or [])}slides"
                                ).strip(" |")[:1500]
                                await _reorchestrate_retry_slides(seed_slides)
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

        url = ""
        export_data: Dict[str, Any] = {"url": url, "skill": skill}
        project_id = _new_id()
        if export_channel == "remote":
            key = f"projects/{project_id}/pptx/presentation.pptx"
            try:
                url = await r2.upload_bytes_to_r2(
                    export_result["pptx_bytes"],
                    key,
                    content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
                export_data["url"] = url
                export_data["inline_delivery"] = "r2_url"
            except Exception as exc:
                if dev_fast_fail:
                    raise RuntimeError(
                        "export_pptx_remote_upload_failed:" + str(exc)[:220]
                    ) from exc
                logger.warning("[ppt_service] export_pptx remote upload failed: %s", exc)
                export_data["pptx_base64"] = base64.b64encode(export_result["pptx_bytes"]).decode("ascii")
                export_data["inline_delivery"] = "base64"
        else:
            export_data["pptx_base64"] = base64.b64encode(export_result["pptx_bytes"]).decode("ascii")
            export_data["inline_delivery"] = "base64"
        generator_meta = export_result.get("generator_meta") or {}
        if generator_meta:
            export_data["generator_meta"] = generator_meta
        export_data["style_variant"] = effective_style_variant
        export_data["palette_key"] = effective_palette_key
        export_data["theme_recipe"] = effective_theme_recipe
        export_data["tone"] = effective_tone
        export_data["template_family"] = effective_template_family
        export_data["skill_profile"] = effective_skill_profile
        export_data["design_decision_v1"] = effective_design_decision
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
                image_url = await r2.upload_bytes_to_r2(
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
            export_data["weighted_quality_score"] = float(final_quality_score.score)
        if final_visual_audit:
            export_data["visual_qa"] = final_visual_audit
        if final_text_qa:
            export_data["text_qa"] = final_text_qa
        text_issue_codes = (
            [str(item).strip() for item in (final_text_qa.get("issue_codes") or []) if str(item).strip()]
            if isinstance(final_text_qa, dict)
            else []
        )
        issue_codes = sorted(
            {
                str(issue.code)
                for issue in [*final_content_issues, *final_layout_issues, *final_visual_gate_issues]
                if getattr(issue, "code", None)
            }
        )
        if final_quality_score is not None:
            visual_professional_score = score_visual_professional_metrics(
                slides=(export_result.get("input_payload") or {}).get("slides") or slides_data,
                quality_score=final_quality_score,
                issue_codes=issue_codes,
                text_issue_codes=text_issue_codes,
                visual_audit=final_visual_audit if isinstance(final_visual_audit, dict) else None,
                profile=quality_profile,
            )
            export_data["visual_professional_score"] = {
                "color_consistency_score": float(visual_professional_score.color_consistency_score),
                "layout_order_score": float(visual_professional_score.layout_order_score),
                "hierarchy_clarity_score": float(visual_professional_score.hierarchy_clarity_score),
                "visual_avg_score": float(visual_professional_score.visual_avg_score),
                "accuracy_gate_passed": bool(visual_professional_score.accuracy_gate_passed),
                "abnormal_tags": list(visual_professional_score.abnormal_tags),
                "diagnostics": dict(visual_professional_score.diagnostics),
                "scorer_version": "v1",
            }
        layout_homogeneous_count = len(
            [code for code in issue_codes if str(code).strip().lower() == "layout_homogeneous"]
        )
        slide_count_for_incidence = max(1, len(list(slides_data or [])))
        export_data["observability_report"] = {
            "route_mode": route_policy.mode,
            "quality_profile": quality_profile,
            "strict_quality_mode": bool(strict_quality_mode),
            "attempts": attempt,
            "retry_count": max(0, int(attempt) - 1),
            "render_success_rate": 1.0,
            "layout_homogeneous_incidence": float(layout_homogeneous_count) / float(slide_count_for_incidence),
            "generator_mode": export_result.get("generator_mode", generator_mode),
            "export_channel": export_result.get("render_channel", export_channel),
            "has_visual_qa": bool(final_visual_audit),
            "has_text_qa": bool(final_text_qa),
            "has_quality_score": bool(final_quality_score),
            "has_visual_professional_score": isinstance(export_data.get("visual_professional_score"), dict),
            "issue_codes": issue_codes,
        }
        if isinstance(export_data.get("quality_score"), dict):
            export_data["observability_report"]["weighted_quality_score"] = float(
                export_data.get("quality_score", {}).get("score") or 0.0
            )
            export_data["observability_report"]["weighted_quality_threshold"] = float(
                export_data.get("quality_score", {}).get("threshold") or 0.0
            )
        if template_renderer_summary:
            export_data["observability_report"]["template_renderer_summary"] = template_renderer_summary
        if isinstance(export_data.get("visual_professional_score"), dict):
            export_data["observability_report"]["visual_professional_score"] = export_data.get(
                "visual_professional_score"
            )
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
        pipeline_timeline.record(
            stage="render",
            ok=True,
            meta={"attempts": int(attempt), "route_mode": route_policy.mode},
        )
        pipeline_timeline.record(
            stage="evaluate",
            ok=True,
            meta={
                "quality_profile": quality_profile,
                "weighted_quality_score": float((export_data.get("quality_score") or {}).get("score") or 0.0)
                if isinstance(export_data.get("quality_score"), dict)
                else None,
            },
        )
        pipeline_timeline.record(
            stage="retry",
            ok=True,
            meta={"retry_count": max(0, int(attempt) - 1), "retry_scope": retry_scope},
        )
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
            pipeline_timeline.record(
                stage="persist",
                ok=False,
                meta={"status": "strict_quality_gate_failed"},
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
        pipeline_timeline.record(
            stage="persist",
            ok=True,
            meta={"status": "success"},
        )
        export_data["pipeline_timeline"] = pipeline_timeline.to_dict()

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
