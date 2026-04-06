"""Shared template catalog loader for PPT render contract."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Set

from src.schemas.ppt_policy import (
    QualityOrchestrationPolicy,
    RoutePolicyConfig,
    RouteRecommendationConfig,
)


_DEFAULT_TEMPLATE_ID_FALLBACK = "consulting_warm_light"
_DEFAULT_ROUTE_POLICIES = {
    "fast": RoutePolicyConfig(
        mode="fast",
        max_retry_attempts=1,
        partial_retry_enabled=False,
        run_post_render_visual_qa=False,
        require_weighted_quality_score=False,
        force_rasterization=False,
        quality_threshold_offset=-6.0,
        warn_threshold_offset=-5.0,
    ),
    "standard": RoutePolicyConfig(
        mode="standard",
        max_retry_attempts=3,
        partial_retry_enabled=True,
        run_post_render_visual_qa=True,
        require_weighted_quality_score=True,
        force_rasterization=True,
        quality_threshold_offset=0.0,
        warn_threshold_offset=0.0,
    ),
    "refine": RoutePolicyConfig(
        mode="refine",
        max_retry_attempts=4,
        partial_retry_enabled=True,
        run_post_render_visual_qa=True,
        require_weighted_quality_score=True,
        force_rasterization=True,
        quality_threshold_offset=4.0,
        warn_threshold_offset=4.0,
    ),
}
_DEFAULT_ROUTE_RECOMMENDATION = RouteRecommendationConfig()


def _catalog_path() -> Path:
    # <repo>/agent/src/ppt_template_catalog.py -> <repo>/scripts/minimax/templates/template-catalog.json
    return Path(__file__).resolve().parents[2] / "scripts" / "minimax" / "templates" / "template-catalog.json"


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_key(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


@lru_cache(maxsize=1)
def get_template_catalog() -> Dict[str, Any]:
    path = _catalog_path()
    if not path.exists():
        return {
            "default_template_id": _DEFAULT_TEMPLATE_ID_FALLBACK,
            "default_palette_key": "business_authority",
            "default_theme_recipe": "consulting_clean",
            "layout_defaults": {},
            "subtype_overrides": {},
            "palettes": {},
            "palette_aliases": {},
            "theme_recipes": {},
            "palette_keywords": {},
            "keyword_rules": [],
            "contract_profiles": {},
            "quality_profiles": {},
            "route_policies": {},
            "templates": {},
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "default_template_id": _DEFAULT_TEMPLATE_ID_FALLBACK,
            "default_palette_key": "business_authority",
            "default_theme_recipe": "consulting_clean",
            "layout_defaults": {},
            "subtype_overrides": {},
            "palettes": {},
            "palette_aliases": {},
            "theme_recipes": {},
            "palette_keywords": {},
            "keyword_rules": [],
            "contract_profiles": {},
            "quality_profiles": {},
            "route_policies": {},
            "templates": {},
        }
    return {
        "default_template_id": str(data.get("default_template_id") or _DEFAULT_TEMPLATE_ID_FALLBACK).strip().lower(),
        "default_palette_key": str(data.get("default_palette_key") or "business_authority").strip().lower(),
        "default_theme_recipe": str(data.get("default_theme_recipe") or "consulting_clean").strip().lower(),
        "layout_defaults": _as_dict(data.get("layout_defaults")),
        "subtype_overrides": _as_dict(data.get("subtype_overrides")),
        "palettes": _as_dict(data.get("palettes")),
        "palette_aliases": _as_dict(data.get("palette_aliases")),
        "theme_recipes": _as_dict(data.get("theme_recipes")),
        "palette_keywords": _as_dict(data.get("palette_keywords")),
        "keyword_rules": data.get("keyword_rules") if isinstance(data.get("keyword_rules"), list) else [],
        "contract_profiles": _as_dict(data.get("contract_profiles")),
        "quality_profiles": _as_dict(data.get("quality_profiles")),
        "route_policies": _as_dict(data.get("route_policies")),
        "templates": _as_dict(data.get("templates")),
    }


def list_template_ids() -> List[str]:
    return list(get_template_catalog().get("templates", {}).keys())


def default_template_id() -> str:
    catalog = get_template_catalog()
    templates = _as_dict(catalog.get("templates"))
    template_ids = list(templates.keys())
    requested = str(catalog.get("default_template_id") or "").strip().lower()
    if requested and requested in template_ids:
        return requested
    if _DEFAULT_TEMPLATE_ID_FALLBACK in template_ids:
        return _DEFAULT_TEMPLATE_ID_FALLBACK
    if "dashboard_dark" in template_ids:
        return "dashboard_dark"
    return template_ids[0] if template_ids else _DEFAULT_TEMPLATE_ID_FALLBACK


def template_profiles(template_id: str) -> Dict[str, str]:
    templates = _as_dict(get_template_catalog().get("templates"))
    candidate = str(template_id or "").strip().lower()
    if candidate not in templates:
        candidate = default_template_id()
    profile = _as_dict(templates.get(candidate))
    return {
        "template_id": candidate,
        "skill_profile": str(profile.get("skill_profile") or "general-content"),
        "hardness_profile": str(profile.get("hardness_profile") or "balanced"),
        "schema_profile": str(profile.get("schema_profile") or "ppt-template/v2-generic"),
        "contract_profile": str(profile.get("contract_profile") or "default"),
        "quality_profile": str(profile.get("quality_profile") or "default"),
    }


def default_template_for_layout(layout_grid: str) -> str:
    defaults = _as_dict(get_template_catalog().get("layout_defaults"))
    candidate = str(defaults.get(str(layout_grid or "").strip().lower()) or default_template_id()).strip().lower()
    if candidate in list_template_ids():
        return candidate
    return default_template_id()


_DENSITY_ORDER = {"sparse": 0, "balanced": 1, "dense": 2}
_VISUAL_BLOCK_TYPES = {"image", "chart", "kpi", "workflow", "diagram"}
_DATA_BLOCK_TYPES = {"chart", "kpi", "table"}
_LIGHT_THEME_HINTS = (
    "education",
    "teaching",
    "training",
    "classroom",
    "student",
    "school",
    "curriculum",
    "lesson",
    "academic",
    "\u6559\u5b66",
    "\u8bfe\u5802",
    "\u6559\u80b2",
    "\u57f9\u8bad",
    "\u5b66\u6821",
    "\u8bfe\u7a0b",
    "\u9ad8\u6821",
)
_TERMINAL_TEMPLATE_IDS = {"hero_dark", "hero_tech_cover", "quote_hero_dark"}
_LAYOUT_CARD_COUNTS = {
    "hero_1": 1,
    "split_2": 2,
    "asymmetric_2": 2,
    "grid_3": 3,
    "grid_4": 4,
    "bento_5": 5,
    "bento_6": 6,
    "timeline": 5,
}


def _normalize_tone(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"light", "dark"}:
        return normalized
    return ""


def _normalize_density(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _DENSITY_ORDER:
        return normalized
    return "balanced"


def _extract_block_types(slide: Dict[str, Any]) -> Set[str]:
    block_types: Set[str] = set()
    blocks = slide.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict):
                continue
            t = str(block.get("block_type") or block.get("type") or "").strip().lower()
            if t:
                block_types.add(t)
    elements = slide.get("elements")
    if isinstance(elements, list):
        for el in elements:
            if not isinstance(el, dict):
                continue
            t = str(el.get("type") or "").strip().lower()
            if t:
                block_types.add(t)
    return block_types


def _has_image_asset(slide: Dict[str, Any]) -> bool:
    blocks = slide.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict):
                continue
            t = str(block.get("block_type") or block.get("type") or "").strip().lower()
            if t != "image":
                continue
            content = block.get("content")
            data = block.get("data")
            content_obj = content if isinstance(content, dict) else {}
            data_obj = data if isinstance(data, dict) else {}
            candidates = [
                content_obj.get("url"),
                content_obj.get("src"),
                content_obj.get("imageUrl"),
                content_obj.get("image_url"),
                data_obj.get("url"),
                data_obj.get("src"),
                data_obj.get("imageUrl"),
                data_obj.get("image_url"),
                block.get("url"),
                block.get("src"),
                block.get("imageUrl"),
                block.get("image_url"),
            ]
            if any(str(item or "").strip() for item in candidates):
                return True

    elements = slide.get("elements")
    if isinstance(elements, list):
        for element in elements:
            if not isinstance(element, dict):
                continue
            t = str(element.get("type") or "").strip().lower()
            if t != "image":
                continue
            candidates = [
                element.get("url"),
                element.get("src"),
                element.get("imageUrl"),
                element.get("image_url"),
            ]
            if any(str(item or "").strip() for item in candidates):
                return True
    return False


def _build_text_blob(slide: Dict[str, Any]) -> str:
    parts = [
        str(slide.get("title") or ""),
        str(slide.get("narration") or ""),
        str(slide.get("speaker_notes") or ""),
    ]
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        content = block.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, dict):
            for key in ("title", "body", "text", "label", "caption", "description"):
                value = str(content.get(key) or "").strip()
                if value:
                    parts.append(value)
    return " ".join(parts).lower()


def _prefers_light_theme(blob: str, block_types: Set[str], *, needs_data: bool, has_image_visual: bool) -> bool:
    hint_hit = any(token in blob for token in _LIGHT_THEME_HINTS)
    _ = (block_types, needs_data, has_image_visual)
    return bool(hint_hit)


def _normalize_archetype_candidates(raw: Any) -> List[str]:
    rows = raw if isinstance(raw, list) else []
    out: List[str] = []
    seen: Set[str] = set()
    for row in rows:
        if isinstance(row, str):
            value = row
        elif isinstance(row, dict):
            value = row.get("archetype")
        else:
            value = ""
        key = _normalize_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _template_archetype_bonus(
    *,
    template_row: Dict[str, Any],
    selected_archetype: str,
    archetype_candidates: List[str],
) -> float:
    preferred = _normalize_archetype_candidates(template_row.get("preferred_archetypes"))
    if not preferred:
        return 0.0
    selected = _normalize_key(selected_archetype)
    if selected and selected in preferred:
        return 3.2
    if any(candidate in preferred for candidate in archetype_candidates):
        return 1.4
    return 0.0


def contract_profile(contract_id: str) -> Dict[str, Any]:
    catalog = get_template_catalog()
    profiles = _as_dict(catalog.get("contract_profiles"))
    requested = str(contract_id or "").strip().lower() or "default"
    profile = _as_dict(profiles.get(requested))
    if not profile and requested != "default":
        profile = _as_dict(profiles.get("default"))
        requested = "default"
    required = profile.get("required_block_types")
    groups = profile.get("required_one_of_groups")
    visual_types = profile.get("visual_anchor_types")
    return {
        "id": requested,
        "required_block_types": [str(x).strip().lower() for x in required] if isinstance(required, list) else [],
        "required_one_of_groups": (
            [
                [str(y).strip().lower() for y in group if str(y).strip()]
                for group in groups
                if isinstance(group, list)
            ]
            if isinstance(groups, list)
            else []
        ),
        "min_text_blocks": int(profile.get("min_text_blocks") or 0),
        "min_visual_blocks": int(profile.get("min_visual_blocks") or 0),
        "visual_anchor_types": (
            [str(x).strip().lower() for x in visual_types if str(x).strip()]
            if isinstance(visual_types, list)
            else sorted(_VISUAL_BLOCK_TYPES)
        ),
        "require_emphasis_signal": bool(profile.get("require_emphasis_signal", False)),
        "forbid_duplicate_text": bool(profile.get("forbid_duplicate_text", False)),
    }


def quality_profile(profile_id: str = "default") -> Dict[str, Any]:
    catalog = get_template_catalog()
    profiles = _as_dict(catalog.get("quality_profiles"))
    requested = str(profile_id or "").strip().lower() or "default"
    profile = _as_dict(profiles.get(requested))
    if not profile and requested != "default":
        profile = _as_dict(profiles.get("default"))
        requested = "default"
    if not profile:
        profile = {}
    raw_weights = _as_dict(profile.get("quality_score_weights"))
    structure_weight = float(raw_weights.get("structure") or 0.26)
    layout_weight = float(raw_weights.get("layout") or 0.20)
    family_weight = float(raw_weights.get("family") or 0.16)
    visual_weight = float(raw_weights.get("visual") or 0.22)
    consistency_weight = float(raw_weights.get("consistency") or 0.16)
    total_weight = structure_weight + layout_weight + family_weight + visual_weight + consistency_weight
    if total_weight <= 0:
        total_weight = 1.0
    min_content_blocks = max(1, int(profile.get("min_content_blocks") or 2))
    raw_orchestration = _as_dict(profile.get("orchestration"))
    try:
        parsed_orchestration = QualityOrchestrationPolicy.model_validate(raw_orchestration)
    except Exception:
        parsed_orchestration = QualityOrchestrationPolicy()
    orchestration = parsed_orchestration.model_dump()
    if "require_image_anchor" not in raw_orchestration:
        orchestration["require_image_anchor"] = min_content_blocks >= 3
    normalized_weights = {
        "structure": max(0.0, structure_weight) / total_weight,
        "layout": max(0.0, layout_weight) / total_weight,
        "family": max(0.0, family_weight) / total_weight,
        "visual": max(0.0, visual_weight) / total_weight,
        "consistency": max(0.0, consistency_weight) / total_weight,
    }
    return {
        "id": requested,
        "min_typography_levels": max(1, int(profile.get("min_typography_levels") or 2)),
        "min_content_blocks": min_content_blocks,
        "blank_area_max_ratio": max(0.1, min(0.9, float(profile.get("blank_area_max_ratio") or 0.45))),
        "chart_min_font_size": max(6.0, float(profile.get("chart_min_font_size") or 9)),
        "require_emphasis_signal": bool(profile.get("require_emphasis_signal", True)),
        "forbid_duplicate_text": bool(profile.get("forbid_duplicate_text", True)),
        "forbid_title_echo": bool(profile.get("forbid_title_echo", True)),
        "require_image_url": bool(profile.get("require_image_url", True)),
        "layout_max_type_ratio": max(0.1, min(0.95, float(profile.get("layout_max_type_ratio") or 0.45))),
        "layout_max_top2_ratio": max(0.1, min(1.0, float(profile.get("layout_max_top2_ratio") or 0.65))),
        "layout_max_adjacent_repeat": max(1, int(profile.get("layout_max_adjacent_repeat") or 1)),
        "layout_abab_max_run": max(4, int(profile.get("layout_abab_max_run") or 4)),
        "layout_min_slide_count": max(2, int(profile.get("layout_min_slide_count") or 6)),
        "layout_min_variety_long_deck": max(1, int(profile.get("layout_min_variety_long_deck") or 4)),
        "layout_long_deck_threshold": max(4, int(profile.get("layout_long_deck_threshold") or 10)),
        "density_max_consecutive_high": max(1, int(profile.get("density_max_consecutive_high") or 2)),
        "density_window_size": max(3, int(profile.get("density_window_size") or 5)),
        "density_require_low_or_breathing_per_window": max(
            1, int(profile.get("density_require_low_or_breathing_per_window") or 1)
        ),
        "enforce_terminal_slide_types": bool(profile.get("enforce_terminal_slide_types", False)),
        "template_family_max_type_ratio": max(0.1, min(1.0, float(profile.get("template_family_max_type_ratio") or 0.55))),
        "template_family_max_top2_ratio": max(0.1, min(1.0, float(profile.get("template_family_max_top2_ratio") or 0.8))),
        "template_family_max_switch_ratio": max(0.0, min(1.0, float(profile.get("template_family_max_switch_ratio") or 0.75))),
        "template_family_abab_max_run": max(4, int(profile.get("template_family_abab_max_run") or 6)),
        "template_family_min_slide_count": max(2, int(profile.get("template_family_min_slide_count") or 8)),
        "pagination_max_bullets_per_slide": max(3, int(profile.get("pagination_max_bullets_per_slide") or 6)),
        "pagination_max_chars_per_slide": max(120, int(profile.get("pagination_max_chars_per_slide") or 360)),
        "pagination_max_continuation_pages": max(1, int(profile.get("pagination_max_continuation_pages") or 3)),
        "visual_blank_slide_max_ratio": max(0.0, min(1.0, float(profile.get("visual_blank_slide_max_ratio") or 0.05))),
        "visual_low_contrast_max_ratio": max(0.0, min(1.0, float(profile.get("visual_low_contrast_max_ratio") or 0.22))),
        "visual_blank_area_max_ratio": max(0.0, min(1.0, float(profile.get("visual_blank_area_max_ratio") or 0.55))),
        "visual_style_drift_max_ratio": max(0.0, min(1.0, float(profile.get("visual_style_drift_max_ratio") or 1.0))),
        "visual_text_overlap_max_ratio": max(0.0, min(1.0, float(profile.get("visual_text_overlap_max_ratio") or 0.75))),
        "visual_occlusion_max_ratio": max(0.0, min(1.0, float(profile.get("visual_occlusion_max_ratio") or 0.75))),
        "visual_card_overlap_max_ratio": max(0.0, min(1.0, float(profile.get("visual_card_overlap_max_ratio") or 0.65))),
        "visual_title_crowded_max_ratio": max(0.0, min(1.0, float(profile.get("visual_title_crowded_max_ratio") or 0.65))),
        "visual_multi_title_max_ratio": max(0.0, min(1.0, float(profile.get("visual_multi_title_max_ratio") or 0.5))),
        "visual_text_overflow_max_ratio": max(0.0, min(1.0, float(profile.get("visual_text_overflow_max_ratio") or 0.65))),
        "visual_irrelevant_image_max_ratio": max(0.0, min(1.0, float(profile.get("visual_irrelevant_image_max_ratio") or 0.25))),
        "visual_image_distortion_max_ratio": max(0.0, min(1.0, float(profile.get("visual_image_distortion_max_ratio") or 0.25))),
        "visual_whitespace_max_ratio": max(0.0, min(1.0, float(profile.get("visual_whitespace_max_ratio") or 0.45))),
        "visual_layout_monotony_max_ratio": max(0.0, min(1.0, float(profile.get("visual_layout_monotony_max_ratio") or 0.45))),
        "visual_style_inconsistent_max_ratio": max(0.0, min(1.0, float(profile.get("visual_style_inconsistent_max_ratio") or 0.45))),
        "require_visual_audit": bool(profile.get("require_visual_audit", True)),
        "quality_score_threshold": max(1.0, min(100.0, float(profile.get("quality_score_threshold") or 72))),
        "quality_score_warn_threshold": max(1.0, min(100.0, float(profile.get("quality_score_warn_threshold") or 80))),
        "quality_score_weights": normalized_weights,
        "orchestration": orchestration,
    }


def route_policy(mode: str) -> Dict[str, Any]:
    requested = str(mode or "").strip().lower()
    if requested not in _DEFAULT_ROUTE_POLICIES:
        requested = "standard"
    route_root = _as_dict(get_template_catalog().get("route_policies"))
    raw = _as_dict(route_root.get(requested))
    fallback = _DEFAULT_ROUTE_POLICIES[requested].model_dump()
    merged = {**fallback, **raw, "mode": requested}
    try:
        parsed = RoutePolicyConfig.model_validate(merged)
    except Exception:
        parsed = _DEFAULT_ROUTE_POLICIES[requested]
    return parsed.model_dump()


def route_recommendation_policy() -> Dict[str, Any]:
    route_root = _as_dict(get_template_catalog().get("route_policies"))
    raw = _as_dict(route_root.get("recommendation"))
    fallback = _DEFAULT_ROUTE_RECOMMENDATION.model_dump()
    merged = {**fallback, **raw}
    try:
        parsed = RouteRecommendationConfig.model_validate(merged)
    except Exception:
        parsed = _DEFAULT_ROUTE_RECOMMENDATION
    return parsed.model_dump()


def template_capabilities(template_id: str) -> Dict[str, Any]:
    templates = _as_dict(get_template_catalog().get("templates"))
    requested = str(template_id or "").strip().lower()
    if requested not in templates:
        requested = default_template_id()
    raw = _as_dict(_as_dict(templates.get(requested)).get("capabilities"))
    density_raw = _as_dict(raw.get("density_range"))
    supported_slide_types = raw.get("supported_slide_types")
    supported_layouts = raw.get("supported_layouts")
    supported_block_types = raw.get("supported_block_types")
    return {
        "template_id": requested,
        "supported_slide_types": (
            [str(x).strip().lower() for x in supported_slide_types if str(x).strip()]
            if isinstance(supported_slide_types, list)
            else ["content"]
        ),
        "supported_layouts": (
            [str(x).strip().lower() for x in supported_layouts if str(x).strip()]
            if isinstance(supported_layouts, list)
            else ["split_2"]
        ),
        "supported_block_types": (
            [str(x).strip().lower() for x in supported_block_types if str(x).strip()]
            if isinstance(supported_block_types, list)
            else ["title", "body", "list"]
        ),
        "density_range": {
            "min": _normalize_density(str(density_raw.get("min") or "sparse")),
            "max": _normalize_density(str(density_raw.get("max") or "dense")),
            "recommended": _normalize_density(str(density_raw.get("recommended") or "balanced")),
        },
        "visual_anchor_capacity": int(raw.get("visual_anchor_capacity") or 0),
        "data_block_capacity": int(raw.get("data_block_capacity") or 0),
        "requires_image_asset": bool(raw.get("requires_image_asset", False)),
    }


def resolve_template_for_slide(
    *,
    slide: Dict[str, Any],
    slide_type: str,
    layout_grid: str,
    requested_template: str = "",
    desired_density: str = "balanced",
    preferred_tone: str = "",
) -> str:
    templates = _as_dict(get_template_catalog().get("templates"))
    template_ids = list(templates.keys())
    requested = str(requested_template or "").strip().lower()
    if requested and requested in templates:
        return requested

    normalized_type = str(slide_type or "").strip().lower() or "content"
    normalized_layout = str(layout_grid or "").strip().lower() or "split_2"
    if normalized_type == "cover":
        return "hero_tech_cover"
    if normalized_type == "toc":
        return "hero_dark"
    if normalized_type in {"summary", "divider"}:
        return "quote_hero_dark"
    if normalized_type == "hero_1":
        return "hero_tech_cover"
    if normalized_layout == "hero_1":
        return "hero_dark"

    desired = _normalize_density(desired_density)
    block_types = _extract_block_types(slide)
    blob = _build_text_blob(slide)
    layout_default = default_template_for_layout(normalized_layout)
    keyword_rules = get_template_catalog().get("keyword_rules") or []
    layout_capacity = int(_LAYOUT_CARD_COUNTS.get(normalized_layout, 3))
    normalized_preferred_tone = _normalize_tone(preferred_tone)
    selected_archetype = _normalize_key(slide.get("archetype") or "")
    archetype_candidates = _normalize_archetype_candidates(slide.get("archetype_candidates"))

    def _keyword_score(candidate: str) -> int:
        best = 0
        for rule in keyword_rules:
            if not isinstance(rule, dict):
                continue
            if str(rule.get("template") or "").strip().lower() != candidate:
                continue
            kws = rule.get("keywords")
            if not isinstance(kws, list):
                continue
            score = 0
            for kw in kws:
                token = str(kw or "").strip().lower()
                if token and token in blob:
                    score += 1
            best = max(best, score)
        return best

    needs_visual = bool(block_types & _VISUAL_BLOCK_TYPES) or bool(slide.get("image_keywords"))
    needs_data = bool(block_types & _DATA_BLOCK_TYPES)
    has_image_visual = _has_image_asset(slide)
    prefers_light_theme = _prefers_light_theme(
        blob,
        block_types,
        needs_data=needs_data,
        has_image_visual=has_image_visual,
    )
    best_template = layout_default
    best_score = -10_000.0

    for template_id in template_ids:
        cap = template_capabilities(template_id)
        template_row = _as_dict(templates.get(template_id))
        contract = contract_profile(str(template_row.get("contract_profile") or "default"))
        score = 0.0
        supported_layouts = set(cap["supported_layouts"])
        supported_types = set(cap["supported_slide_types"])

        if normalized_layout in supported_layouts:
            score += 4.0
        else:
            score -= 6.0
        if normalized_type in supported_types:
            score += 3.0
        else:
            score -= 4.0
        # Keep cover/quote templates away from regular content pages.
        if normalized_type == "content" and template_id in _TERMINAL_TEMPLATE_IDS:
            score -= 7.5

        density_min = _DENSITY_ORDER.get(cap["density_range"]["min"], 0)
        density_max = _DENSITY_ORDER.get(cap["density_range"]["max"], 2)
        density_target = _DENSITY_ORDER.get(desired, 1)
        if density_min <= density_target <= density_max:
            score += 2.0
        else:
            score -= 2.0

        supported_blocks = set(cap["supported_block_types"])
        for bt in block_types:
            if bt in supported_blocks:
                score += 0.35
            else:
                score -= 0.8

        if needs_visual:
            score += 1.5 if cap["visual_anchor_capacity"] > 0 else -4.0
        if cap.get("requires_image_asset") and not has_image_visual:
            score -= 5.0
        required_text = int(contract.get("min_text_blocks") or 0)
        required_visual = int(contract.get("min_visual_blocks") or 0)
        min_required_non_title = required_text + required_visual
        # Hard feasibility guard: avoid templates whose contract cannot fit
        # the selected layout card capacity.
        if layout_capacity > 0 and min_required_non_title > layout_capacity:
            score -= 10.0
        if required_visual > 0 and not needs_visual:
            score -= 2.0
        if needs_data:
            score += 1.5 if cap["data_block_capacity"] > 0 else -4.0

        kw_score = _keyword_score(template_id)
        score += min(3.0, float(kw_score))
        score += _template_archetype_bonus(
            template_row=template_row,
            selected_archetype=selected_archetype,
            archetype_candidates=archetype_candidates,
        )
        if template_id == "architecture_dark_panel" and kw_score < 2 and "workflow" not in block_types:
            score -= 2.0

        if prefers_light_theme:
            if template_id.endswith("_light"):
                score += 3.2
            elif template_id.endswith("_dark"):
                score -= 2.4
        if normalized_preferred_tone == "light":
            if template_id.endswith("_light"):
                score += 4.0
            elif template_id.endswith("_dark"):
                score -= 3.2
        elif normalized_preferred_tone == "dark":
            if template_id.endswith("_dark"):
                score += 3.2
            elif template_id.endswith("_light"):
                score -= 2.6

        if template_id == layout_default:
            score += 1.2

        if score > best_score:
            best_score = score
            best_template = template_id

    return best_template if best_template in templates else default_template_id()
