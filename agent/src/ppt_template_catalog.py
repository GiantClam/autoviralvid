"""Shared template catalog loader for PPT render contract."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Set


_DEFAULT_TEMPLATE_ID = "dashboard_dark"


def _catalog_path() -> Path:
    # <repo>/agent/src/ppt_template_catalog.py -> <repo>/scripts/minimax/templates/template-catalog.json
    return Path(__file__).resolve().parents[2] / "scripts" / "minimax" / "templates" / "template-catalog.json"


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


@lru_cache(maxsize=1)
def get_template_catalog() -> Dict[str, Any]:
    path = _catalog_path()
    if not path.exists():
        return {
            "layout_defaults": {},
            "subtype_overrides": {},
            "keyword_rules": [],
            "contract_profiles": {},
            "quality_profiles": {},
            "templates": {},
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "layout_defaults": {},
            "subtype_overrides": {},
            "keyword_rules": [],
            "contract_profiles": {},
            "quality_profiles": {},
            "templates": {},
        }
    return {
        "layout_defaults": _as_dict(data.get("layout_defaults")),
        "subtype_overrides": _as_dict(data.get("subtype_overrides")),
        "keyword_rules": data.get("keyword_rules") if isinstance(data.get("keyword_rules"), list) else [],
        "contract_profiles": _as_dict(data.get("contract_profiles")),
        "quality_profiles": _as_dict(data.get("quality_profiles")),
        "templates": _as_dict(data.get("templates")),
    }


def list_template_ids() -> List[str]:
    return list(get_template_catalog().get("templates", {}).keys())


def template_profiles(template_id: str) -> Dict[str, str]:
    templates = _as_dict(get_template_catalog().get("templates"))
    candidate = str(template_id or "").strip().lower()
    if candidate not in templates:
        candidate = _DEFAULT_TEMPLATE_ID
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
    candidate = str(defaults.get(str(layout_grid or "").strip().lower()) or _DEFAULT_TEMPLATE_ID).strip().lower()
    if candidate in list_template_ids():
        return candidate
    return _DEFAULT_TEMPLATE_ID


_DENSITY_ORDER = {"sparse": 0, "balanced": 1, "dense": 2}
_VISUAL_BLOCK_TYPES = {"image", "chart", "kpi", "workflow", "diagram"}
_DATA_BLOCK_TYPES = {"chart", "kpi", "table"}


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
    return {
        "id": requested,
        "min_typography_levels": max(1, int(profile.get("min_typography_levels") or 2)),
        "min_content_blocks": max(1, int(profile.get("min_content_blocks") or 2)),
        "blank_area_max_ratio": max(0.1, min(0.9, float(profile.get("blank_area_max_ratio") or 0.45))),
        "chart_min_font_size": max(6.0, float(profile.get("chart_min_font_size") or 9)),
        "require_emphasis_signal": bool(profile.get("require_emphasis_signal", True)),
        "forbid_duplicate_text": bool(profile.get("forbid_duplicate_text", True)),
        "forbid_title_echo": bool(profile.get("forbid_title_echo", True)),
        "require_image_url": bool(profile.get("require_image_url", True)),
        "layout_max_type_ratio": max(0.1, min(0.95, float(profile.get("layout_max_type_ratio") or 0.45))),
        "layout_max_adjacent_repeat": max(1, int(profile.get("layout_max_adjacent_repeat") or 1)),
        "layout_min_slide_count": max(2, int(profile.get("layout_min_slide_count") or 6)),
        "layout_min_variety_long_deck": max(1, int(profile.get("layout_min_variety_long_deck") or 4)),
        "layout_long_deck_threshold": max(4, int(profile.get("layout_long_deck_threshold") or 10)),
        "enforce_terminal_slide_types": bool(profile.get("enforce_terminal_slide_types", False)),
    }


def template_capabilities(template_id: str) -> Dict[str, Any]:
    templates = _as_dict(get_template_catalog().get("templates"))
    requested = str(template_id or "").strip().lower()
    if requested not in templates:
        requested = _DEFAULT_TEMPLATE_ID
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
) -> str:
    templates = _as_dict(get_template_catalog().get("templates"))
    template_ids = list(templates.keys())
    requested = str(requested_template or "").strip().lower()
    if requested and requested in templates:
        return requested

    normalized_type = str(slide_type or "").strip().lower() or "content"
    normalized_layout = str(layout_grid or "").strip().lower() or "split_2"
    if normalized_type in {"cover", "hero_1"} or normalized_layout == "hero_1":
        return "hero_tech_cover"
    if normalized_type == "summary":
        return "hero_dark"

    desired = _normalize_density(desired_density)
    block_types = _extract_block_types(slide)
    blob = _build_text_blob(slide)
    layout_default = default_template_for_layout(normalized_layout)
    keyword_rules = get_template_catalog().get("keyword_rules") or []

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
    best_template = layout_default
    best_score = -10_000.0

    for template_id in template_ids:
        cap = template_capabilities(template_id)
        contract = contract_profile(str(_as_dict(templates.get(template_id)).get("contract_profile") or "default"))
        score = 0.0

        if normalized_layout in set(cap["supported_layouts"]):
            score += 3.0
        if normalized_type in set(cap["supported_slide_types"]):
            score += 2.5

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
        if int(contract.get("min_visual_blocks") or 0) > 0 and not needs_visual:
            score -= 4.0
        if needs_data:
            score += 1.5 if cap["data_block_capacity"] > 0 else -4.0

        kw_score = _keyword_score(template_id)
        score += min(3.0, float(kw_score))
        if template_id == "architecture_dark_panel" and kw_score < 2 and "workflow" not in block_types:
            score -= 2.0

        if template_id == layout_default:
            score += 1.2

        if score > best_score:
            best_score = score
            best_template = template_id

    return best_template if best_template in templates else _DEFAULT_TEMPLATE_ID
