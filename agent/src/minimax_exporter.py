"""Shared MiniMax PPTX export helper."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from src.ppt_design_decision import (
    apply_design_decision_to_slides,
    decision_deck_value,
    normalize_design_decision_v1,
)
from src.ppt_failure_classifier import FailureClassification, classify_failure
from src.ppt_template_catalog import (
    list_template_ids,
    resolve_template_for_slide,
    template_capabilities,
    template_profiles,
)
from src.ppt_master_design_spec import apply_render_paths, build_design_spec
from src.ppt_visual_identity import canonicalize_theme_recipe, resolve_style_variant, resolve_tone

logger = logging.getLogger("minimax_exporter")

_TEMPLATE_ID_SET = set(list_template_ids())
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SUPPORTING_PREFIX_RE = re.compile(r"^(?:补充要点|supporting point)\s*[:：-]\s*", re.IGNORECASE)


def _runtime_role() -> str:
    explicit = str(os.getenv("PPT_EXECUTION_ROLE", "auto")).strip().lower()
    if explicit in {"worker", "web"}:
        return explicit
    if str(os.getenv("VERCEL", "")).strip() or str(os.getenv("VERCEL_ENV", "")).strip():
        return "web"
    return "worker"


def _parse_bool(raw: str, default: bool) -> bool:
    text = str(raw or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _module_retry_enabled() -> bool:
    # Strict alignment with PPT architecture doc:
    # module retry/orchestration is part of the primary path across roles.
    default_enabled = True
    return _parse_bool(os.getenv("PPT_MODULE_RETRY_ENABLED", ""), default_enabled)


def _module_mainflow_enabled() -> bool:
    # Strict alignment with architecture doc:
    # mainflow should be enabled by default regardless of runtime role.
    default_enabled = True
    return _parse_bool(os.getenv("PPT_MODULE_MAINFLOW_ENABLED", ""), default_enabled)


def _module_mainflow_render_each_enabled() -> bool:
    # Strict alignment with architecture doc:
    # mainflow should run per-slide orchestration + typed subagent by default.
    return _parse_bool(os.getenv("PPT_MODULE_MAINFLOW_RENDER_EACH_ENABLED", ""), True)


def _module_retry_max_parallel() -> int:
    raw = str(os.getenv("PPT_MODULE_RETRY_MAX_PARALLEL", "5")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 5
    return max(1, min(10, value))


def _module_subagent_exec_enabled() -> bool:
    # Keep an explicit escape hatch, but default to enabled for all roles.
    return _parse_bool(os.getenv("PPT_MODULE_SUBAGENT_EXEC_ENABLED", ""), True)


def _resolve_scripts_root() -> Path:
    explicit = str(os.getenv("PPT_SCRIPTS_ROOT", "")).strip()
    candidates: List[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    here = Path(__file__).resolve()
    candidates.extend(
        [
            here.parents[2] / "scripts",
            here.parents[1] / "scripts",
            Path.cwd() / "scripts",
            Path.cwd().parent / "scripts",
        ]
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return here.parents[2] / "scripts"


def _build_generator_cmd(
    *,
    script_path: Path,
    input_path: Path,
    output_path: Path,
    render_spec_path: Path,
    payload: Dict[str, Any],
    retry_scope: str,
    target_slide_ids: List[str] | None,
    target_block_ids: List[str] | None,
    retry_hint: str,
    idempotency_key: str,
    verbatim_content: bool,
    original_style: bool,
    disable_local_style_rewrite: bool,
    visual_priority: bool,
    visual_preset: str,
    visual_density: str,
    constraint_hardness: str,
    deck_id: str,
) -> List[str]:
    cmd = [
        "node",
        str(script_path),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--render-output",
        str(render_spec_path),
        "--retry-scope",
        str(retry_scope or "deck"),
        "--generator-mode",
        str(payload.get("generator_mode") or "official"),
    ]
    if deck_id:
        cmd.extend(["--deck-id", deck_id])
    if target_slide_ids:
        cmd.extend(["--target-slide-ids", ",".join(target_slide_ids)])
    if target_block_ids:
        cmd.extend(["--target-block-ids", ",".join(target_block_ids)])
    if retry_hint:
        cmd.extend(["--retry-hint", retry_hint[:1500]])
    if idempotency_key:
        cmd.extend(["--idempotency-key", idempotency_key])
    if verbatim_content:
        cmd.append("--verbatim-content")
    if original_style:
        cmd.append("--original-style")
    if disable_local_style_rewrite:
        cmd.append("--disable-local-style-rewrite")
    if visual_priority:
        cmd.append("--visual-priority")
    if str(visual_preset or "").strip():
        cmd.extend(["--visual-preset", str(visual_preset).strip()])
    if str(visual_density or "").strip():
        cmd.extend(["--visual-density", str(visual_density).strip()])
    if str(constraint_hardness or "").strip():
        cmd.extend(["--constraint-hardness", str(constraint_hardness).strip()])
    if str(payload.get("theme_recipe") or "").strip():
        cmd.extend(["--theme-recipe", str(payload.get("theme_recipe")).strip()])
    if str(payload.get("tone") or "").strip():
        cmd.extend(["--tone", str(payload.get("tone")).strip()])
    return cmd


def _build_module_retry_cmd(
    *,
    orchestrator_script_path: Path,
    generator_script_path: Path,
    input_path: Path,
    output_path: Path,
    render_spec_path: Path,
    modules_dir: Path,
    manifest_path: Path,
    target_slide_ids: List[str],
    render_each: bool,
) -> List[str]:
    cmd = [
        "node",
        str(orchestrator_script_path),
        "--input",
        str(input_path),
        "--modules-dir",
        str(modules_dir),
        "--manifest",
        str(manifest_path),
        "--compile",
        "--output",
        str(output_path),
        "--render-output",
        str(render_spec_path),
        "--generator-script",
        str(generator_script_path),
    ]
    if render_each:
        cmd.extend(
            [
                "--render-each",
                "--max-parallel",
                str(_module_retry_max_parallel()),
            ]
        )
    if target_slide_ids:
        cmd.extend(["--target-slide-ids", ",".join(target_slide_ids)])
    if render_each and _module_subagent_exec_enabled():
        cmd.append("--subagent-exec")
    return cmd


def _normalize_text_key(text: str) -> str:
    lowered = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%+.-]", "", lowered)


def _sanitize_block_text(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = _SUPPORTING_PREFIX_RE.sub("", value).strip()
    return re.sub(r"\s+", " ", value)


def _extract_block_text(block: Dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return _sanitize_block_text(content)
    if isinstance(content, dict):
        parts: List[str] = []
        for key in ("title", "body", "text", "label", "caption", "description"):
            value = _sanitize_block_text(str(content.get(key) or ""))
            if value:
                parts.append(value)
        if parts:
            return _sanitize_block_text(" ".join(parts))
    data = block.get("data")
    if isinstance(data, dict):
        parts = []
        for key in ("title", "label", "description", "text"):
            value = _sanitize_block_text(str(data.get(key) or ""))
            if value:
                parts.append(value)
        if parts:
            return _sanitize_block_text(" ".join(parts))
    return ""


def _set_block_text(block: Dict[str, Any], text: str) -> None:
    content = block.get("content")
    if isinstance(content, str):
        block["content"] = text
        return
    if isinstance(content, dict):
        updated = dict(content)
        for key in ("title", "text", "label", "caption", "description", "body"):
            if str(updated.get(key) or "").strip():
                updated[key] = text
                block["content"] = updated
                return
        updated["title"] = text
        block["content"] = updated
        return
    data = block.get("data")
    if isinstance(data, dict):
        updated = dict(data)
        for key in ("label", "description", "title", "text"):
            if str(updated.get(key) or "").strip():
                updated[key] = text
                block["data"] = updated
                return
        updated["label"] = text
        block["data"] = updated
        return
    block["content"] = text


def _disambiguated_text(
    text: str,
    *,
    block_type: str,
    duplicate_index: int,
    prefer_zh: bool,
) -> str:
    base = _sanitize_block_text(text)
    if not base:
        base = "细节" if prefer_zh else "Detail"
    visual_suffix = {
        "image": "图示",
        "chart": "图表",
        "kpi": "指标",
        "table": "表格",
        "workflow": "流程",
        "diagram": "示意",
    }.get(block_type, "补充")
    en_suffix = {
        "image": "visual",
        "chart": "chart",
        "kpi": "metric",
        "table": "table",
        "workflow": "workflow",
        "diagram": "diagram",
    }.get(block_type, "detail")
    suffix = visual_suffix if prefer_zh else en_suffix
    ordinal = "" if duplicate_index <= 1 else str(duplicate_index)
    if prefer_zh:
        return f"{base}（{suffix}{ordinal}）"
    return f"{base} ({suffix}{ordinal})"


def _ensure_unique_non_title_block_text(
    blocks: List[Dict[str, Any]],
    *,
    slide_title: str,
) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    duplicate_counts: Dict[str, int] = {}
    prefer_zh = bool(_CJK_RE.search(str(slide_title or "")))

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("block_type") or block.get("type") or "").strip().lower()
        if block_type == "title":
            continue
        raw_text = _extract_block_text(block)
        if raw_text:
            _set_block_text(block, raw_text)
        text_key = _normalize_text_key(raw_text)
        if not text_key:
            continue
        if _CJK_RE.search(raw_text):
            prefer_zh = True
        if text_key not in seen:
            seen.add(text_key)
            continue

        base_text = _sanitize_block_text(raw_text) or ("细节" if prefer_zh else "Detail")
        idx = duplicate_counts.get(block_type, 1)
        while True:
            candidate = _disambiguated_text(
                base_text,
                block_type=block_type,
                duplicate_index=idx,
                prefer_zh=prefer_zh,
            )
            candidate_key = _normalize_text_key(candidate)
            if candidate_key and candidate_key not in seen:
                _set_block_text(block, candidate)
                seen.add(candidate_key)
                duplicate_counts[block_type] = idx + 1
                break
            idx += 1

    return blocks


def _allow_legacy_mode() -> bool:
    return str(os.getenv("PPT_ALLOW_LEGACY_MODE", "false")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _extract_json_from_stdout(stdout: str) -> Dict[str, Any]:
    for line in reversed((stdout or "").splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


class MiniMaxExportError(RuntimeError):
    """Structured export error with retry classification metadata."""

    def __init__(
        self,
        *,
        message: str,
        classification: FailureClassification,
        detail: str = "",
    ) -> None:
        super().__init__(message)
        self.classification = classification
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": str(self),
            "failure_code": self.classification.code,
            "retryable": self.classification.retryable,
            "max_attempts": self.classification.max_attempts,
            "base_delay_ms": self.classification.base_delay_ms,
            "failure_detail": self.detail[:1200],
        }


def _stable_slide_id(slide: Dict[str, Any], index: int) -> str:
    for key in ("slide_id", "id", "page_number"):
        value = slide.get(key)
        if value is None:
            continue
        candidate = str(value).strip()
        if candidate:
            return candidate
    return f"slide-{index + 1}"


def _normalize_slides(slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for idx, raw in enumerate(slides):
        slide = dict(raw or {})
        slide["slide_id"] = _stable_slide_id(slide, idx)
        elements = slide.get("elements")
        if isinstance(elements, list):
            fixed_elements = []
            for block_idx, item in enumerate(elements):
                if not isinstance(item, dict):
                    fixed_elements.append(item)
                    continue
                el = dict(item)
                if not str(el.get("block_id") or "").strip():
                    fallback = str(el.get("id") or "").strip() or f"{slide['slide_id']}-block-{block_idx + 1}"
                    el["block_id"] = fallback
                fixed_elements.append(el)
            slide["elements"] = fixed_elements
        normalized.append(slide)
    return normalized


def _normalize_generator_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "legacy" and _allow_legacy_mode():
        return "legacy"
    return "official"


def _normalize_render_channel(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"local", "remote"}:
        return normalized
    return "local"


def _infer_slide_type(slide: Dict[str, Any], index: int, total: int) -> str:
    explicit = str(slide.get("slide_type") or slide.get("type") or "").strip().lower()
    if explicit:
        return explicit
    if index == 0:
        return "cover"
    if index == max(0, total - 1):
        return "summary"
    return "content"


def _canonical_slide_type_for_template(slide_type: str) -> str:
    normalized = str(slide_type or "").strip().lower()
    if normalized in {"hero_1", "cover"}:
        return "cover"
    if normalized in {"table_of_contents", "contents", "toc"}:
        return "cover"
    if normalized in {"section", "section_divider", "divider"}:
        return "cover"
    if normalized in {"summary", "closing", "conclusion"}:
        return "summary"
    if normalized in {"timeline", "workflow"}:
        return "workflow"
    if normalized in {"comparison", "data"}:
        return normalized
    return "content"


def _template_family_supports_slide(template_family: str, *, slide_type: str, layout_grid: str) -> bool:
    family = str(template_family or "").strip().lower()
    if not family:
        return False
    try:
        cap = template_capabilities(family)
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
    if not type_ok and normalized_type in {"toc", "divider", "summary"} and "cover" in supported_types:
        type_ok = True
    layout_ok = normalized_layout in supported_layouts if supported_layouts else True
    return bool(type_ok and layout_ok)


def _infer_template_family(
    slide: Dict[str, Any],
    *,
    slide_type: str,
    layout_grid: str,
    preferred_template_family: str = "",
) -> str:
    explicit = str(slide.get("template_family") or slide.get("template_id") or "").strip().lower()
    if explicit in _TEMPLATE_ID_SET and _template_family_supports_slide(
        explicit,
        slide_type=slide_type,
        layout_grid=layout_grid,
    ):
        return explicit
    preferred = str(preferred_template_family or "").strip().lower()
    if preferred in _TEMPLATE_ID_SET and _template_family_supports_slide(
        preferred,
        slide_type=slide_type,
        layout_grid=layout_grid,
    ):
        return preferred
    return resolve_template_for_slide(
        slide=slide,
        slide_type=slide_type,
        layout_grid=layout_grid,
        requested_template="",
        desired_density=str(slide.get("content_density") or "balanced"),
    )


def _template_profiles(template_family: str) -> Dict[str, str]:
    return template_profiles(template_family)


def _normalize_contract_slides(
    slides: List[Dict[str, Any]],
    *,
    preferred_template_family: str = "",
) -> List[Dict[str, Any]]:
    normalized = _normalize_slides(slides)
    total = len(normalized)
    out: List[Dict[str, Any]] = []
    for idx, raw in enumerate(normalized):
        slide = dict(raw)
        slide_type = _infer_slide_type(slide, idx, total)
        layout_grid = (
            str(slide.get("layout_grid") or slide.get("layout") or "").strip()
            or ("hero_1" if slide_type in {"cover", "summary"} else "split_2")
        )
        page_number = slide.get("page_number")
        if page_number is None:
            page_number = idx + 1
        raw_blocks = slide.get("blocks")
        blocks: List[Dict[str, Any]] = []
        if isinstance(raw_blocks, list):
            for item in raw_blocks:
                if isinstance(item, dict):
                    blocks.append(dict(item))
        blocks = _ensure_unique_non_title_block_text(
            blocks,
            slide_title=str(slide.get("title") or f"Slide {idx + 1}"),
        )

        slide["page_number"] = int(page_number)
        slide["slide_type"] = slide_type
        slide["layout_grid"] = layout_grid
        template_family = _infer_template_family(
            slide,
            slide_type=slide_type,
            layout_grid=layout_grid,
            preferred_template_family=preferred_template_family,
        )
        profiles = _template_profiles(template_family)
        slide["template_family"] = profiles["template_id"]
        slide["template_id"] = str(slide.get("template_id") or profiles["template_id"])
        slide["skill_profile"] = str(slide.get("skill_profile") or profiles["skill_profile"])
        slide["hardness_profile"] = str(slide.get("hardness_profile") or profiles["hardness_profile"])
        slide["schema_profile"] = str(slide.get("schema_profile") or profiles["schema_profile"])
        slide["contract_profile"] = str(slide.get("contract_profile") or profiles["contract_profile"])
        slide["quality_profile"] = str(slide.get("quality_profile") or profiles["quality_profile"])
        slide["blocks"] = blocks
        slide["bg_style"] = str(slide.get("bg_style") or "light")
        keywords = slide.get("image_keywords")
        if not isinstance(keywords, list):
            keywords = []
        slide["image_keywords"] = [str(item).strip() for item in keywords if str(item).strip()]
        out.append(slide)
    return out


def build_payload(
    *,
    slides: List[Dict[str, Any]],
    title: str,
    author: str,
    style_variant: str = "auto",
    palette_key: str = "auto",
    theme_recipe: str = "auto",
    tone: str = "auto",
    verbatim_content: bool = False,
    deck_id: str = "",
    retry_scope: str = "deck",
    target_slide_ids: List[str] | None = None,
    target_block_ids: List[str] | None = None,
    retry_hint: str = "",
    idempotency_key: str = "",
    route_mode: str = "standard",
    render_channel: str = "local",
    generator_mode: str = "official",
    enable_legacy_fallback: bool = False,
    original_style: bool = False,
    disable_local_style_rewrite: bool = False,
    visual_priority: bool = True,
    visual_preset: str = "auto",
    visual_density: str = "balanced",
    constraint_hardness: str = "minimal",
    svg_mode: str = "on",
    template_family: str = "auto",
    template_id: str = "",
    skill_profile: str = "",
    hardness_profile: str = "",
    schema_profile: str = "",
    contract_profile: str = "",
    quality_profile: str = "",
    enforce_visual_contract: bool = True,
    design_spec: Dict[str, Any] | None = None,
    design_decision: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    mode = _normalize_generator_mode(generator_mode)
    channel = _normalize_render_channel(render_channel)
    preserve_original = bool(original_style)
    disable_rewrite = bool(disable_local_style_rewrite) or preserve_original
    normalized_decision = normalize_design_decision_v1(design_decision)
    resolved_style_variant = str(style_variant or "auto").strip() or "auto"
    resolved_palette_key = str(palette_key or "auto").strip() or "auto"
    resolved_theme_recipe = canonicalize_theme_recipe(theme_recipe or "auto", fallback="auto")
    resolved_tone = resolve_tone(tone or "auto", theme_recipe=resolved_theme_recipe, fallback="auto")
    resolved_template_family = str(template_family or "auto").strip() or "auto"
    resolved_skill_profile = str(skill_profile or "").strip()

    decision_style = decision_deck_value(normalized_decision, "style_variant")
    decision_palette = decision_deck_value(normalized_decision, "palette_key")
    decision_theme_recipe = decision_deck_value(normalized_decision, "theme_recipe")
    decision_tone = decision_deck_value(normalized_decision, "tone")
    decision_template = decision_deck_value(normalized_decision, "template_family")
    decision_skill_profile = decision_deck_value(normalized_decision, "skill_profile")
    decision_quality_profile = decision_deck_value(normalized_decision, "quality_profile")
    decision_route_mode = decision_deck_value(normalized_decision, "route_mode")

    if resolved_style_variant.lower() in {"", "auto"} and decision_style:
        resolved_style_variant = decision_style
    if resolved_palette_key.lower() in {"", "auto"} and decision_palette:
        resolved_palette_key = decision_palette
    if resolved_theme_recipe.lower() in {"", "auto"} and decision_theme_recipe:
        resolved_theme_recipe = canonicalize_theme_recipe(decision_theme_recipe, fallback="consulting_clean")
    if resolved_tone in {"", "auto"} and decision_tone:
        resolved_tone = resolve_tone(decision_tone, theme_recipe=resolved_theme_recipe, fallback=resolved_tone)
    if resolved_template_family.lower() in {"", "auto"} and decision_template:
        resolved_template_family = decision_template
    if not resolved_skill_profile and decision_skill_profile:
        resolved_skill_profile = decision_skill_profile
    if not str(quality_profile or "").strip() and decision_quality_profile:
        quality_profile = decision_quality_profile
    if str(route_mode or "").strip().lower() in {"", "auto"} and decision_route_mode:
        route_mode = decision_route_mode

    if resolved_theme_recipe in {"", "auto"}:
        resolved_theme_recipe = canonicalize_theme_recipe(resolved_theme_recipe, fallback="consulting_clean")

    resolved_style_variant = resolve_style_variant(
        resolved_style_variant,
        theme_recipe=resolved_theme_recipe,
        fallback="soft",
    )
    resolved_tone = resolve_tone(
        resolved_tone,
        theme_recipe=resolved_theme_recipe,
        fallback="auto",
    )

    normalized_contract_slides = _normalize_contract_slides(
        slides,
        preferred_template_family=resolved_template_family,
    )
    decision_filled_slides = apply_design_decision_to_slides(
        normalized_contract_slides,
        normalized_decision,
    )
    normalized_slides = apply_render_paths(
        decision_filled_slides,
        svg_mode=str(svg_mode or "on"),
    )
    primary_template = (
        str(normalized_slides[0].get("template_family") or "dashboard_dark")
        if normalized_slides
        else "dashboard_dark"
    )
    deck_profiles = _template_profiles(primary_template)
    theme = {
        "palette": str(resolved_palette_key or "auto").strip() or "auto",
        "style": str(resolved_style_variant or "auto").strip() or "auto",
        "theme_recipe": str(resolved_theme_recipe or "auto").strip() or "auto",
        "tone": str(resolved_tone or "auto").strip() or "auto",
    }
    resolved_template_id = str(template_id or deck_profiles["template_id"]).strip() or deck_profiles["template_id"]
    resolved_design_spec = (
        dict(design_spec)
        if isinstance(design_spec, dict)
        else build_design_spec(
            theme=theme,
            template_family=str(resolved_template_family or resolved_template_id or "auto"),
            style_variant=str(theme.get("style") or "soft"),
            theme_recipe=str(resolved_theme_recipe or "auto"),
            tone=str(resolved_tone or "auto"),
            visual_preset=str(visual_preset or "auto"),
            visual_density=str(visual_density or "balanced"),
            visual_priority=bool(visual_priority),
            topic=str(title or ""),
        )
    )
    return {
        "slides": normalized_slides,
        "title": title,
        "author": author,
        "theme": theme,
        "theme_recipe": str(resolved_theme_recipe or "auto"),
        "tone": str(resolved_tone or "auto"),
        "render_channel": channel,
        "generator_mode": mode,
        "enable_legacy_fallback": bool(enable_legacy_fallback),
        "minimax_style_variant": theme["style"],
        "minimax_palette_key": theme["palette"],
        "verbatim_content": bool(verbatim_content),
        "deck_id": deck_id,
        "retry_scope": retry_scope,
        "target_slide_ids": [s for s in (target_slide_ids or []) if str(s).strip()],
        "target_block_ids": [s for s in (target_block_ids or []) if str(s).strip()],
        "retry_hint": retry_hint,
        "idempotency_key": idempotency_key,
        "route_mode": str(route_mode or "standard").strip().lower() or "standard",
        "original_style": preserve_original,
        "disable_local_style_rewrite": disable_rewrite,
        "visual_priority": bool(visual_priority),
        "visual_preset": str(visual_preset or "auto"),
        "visual_density": str(visual_density or "balanced"),
        "constraint_hardness": str(constraint_hardness or "minimal"),
        "svg_mode": str(svg_mode or "on"),
        "template_family": str(resolved_template_family or resolved_template_id or "auto"),
        "template_id": resolved_template_id,
        "skill_profile": str(resolved_skill_profile or deck_profiles["skill_profile"]),
        "hardness_profile": str(hardness_profile or deck_profiles["hardness_profile"]),
        "schema_profile": str(schema_profile or deck_profiles["schema_profile"]),
        "contract_profile": str(contract_profile or deck_profiles["contract_profile"]),
        "quality_profile": str(quality_profile or deck_profiles["quality_profile"]),
        "enforce_visual_contract": bool(enforce_visual_contract),
        "design_spec": resolved_design_spec,
        "design_decision_v1": normalized_decision,
    }


def export_minimax_pptx(
    *,
    slides: List[Dict[str, Any]],
    title: str,
    author: str,
    style_variant: str = "auto",
    palette_key: str = "auto",
    theme_recipe: str = "auto",
    tone: str = "auto",
    verbatim_content: bool = False,
    deck_id: str = "",
    retry_scope: str = "deck",
    target_slide_ids: List[str] | None = None,
    target_block_ids: List[str] | None = None,
    retry_hint: str = "",
    idempotency_key: str = "",
    route_mode: str = "standard",
    render_channel: str = "local",
    generator_mode: str = "official",
    enable_legacy_fallback: bool = False,
    original_style: bool = False,
    disable_local_style_rewrite: bool = False,
    visual_priority: bool = True,
    visual_preset: str = "auto",
    visual_density: str = "balanced",
    constraint_hardness: str = "minimal",
    svg_mode: str = "on",
    template_family: str = "auto",
    template_id: str = "",
    skill_profile: str = "",
    hardness_profile: str = "",
    schema_profile: str = "",
    contract_profile: str = "",
    quality_profile: str = "",
    enforce_visual_contract: bool = True,
    design_spec: Dict[str, Any] | None = None,
    design_decision: Dict[str, Any] | None = None,
    timeout: int = 180,
) -> Dict[str, Any]:
    scripts_root = _resolve_scripts_root()
    generator_script_path = scripts_root / "generate-pptx-minimax.mjs"
    orchestrator_script_path = scripts_root / "orchestrate-pptx-modules.mjs"
    if not generator_script_path.exists():
        raise FileNotFoundError(f"MiniMax PPTX script not found: {generator_script_path}")

    payload = build_payload(
        slides=slides,
        title=title,
        author=author,
        style_variant=style_variant,
        palette_key=palette_key,
        theme_recipe=theme_recipe,
        tone=tone,
        verbatim_content=verbatim_content,
        deck_id=deck_id,
        retry_scope=retry_scope,
        target_slide_ids=target_slide_ids,
        target_block_ids=target_block_ids,
        retry_hint=retry_hint,
        idempotency_key=idempotency_key,
        route_mode=route_mode,
        render_channel=render_channel,
        generator_mode=generator_mode,
        enable_legacy_fallback=enable_legacy_fallback,
        original_style=original_style,
        disable_local_style_rewrite=disable_local_style_rewrite,
        visual_priority=visual_priority,
        visual_preset=visual_preset,
        visual_density=visual_density,
        constraint_hardness=constraint_hardness,
        svg_mode=svg_mode,
        template_family=template_family,
        template_id=template_id,
        skill_profile=skill_profile,
        hardness_profile=hardness_profile,
        schema_profile=schema_profile,
        contract_profile=contract_profile,
        quality_profile=quality_profile,
        enforce_visual_contract=enforce_visual_contract,
        design_spec=design_spec,
        design_decision=design_decision,
    )

    requested_channel = _normalize_render_channel(payload.get("render_channel"))
    effective_channel = "local"
    channel_fallback_reason = ""
    if requested_channel == "remote":
        channel_fallback_reason = (
            "remote_channel_not_configured: current deployment uses local pptx-plugin rendering"
        )
        logger.warning("[minimax_exporter] %s", channel_fallback_reason)

    input_path: Path | None = None
    output_path: Path | None = None
    render_spec_path: Path | None = None
    modules_dir: Path | None = None
    manifest_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as f:
            json.dump(payload, f, ensure_ascii=False)
            input_path = Path(f.name)

        output_path = input_path.with_suffix(".pptx")
        render_spec_path = input_path.with_suffix(".render.json")
        normalized_retry_scope = str(retry_scope or "").strip().lower()
        normalized_target_slide_ids = [str(item).strip() for item in (target_slide_ids or []) if str(item).strip()]
        should_use_module_retry = (
            normalized_retry_scope == "slide"
            and bool(normalized_target_slide_ids)
            and _module_retry_enabled()
            and orchestrator_script_path.exists()
        )
        should_use_module_mainflow = (
            normalized_retry_scope != "slide"
            and _module_mainflow_enabled()
            and _module_retry_enabled()
            and orchestrator_script_path.exists()
        )
        should_use_module_orchestrator = should_use_module_retry or should_use_module_mainflow

        render_each = False
        if should_use_module_orchestrator:
            modules_dir = input_path.with_name(f"{input_path.stem}_modules")
            manifest_path = modules_dir / "manifest.json"
            render_each = bool(should_use_module_retry) or _module_mainflow_render_each_enabled()
            cmd = _build_module_retry_cmd(
                orchestrator_script_path=orchestrator_script_path,
                generator_script_path=generator_script_path,
                input_path=input_path,
                output_path=output_path,
                render_spec_path=render_spec_path,
                modules_dir=modules_dir,
                manifest_path=manifest_path,
                target_slide_ids=normalized_target_slide_ids if should_use_module_retry else [],
                render_each=render_each,
            )
        else:
            cmd = _build_generator_cmd(
                script_path=generator_script_path,
                input_path=input_path,
                output_path=output_path,
                render_spec_path=render_spec_path,
                payload=payload,
                retry_scope=retry_scope,
                target_slide_ids=target_slide_ids,
                target_block_ids=target_block_ids,
                retry_hint=retry_hint,
                idempotency_key=idempotency_key,
                verbatim_content=verbatim_content,
                original_style=original_style,
                disable_local_style_rewrite=disable_local_style_rewrite,
                visual_priority=visual_priority,
                visual_preset=visual_preset,
                visual_density=visual_density,
                constraint_hardness=constraint_hardness,
                deck_id=deck_id,
            )

        def _run(export_cmd: List[str], *, cmd_timeout: int) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                export_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=max(30, int(cmd_timeout)),
            )

        module_timeout = int(timeout)
        if should_use_module_orchestrator:
            env_timeout = str(os.getenv("PPT_MODULE_ORCHESTRATOR_TIMEOUT_SEC", "")).strip()
            if env_timeout:
                try:
                    module_timeout = max(module_timeout, int(float(env_timeout)))
                except Exception:
                    module_timeout = max(module_timeout, 420)
            else:
                module_timeout = max(module_timeout, 420)

        module_timeout_fallback_used = False
        try:
            result = _run(
                cmd,
                cmd_timeout=(module_timeout if should_use_module_orchestrator else int(timeout)),
            )
        except subprocess.TimeoutExpired:
            if should_use_module_orchestrator:
                logger.warning(
                    "[minimax_exporter] module orchestrator timed out after %ss; fallback to direct generator",
                    module_timeout,
                )
                cmd = _build_generator_cmd(
                    script_path=generator_script_path,
                    input_path=input_path,
                    output_path=output_path,
                    render_spec_path=render_spec_path,
                    payload=payload,
                    retry_scope=retry_scope,
                    target_slide_ids=target_slide_ids,
                    target_block_ids=target_block_ids,
                    retry_hint=retry_hint,
                    idempotency_key=idempotency_key,
                    verbatim_content=verbatim_content,
                    original_style=original_style,
                    disable_local_style_rewrite=disable_local_style_rewrite,
                    visual_priority=visual_priority,
                    visual_preset=visual_preset,
                    visual_density=visual_density,
                    constraint_hardness=constraint_hardness,
                    deck_id=deck_id,
                )
                result = _run(cmd, cmd_timeout=int(timeout))
                should_use_module_orchestrator = False
                should_use_module_mainflow = False
                should_use_module_retry = False
                module_timeout_fallback_used = True
            else:
                raise
        effective_mode = payload["generator_mode"]
        fallback_used = False
        legacy_fallback_enabled = bool(enable_legacy_fallback) and _allow_legacy_mode()
        if (
            result.returncode != 0
            and payload["generator_mode"] == "official"
            and legacy_fallback_enabled
            and not should_use_module_orchestrator
        ):
            fallback_cmd: List[str] = []
            skip_next = False
            for part in cmd:
                if skip_next:
                    skip_next = False
                    continue
                if part == "--generator-mode":
                    skip_next = True
                    continue
                fallback_cmd.append(part)
            fallback_cmd.extend(["--generator-mode", "legacy"])
            result = _run(fallback_cmd, cmd_timeout=int(timeout))
            effective_mode = "legacy"
            fallback_used = True

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            classification = classify_failure(detail)
            raise MiniMaxExportError(
                message=f"MiniMax PPTX export failed: {detail[:800]}",
                classification=classification,
                detail=detail,
            )
        if not output_path.exists():
            detail = "MiniMax PPTX export reported success but file was not created"
            classification = classify_failure(detail)
            raise MiniMaxExportError(
                message=detail,
                classification=classification,
                detail=detail,
            )

        render_spec: Dict[str, Any] = {}
        if render_spec_path.exists():
            try:
                parsed = json.loads(render_spec_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    render_spec = parsed
            except Exception as exc:
                logger.warning("failed to parse minimax render spec: %s", exc)

        generator_meta = _extract_json_from_stdout(result.stdout)
        if should_use_module_orchestrator:
            generator_meta["module_retry_enabled"] = True
            generator_meta["module_orchestrator_enabled"] = True
            generator_meta["module_orchestrator_mode"] = "slide_retry" if should_use_module_retry else "mainflow"
            generator_meta["module_retry_target_slide_ids"] = normalized_target_slide_ids if should_use_module_retry else []
            generator_meta["module_mainflow_enabled"] = bool(should_use_module_mainflow)
            generator_meta["module_mainflow_render_each_enabled"] = bool(render_each)
            if isinstance(generator_meta.get("compile"), dict):
                compile_meta = dict(generator_meta.get("compile") or {})
                compile_meta.setdefault("is_full_deck", True)
                generator_meta["compile"] = compile_meta
        if fallback_used:
            generator_meta["fallback_used"] = True
            generator_meta["generator_mode"] = effective_mode
        if module_timeout_fallback_used:
            generator_meta["module_timeout_fallback_used"] = True
        if channel_fallback_reason:
            generator_meta["channel_fallback_used"] = True
            generator_meta["channel_fallback_reason"] = channel_fallback_reason
        generator_meta["render_channel"] = effective_channel

        return {
            "pptx_bytes": output_path.read_bytes(),
            "generator_meta": generator_meta,
            "render_spec": render_spec,
            "input_payload": {
                **payload,
                "generator_mode": effective_mode,
                "render_channel": effective_channel,
                "requested_render_channel": requested_channel,
            },
            "generator_mode": effective_mode,
            "render_channel": effective_channel,
            "is_full_deck": bool(should_use_module_orchestrator or normalized_retry_scope == "deck"),
        }
    except subprocess.TimeoutExpired as exc:
        detail = f"subprocess.TimeoutExpired: {exc}"
        classification = classify_failure(detail)
        raise MiniMaxExportError(
            message=f"MiniMax PPTX export timeout after {timeout}s",
            classification=classification,
            detail=detail,
        ) from exc
    except MiniMaxExportError:
        raise
    except Exception as exc:
        detail = str(exc)
        classification = classify_failure(detail)
        raise MiniMaxExportError(
            message=f"MiniMax PPTX export failed: {detail[:800]}",
            classification=classification,
            detail=detail,
        ) from exc
    finally:
        for path in (input_path, output_path, render_spec_path):
            if path and path.exists():
                try:
                    path.unlink()
                except Exception:
                    logger.debug("failed to cleanup temp file: %s", path, exc_info=True)
        for dir_path in (modules_dir,):
            if dir_path and dir_path.exists():
                try:
                    shutil.rmtree(dir_path, ignore_errors=True)
                except Exception:
                    logger.debug("failed to cleanup temp dir: %s", dir_path, exc_info=True)
