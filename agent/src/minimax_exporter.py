"""Shared MiniMax PPTX export helper."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from xml.etree import ElementTree as ET
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
from src.ppt_svg_finalizer import PPTSvgFinalizer
from src.ppt_visual_identity import canonicalize_theme_recipe, resolve_style_variant, resolve_tone
from src.ppt_svg_renderer import render_slide_svg_markup, resolve_slide_svg_markup
from src.pptx_theme_patch import patch_pptx_theme_colors
from src.svg_to_pptx import create_pptx_with_native_svg

logger = logging.getLogger("minimax_exporter")

_TEMPLATE_ID_SET = set(list_template_ids())
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SUPPORTING_PREFIX_RE = re.compile(r"^(?:补充要点|supporting point)\s*[:：-]\s*", re.IGNORECASE)


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


def _is_valid_svg_markup(markup: str) -> bool:
    text = str(markup or "").strip()
    if not text:
        return False
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return False
    tag = str(root.tag or "").strip().lower()
    return tag.endswith("svg")


def _emergency_svg_markup() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">'
        '<rect width="1280" height="720" fill="#0B1220"/>'
        '<text x="80" y="140" fill="#F4F8FF" font-size="48" '
        'font-family="Microsoft YaHei, Segoe UI, Arial">Fallback Slide</text>'
        "</svg>"
    )


def _prepare_svg_slides(
    *,
    slides: List[Dict[str, Any]],
    deck_title: str,
    design_spec: Dict[str, Any] | None = None,
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    prepared: List[Dict[str, Any]] = []
    provided_count = 0
    templated_count = 0
    repaired_count = 0
    invalid_count = 0
    emergency_count = 0
    total = len(slides)
    for idx, raw in enumerate(slides):
        slide = dict(raw if isinstance(raw, dict) else {})
        markup = resolve_slide_svg_markup(slide)
        if markup:
            provided_count += 1
            if not _is_valid_svg_markup(markup):
                invalid_count += 1
                repaired_count += 1
                markup = ""
        if not markup:
            markup = render_slide_svg_markup(
                slide=slide,
                slide_index=idx,
                slide_count=total,
                deck_title=deck_title,
                design_spec=design_spec,
            )
            templated_count += 1
        if not _is_valid_svg_markup(markup):
            invalid_count += 1
            markup = _emergency_svg_markup()
            emergency_count += 1
        slide["render_path"] = "svg"
        slide["svg_markup"] = markup
        prepared.append(slide)
    return prepared, {
        "provided_svg_count": int(provided_count),
        "templated_svg_count": int(templated_count),
        "repaired_svg_count": int(repaired_count),
        "invalid_svg_count": int(invalid_count),
        "emergency_svg_count": int(emergency_count),
    }


def _extract_slide_notes(slide: Dict[str, Any]) -> str:
    for key in ("speaker_notes", "narration", "notes_for_designer", "notes", "script"):
        value = str(slide.get(key) or "").strip()
        if value:
            return value
    return ""


def _write_svg_files(
    *,
    slides: List[Dict[str, Any]],
    temp_root: Path,
) -> tuple[List[Path], Dict[str, str]]:
    svg_files: List[Path] = []
    notes: Dict[str, str] = {}
    for idx, slide in enumerate(slides):
        stem = f"slide_{idx + 1:03d}"
        svg_path = temp_root / f"{stem}.svg"
        markup = str(slide.get("svg_markup") or "")
        if not _is_valid_svg_markup(markup):
            raise ValueError(f"invalid_svg_markup_at_slide_{idx + 1}")
        svg_path.write_text(markup, encoding="utf-8")
        svg_files.append(svg_path)
        note_text = _extract_slide_notes(slide)
        if note_text:
            notes[stem] = note_text
    return svg_files, notes


def _assemble_pptx_with_drawingml(
    *,
    slides: List[Dict[str, Any]],
    temp_root: Path,
) -> tuple[bytes, Dict[str, int]]:
    svg_files, notes = _write_svg_files(slides=slides, temp_root=temp_root)
    finalizer = PPTSvgFinalizer()
    finalizer_result = finalizer.finalize_svg_files(svg_files)
    output_path = temp_root / "presentation.pptx"
    ok = create_pptx_with_native_svg(
        svg_files=svg_files,
        output_path=output_path,
        verbose=False,
        transition=None,
        auto_advance=None,
        use_compat_mode=False,
        notes=notes or None,
        enable_notes=bool(notes),
        use_native_shapes=True,
    )
    if (not ok) or (not output_path.exists()):
        raise RuntimeError("drawingml_export_failed")
    return output_path.read_bytes(), {
        "notes_slide_count": int(len(notes)),
        "svg_finalize_processed_files": int(finalizer_result.processed_files),
        "svg_finalize_steps_run": int(len(finalizer_result.steps_run)),
        "svg_finalize_step_errors": int(
            sum(
                int((stats or {}).get("errors") or 0)
                for stats in (finalizer_result.step_stats or {}).values()
            )
        ),
        "svg_finalize_skipped_steps": int(len(finalizer_result.skipped_steps)),
    }


def _render_all_slides_with_template(
    *,
    slides: List[Dict[str, Any]],
    deck_title: str,
    design_spec: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    rendered: List[Dict[str, Any]] = []
    total = len(slides)
    for idx, raw in enumerate(slides):
        slide = dict(raw if isinstance(raw, dict) else {})
        markup = render_slide_svg_markup(
            slide=slide,
            slide_index=idx,
            slide_count=total,
            deck_title=deck_title,
            design_spec=design_spec,
        )
        if not _is_valid_svg_markup(markup):
            markup = _emergency_svg_markup()
        slide["render_path"] = "svg"
        slide["svg_markup"] = markup
        rendered.append(slide)
    return rendered


def _build_render_spec(slides: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary_rows: List[Dict[str, Any]] = []
    for idx, slide in enumerate(slides):
        summary_rows.append(
            {
                "slide_id": str(slide.get("slide_id") or f"slide-{idx + 1}"),
                "page_number": idx + 1,
                "slide_type": str(slide.get("slide_type") or "content"),
                "layout_grid": str(slide.get("layout_grid") or "split_2"),
                "render_path": "svg",
            }
        )
    return {
        "mode": "minimax_presentation",
        "engine": "drawingml_native",
        "slides": summary_rows,
        "template_renderer_summary": {
            "evaluated_slides": len(summary_rows),
            "skipped_slides": 0,
            "skipped_ratio": 0.0,
            "mode_counts": {"drawingml_native": len(summary_rows)},
            "reason_counts": {},
            "reason_ratios": {},
        },
    }


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
    deck_archetype_profile: str = "",
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
    # DrawingML-first architecture: all slides are normalized to SVG route.
    for slide in normalized_slides:
        if isinstance(slide, dict):
            slide["render_path"] = "svg"
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
        # DrawingML export always operates at full-deck scope.
        "retry_scope": "deck",
        "target_slide_ids": [],
        "target_block_ids": [],
        "retry_hint": retry_hint,
        "idempotency_key": idempotency_key,
        "route_mode": str(route_mode or "standard").strip().lower() or "standard",
        "original_style": preserve_original,
        "disable_local_style_rewrite": disable_rewrite,
        "visual_priority": bool(visual_priority),
        "visual_preset": str(visual_preset or "auto"),
        "visual_density": str(visual_density or "balanced"),
        "deck_archetype_profile": str(deck_archetype_profile or "").strip().lower(),
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
    deck_archetype_profile: str = "",
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
        deck_archetype_profile=deck_archetype_profile,
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
    if requested_channel == "remote":
        classification = classify_failure("remote channel unsupported")
        raise MiniMaxExportError(
            message="MiniMax PPTX export failed: remote render_channel is not supported",
            classification=classification,
            detail=(
                "remote channel is disabled for drawingml exporter; "
                "call with render_channel=local and upload in service layer"
            ),
        )

    try:
        prepared_slides, svg_stats = _prepare_svg_slides(
            slides=[slide for slide in payload.get("slides", []) if isinstance(slide, dict)],
            deck_title=title,
            design_spec=payload.get("design_spec") if isinstance(payload.get("design_spec"), dict) else None,
        )
        payload["slides"] = prepared_slides

        with tempfile.TemporaryDirectory(prefix="drawingml_export_") as tmp_dir:
            temp_root = Path(tmp_dir)
            try:
                output_bytes, assembly_stats = _assemble_pptx_with_drawingml(
                    slides=prepared_slides,
                    temp_root=temp_root,
                )
            except Exception as first_exc:
                logger.warning(
                    "[minimax_exporter] drawingml primary assembly failed, retrying with fully templated SVG: %s",
                    first_exc,
                )
                retry_slides = _render_all_slides_with_template(
                    slides=prepared_slides,
                    deck_title=title,
                    design_spec=payload.get("design_spec")
                    if isinstance(payload.get("design_spec"), dict)
                    else None,
                )
                try:
                    output_bytes, assembly_stats = _assemble_pptx_with_drawingml(
                        slides=retry_slides,
                        temp_root=temp_root,
                    )
                    prepared_slides = retry_slides
                    payload["slides"] = prepared_slides
                    svg_stats["full_template_retry_used"] = 1
                    svg_stats["full_template_retry_slides"] = len(retry_slides)
                except Exception as retry_exc:
                    detail = f"drawingml_export_failed: {first_exc}; retry_failed: {retry_exc}"
                    classification = classify_failure(detail)
                    raise MiniMaxExportError(
                        message="MiniMax PPTX export failed: DrawingML assembly failed",
                        classification=classification,
                        detail=detail,
                    ) from retry_exc

        render_spec = _build_render_spec(prepared_slides)
        effective_mode = "drawingml"
        generator_meta: Dict[str, Any] = {
            "success": True,
            "engine": "drawingml_native",
            "generator_mode": effective_mode,
            "requested_generator_mode": str(payload.get("generator_mode") or "official"),
            "render_channel": effective_channel,
            "render_slides": len(prepared_slides),
            "timeout_sec": int(timeout),
            **svg_stats,
            **assembly_stats,
        }
        themed_bytes = patch_pptx_theme_colors(
            output_bytes,
            payload.get("minimax_palette_key") or payload.get("theme", {}).get("palette") or "",
        )
        return {
            "pptx_bytes": themed_bytes,
            "generator_meta": generator_meta,
            "render_spec": render_spec,
            "input_payload": {
                **payload,
                "generator_mode": effective_mode,
                "render_channel": effective_channel,
            },
            "generator_mode": effective_mode,
            "render_channel": effective_channel,
            "is_full_deck": True,
        }
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
