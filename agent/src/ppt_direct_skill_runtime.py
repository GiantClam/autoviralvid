"""Direct skill runtime adapter for PPT planning.

This module is designed to be invoked as an external process by
``src.installed_skill_executor`` through stdin/stdout JSON.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List


_DEFAULT_LAYOUT_BY_SLIDE_TYPE: Dict[str, str] = {
    "cover": "hero_1",
    "toc": "hero_1",
    "divider": "hero_1",
    "section": "hero_1",
    "summary": "hero_1",
    "content": "split_2",
    "comparison": "split_2",
    "timeline": "timeline",
    "workflow": "timeline",
}

_AGENT_BY_SLIDE_TYPE: Dict[str, str] = {
    "cover": "cover-page-generator",
    "toc": "table-of-contents-generator",
    "divider": "section-divider-generator",
    "section": "section-divider-generator",
    "summary": "summary-page-generator",
    "content": "content-page-generator",
}

_STYLE_TEMPLATE_BY_TYPE: Dict[str, Dict[str, str]] = {
    "sharp": {
        "cover": "hero_tech_cover",
        "toc": "dashboard_dark",
        "divider": "architecture_dark_panel",
        "summary": "dashboard_dark",
        "content": "architecture_dark_panel",
    },
    "soft": {
        "cover": "hero_dark",
        "toc": "dashboard_dark",
        "divider": "dashboard_dark",
        "summary": "dashboard_dark",
        "content": "dashboard_dark",
    },
    "rounded": {
        "cover": "hero_dark",
        "toc": "ops_lifecycle_light",
        "divider": "ops_lifecycle_light",
        "summary": "ops_lifecycle_light",
        "content": "ops_lifecycle_light",
    },
    "pill": {
        "cover": "hero_dark",
        "toc": "dashboard_dark",
        "divider": "ecosystem_orange_dark",
        "summary": "ecosystem_orange_dark",
        "content": "bento_mosaic_dark",
    },
}

_PALETTE_HINTS: List[tuple[str, str]] = [
    ("finance", "business_authority"),
    ("investor", "business_authority"),
    ("fundraising", "business_authority"),
    ("marketing", "energetic"),
    ("brand", "energetic"),
    ("education", "education_charts"),
    ("training", "education_charts"),
    ("health", "modern_wellness"),
    ("medical", "modern_wellness"),
    ("retail", "vibrant_orange_mint"),
    ("sustain", "forest_eco"),
    ("green", "forest_eco"),
    ("architecture", "pure_tech_blue"),
    ("cloud", "pure_tech_blue"),
    ("ai", "pure_tech_blue"),
    ("tech", "pure_tech_blue"),
]

_STYLE_HINTS: List[tuple[str, str]] = [
    ("architecture", "sharp"),
    ("cloud", "sharp"),
    ("workflow", "sharp"),
    ("system", "sharp"),
    ("enterprise", "sharp"),
    ("tech", "sharp"),
    ("premium", "pill"),
    ("luxury", "pill"),
    ("brand", "rounded"),
    ("creative", "rounded"),
    ("training", "soft"),
    ("education", "soft"),
    ("consulting", "soft"),
]

_SECTION_HINT_RE = re.compile(
    r"(section|chapter|part|agenda)\b",
    flags=re.IGNORECASE,
)
_TIMELINE_HINT_RE = re.compile(
    r"(timeline|roadmap|workflow|process|journey|funnel|milestone)",
    flags=re.IGNORECASE,
)
_COMPARE_HINT_RE = re.compile(
    r"(compare|versus|vs\.?|before|after|benchmark)",
    flags=re.IGNORECASE,
)

_SOURCES = [
    "minimax:skills/pptx-generator",
    "minimax:plugins/pptx-plugin",
    "anthropic:skills/pptx",
    "ppt-master",
]

_CONTENT_LAYOUT_ROTATION: List[str] = ["split_2", "grid_3", "grid_4", "asymmetric_2", "timeline"]
_CONTENT_LAYOUT_SET = set(_CONTENT_LAYOUT_ROTATION)
_CONTENT_LAYOUT_MAX_RATIO = 0.5
_CONTENT_LAYOUT_MAX_SPLIT_RATIO = 0.34
_GENERIC_COVER_TEMPLATE_OVERRIDES = {
    "",
    "auto",
    "dashboard_dark",
    "bento_2x2_dark",
    "bento_mosaic_dark",
    "split_media_dark",
}


def _normalize_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _as_bool(value: Any, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _normalize_skill_key(value: Any) -> str:
    text = _normalize_text(value, "").lower()
    text = "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def _dedupe_skills(raw_value: Any) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in _as_list(raw_value):
        skill = _normalize_skill_key(item)
        if not skill or skill in seen:
            continue
        seen.add(skill)
        out.append(skill)
    return out


def _slide_text_blob(slide: Dict[str, Any], deck: Dict[str, Any]) -> str:
    parts: List[str] = [
        _normalize_text(deck.get("title"), ""),
        _normalize_text(deck.get("topic"), ""),
        _normalize_text(slide.get("title"), ""),
        _normalize_text(slide.get("slide_type"), ""),
        _normalize_text(slide.get("layout_grid"), ""),
    ]
    for block in _as_list(slide.get("blocks"))[:10]:
        row = _as_dict(block)
        parts.append(_normalize_text(row.get("block_type") or row.get("type"), ""))
        content = row.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, dict):
            for key in ("title", "body", "text", "label", "caption", "description"):
                parts.append(_normalize_text(content.get(key), ""))
    return " ".join(part for part in parts if part).lower()


def _parse_used_content_layouts(deck: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
    raw = []
    if isinstance(deck.get("used_content_layouts"), list):
        raw = list(deck.get("used_content_layouts") or [])
    elif isinstance(state.get("used_content_layouts"), list):
        raw = list(state.get("used_content_layouts") or [])
    out: List[str] = []
    for item in raw:
        text = _normalize_text(item, "").lower()
        if text in _CONTENT_LAYOUT_SET:
            out.append(text)
    return out


def _content_slide_index(slide: Dict[str, Any], deck: Dict[str, Any], used_layouts: List[str]) -> int:
    for key in ("content_slide_index", "content_index"):
        raw = deck.get(key)
        if raw is None:
            continue
        try:
            return max(0, int(raw))
        except Exception:
            continue
    page_number = int(slide.get("page_number") or 0)
    if page_number > 2:
        # Keep first content pages more diverse when page_number exists.
        return max(0, page_number - 2)
    return len(used_layouts)


def _pick_content_layout(current: str, slide: Dict[str, Any], deck: Dict[str, Any], state: Dict[str, Any]) -> str:
    locked = _as_bool(state.get("layout_lock"), False) or _as_bool(slide.get("layout_lock"), False)
    if locked and current:
        return current

    used_layouts = _parse_used_content_layouts(deck, state)
    idx = _content_slide_index(slide, deck, used_layouts)
    counts: Dict[str, int] = {}
    for item in used_layouts:
        counts[item] = counts.get(item, 0) + 1

    ordered_candidates: List[str] = []
    if current and current in _CONTENT_LAYOUT_SET:
        ordered_candidates.append(current)
    for step in range(len(_CONTENT_LAYOUT_ROTATION)):
        ordered_candidates.append(_CONTENT_LAYOUT_ROTATION[(idx + step) % len(_CONTENT_LAYOUT_ROTATION)])
    deduped: List[str] = []
    for candidate in ordered_candidates:
        if candidate not in _CONTENT_LAYOUT_SET:
            continue
        if candidate in deduped:
            continue
        deduped.append(candidate)

    def _violates_budget(candidate: str) -> bool:
        if used_layouts and candidate == used_layouts[-1]:
            return True
        ratio = counts.get(candidate, 0) / max(1, len(used_layouts))
        if ratio >= _CONTENT_LAYOUT_MAX_RATIO:
            return True
        if candidate == "split_2":
            split_ratio = counts.get("split_2", 0) / max(1, len(used_layouts))
            if split_ratio >= _CONTENT_LAYOUT_MAX_SPLIT_RATIO:
                return True
        return False

    for candidate in deduped:
        if not _violates_budget(candidate):
            return candidate
    for candidate in deduped:
        if not (used_layouts and candidate == used_layouts[-1]):
            return candidate
    return deduped[0] if deduped else "grid_3"


def _page_skill_directives(slide_type: str, layout_grid: str, render_path: str) -> List[str]:
    slide = _normalize_text(slide_type, "content").lower()
    layout = _normalize_text(layout_grid, "split_2").lower()
    path = _normalize_text(render_path, "pptxgenjs").lower()
    directives: List[str] = [
        "Only one title area is allowed at the top of the slide.",
        "Never emit prefixes like 补充要点: or Supporting point:.",
    ]
    if slide == "cover":
        directives.extend(
            [
                "Use one H1 title and one subtitle block only.",
                "Subtitle must be concise: <= 2 lines.",
                "Avoid oversized decorative rounded rectangles as dominant visual blocks.",
            ]
        )
    elif slide in {"summary", "toc", "divider"}:
        directives.extend(
            [
                "Use concise bullets (3-5) and keep each bullet short.",
                "Avoid mixed visual themes within the same slide.",
            ]
        )
    else:
        directives.extend(
            [
                "Bullet count should be <= 4 for dense layouts.",
                "Each bullet should stay within one short sentence.",
                "Prefer layout diversity across consecutive content slides.",
            ]
        )
        if layout in {"split_2", "asymmetric_2"}:
            directives.append("When using left-right layout, ensure text area is not overloaded.")
        if layout == "timeline":
            directives.append("Timeline slides should keep 3-5 milestones with balanced spacing.")
    if path in {"svg", "png_fallback"}:
        directives.append("SVG visuals must remain semantic and avoid decorative noise.")
    return directives

def _text_constraints(slide_type: str, layout_grid: str) -> Dict[str, Any]:
    slide = _normalize_text(slide_type, "content").lower()
    layout = _normalize_text(layout_grid, "split_2").lower()
    if slide == "cover":
        return {
            "subtitle_max_lines": 2,
            "subtitle_max_chars_cjk": 80,
            "subtitle_min_font_pt": 13,
            "min_title_font_pt": 30,
        }
    if slide in {"summary", "toc", "divider"}:
        return {
            "bullet_max_items": 5,
            "bullet_max_chars_cjk": 30,
            "min_body_font_pt": 11,
            "min_title_font_pt": 20,
            "bullet_auto_split": True,
        }
    if layout in {"split_2", "asymmetric_2"}:
        return {
            "bullet_max_items": 4,
            "bullet_max_chars_cjk": 26,
            "min_body_font_pt": 11,
            "min_title_font_pt": 20,
            "bullet_auto_split": True,
        }
    if layout == "timeline":
        return {
            "bullet_max_items": 5,
            "bullet_max_chars_cjk": 24,
            "min_body_font_pt": 11,
            "min_title_font_pt": 20,
            "bullet_auto_split": True,
        }
    return {
        "bullet_max_items": 5,
        "bullet_max_chars_cjk": 30,
        "min_body_font_pt": 11,
        "min_title_font_pt": 20,
        "bullet_auto_split": True,
    }
def _image_policy(slide_type: str, layout_grid: str) -> Dict[str, Any]:
    slide = _normalize_text(slide_type, "content").lower()
    layout = _normalize_text(layout_grid, "split_2").lower()
    return {
        "prefer_real_stock_images": slide == "content",
        "allow_abstract_svg_illustration": layout in {"timeline"} or slide in {"divider"},
        "cross_slide_duplicate_policy": "strict_url_and_subject_diversity",
    }


def _infer_slide_type(slide: Dict[str, Any], deck: Dict[str, Any], state: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        state.get("slide_type")
        or slide.get("slide_type")
        or slide.get("page_type")
        or slide.get("subtype"),
        "",
    ).lower()
    if explicit in {"cover", "toc", "divider", "section", "summary", "content"}:
        return "divider" if explicit == "section" else explicit

    page_number = int(slide.get("page_number") or 0)
    total_slides = int(deck.get("total_slides") or 0)
    if page_number <= 1:
        return "cover"
    if total_slides > 0 and page_number >= total_slides:
        return "summary"
    if total_slides >= 6 and page_number == 2:
        return "toc"
    if _SECTION_HINT_RE.search(_slide_text_blob(slide, deck)):
        return "divider"
    return "content"


def _infer_layout(slide_type: str, slide: Dict[str, Any], deck: Dict[str, Any], state: Dict[str, Any]) -> str:
    current = _normalize_text(state.get("layout_grid") or slide.get("layout_grid") or slide.get("layout"), "").lower()
    if slide_type == "content":
        return _pick_content_layout(current, slide, deck, state)
    if current:
        return current
    if slide_type in _DEFAULT_LAYOUT_BY_SLIDE_TYPE:
        return _DEFAULT_LAYOUT_BY_SLIDE_TYPE[slide_type]
    blob = _slide_text_blob(slide, deck)
    if _TIMELINE_HINT_RE.search(blob):
        return "timeline"
    if _COMPARE_HINT_RE.search(blob):
        return "split_2"
    return "split_2"


def _infer_render_path(
    slide_type: str,
    layout_grid: str,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    state: Dict[str, Any],
) -> str:
    current = _normalize_text(state.get("render_path") or slide.get("render_path"), "").lower()
    if current in {"pptxgenjs", "svg", "png_fallback"}:
        return current
    # Keep svg/png as explicit opt-in; default path should remain editable and stable.
    return "pptxgenjs"


def _choose_palette(deck: Dict[str, Any], slide: Dict[str, Any], state: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        state.get("palette_key") or slide.get("palette_key") or deck.get("palette_key"),
        "",
    )
    if explicit and explicit.lower() != "auto":
        return explicit
    blob = _slide_text_blob(slide, deck)
    for hint, palette in _PALETTE_HINTS:
        if hint in blob:
            return palette
    return "platinum_white_gold"


def _choose_style(deck: Dict[str, Any], slide: Dict[str, Any], state: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        state.get("style_variant")
        or slide.get("style_variant")
        or slide.get("style")
        or deck.get("style_variant")
        or deck.get("style"),
        "",
    ).lower()
    if explicit in {"sharp", "soft", "rounded", "pill"}:
        return explicit
    blob = _slide_text_blob(slide, deck)
    for hint, style in _STYLE_HINTS:
        if hint in blob:
            return style
    return "soft"


def _choose_template_family(
    slide_type: str,
    style_variant: str,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    state: Dict[str, Any],
) -> str:
    locked = _as_bool(state.get("template_lock"), False) or _as_bool(slide.get("template_lock"), False)
    explicit = _normalize_text(
        state.get("template_family")
        or slide.get("template_family")
        or slide.get("template_id")
        or deck.get("template_family"),
        "",
    ).lower()
    mapping = _STYLE_TEMPLATE_BY_TYPE.get(style_variant, _STYLE_TEMPLATE_BY_TYPE["soft"])
    if slide_type == "cover" and not locked:
        if explicit in _GENERIC_COVER_TEMPLATE_OVERRIDES:
            return mapping.get("cover", "hero_dark")
    if explicit and explicit != "auto":
        return explicit
    return mapping.get(slide_type, mapping.get("content", "dashboard_dark"))


def _choose_skill_profile(slide_type: str, template_family: str, state: Dict[str, Any]) -> str:
    explicit = _normalize_text(state.get("skill_profile"), "").lower()
    if explicit and explicit != "auto":
        return explicit
    family = _normalize_text(template_family, "").lower()
    if slide_type == "cover":
        return "cover"
    if slide_type == "toc":
        return "toc"
    if slide_type in {"divider"}:
        return "section-divider"
    if slide_type == "summary":
        return "summary"
    if "architecture" in family or "blueprint" in family:
        return "architecture"
    if "dashboard" in family:
        return "data-story"
    if "consulting" in family:
        return "consulting"
    return "general-content"


def _agent_type_for_slide_type(slide_type: str) -> str:
    return _AGENT_BY_SLIDE_TYPE.get(slide_type, "content-page-generator")


def _recommended_skills(*, slide_type: str, render_path: str, requested_skills: List[str], deck: Dict[str, Any]) -> List[str]:
    skills: List[str] = ["slide-making-skill", "design-style-skill", "ppt-orchestra-skill"]
    template_family = _normalize_text(deck.get("template_family"), "").lower()
    if template_family and template_family not in {"auto"}:
        skills.append("ppt-editing-skill")
    if slide_type in {"cover", "toc", "summary", "divider"}:
        skills.append("color-font-skill")
    if render_path in {"svg", "png_fallback"}:
        skills.append("pptx")
    skills.extend(requested_skills)
    return _dedupe_skills(skills)


def _build_skill_row(skill: str, state: Dict[str, Any], requested_skills: List[str], slide: Dict[str, Any], deck: Dict[str, Any]) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
    note = ""

    slide_type = _normalize_text(state.get("slide_type"), "content").lower()
    layout_grid = _normalize_text(state.get("layout_grid"), "split_2").lower()
    render_path = _normalize_text(state.get("render_path"), "pptxgenjs").lower()
    style_variant = _normalize_text(state.get("style_variant"), "soft").lower()
    palette_key = _normalize_text(state.get("palette_key"), "platinum_white_gold")
    template_family = _normalize_text(state.get("template_family"), "dashboard_dark")
    skill_profile = _normalize_text(state.get("skill_profile"), "general-content")

    if skill == "ppt-orchestra-skill":
        patch.update(
            {
                "slide_type": slide_type,
                "layout_grid": layout_grid,
                "render_path": render_path,
                "agent_type": _agent_type_for_slide_type(slide_type),
            }
        )
        outputs["recommended_load_skills"] = _recommended_skills(
            slide_type=slide_type,
            render_path=render_path,
            requested_skills=requested_skills,
            deck=deck,
        )
        outputs["planning_mode"] = "skill-first"
        outputs["page_skill_directives"] = _page_skill_directives(slide_type, layout_grid, render_path)
        outputs["page_design_intent"] = (
            f"{slide_type} slide using {layout_grid} layout with {render_path} render path; "
            "prioritize readability, single-title hierarchy, and visual consistency."
        )
    elif skill == "slide-making-skill":
        patch.update(
            {
                "layout_grid": layout_grid,
                "render_path": render_path,
                "agent_type": _agent_type_for_slide_type(slide_type),
            }
        )
        outputs["theme_contract"] = {
            "keys": ["primary", "secondary", "accent", "light", "bg"],
            "layout_16x9": True,
        }
        outputs["text_constraints"] = _text_constraints(slide_type, layout_grid)
        outputs["image_policy"] = _image_policy(slide_type, layout_grid)
        if slide_type != "cover":
            outputs["page_badge_required"] = True
    elif skill == "design-style-skill":
        patch.update(
            {
                "style_variant": style_variant,
                "template_family": template_family,
                "skill_profile": skill_profile,
            }
        )
        outputs["style_recipe"] = style_variant
    elif skill == "color-font-skill":
        patch["palette_key"] = palette_key
        outputs["font_pair"] = {"en": "Arial", "zh": "Microsoft YaHei"}
    elif skill == "ppt-editing-skill":
        patch["skill_profile"] = "template-edit"
        outputs["template_edit_pipeline"] = "unpack->xml-edit->clean->pack"
        outputs["template_edit_engine"] = "xml_with_python_pptx_fallback"
        outputs["placeholder_strategy"] = "markitdown+token-replace"
    elif skill == "pptx":
        blob = _slide_text_blob(slide, deck)
        if render_path == "pptxgenjs" and _TIMELINE_HINT_RE.search(blob):
            patch["render_path"] = "svg"
        outputs["qa_pipeline"] = "markitdown+ooxml"
    else:
        note = "unknown_skill_passthrough"

    status = "applied" if patch or outputs else "noop"
    if status == "noop" and not note:
        note = "noop"
    return {
        "skill": skill,
        "status": status,
        "patch": patch,
        "outputs": outputs,
        "note": note,
        "source": "direct_skill_runtime",
    }


def execute_direct_skill_runtime(payload: Dict[str, Any]) -> Dict[str, Any]:
    req = _as_dict(payload)
    requested_skills = _dedupe_skills(req.get("requested_skills"))
    slide = _as_dict(req.get("slide"))
    deck = _as_dict(req.get("deck"))
    state = _as_dict(req.get("state"))

    if not requested_skills:
        requested_skills = ["ppt-orchestra-skill", "slide-making-skill", "design-style-skill"]

    resolved_state: Dict[str, Any] = {}
    resolved_state["slide_type"] = _infer_slide_type(slide, deck, state)
    resolved_state["layout_grid"] = _infer_layout(resolved_state["slide_type"], slide, deck, state)
    resolved_state["render_path"] = _infer_render_path(
        resolved_state["slide_type"],
        resolved_state["layout_grid"],
        slide,
        deck,
        state,
    )
    resolved_state["style_variant"] = _choose_style(deck, slide, state)
    resolved_state["palette_key"] = _choose_palette(deck, slide, state)
    resolved_state["template_family"] = _choose_template_family(
        resolved_state["slide_type"],
        resolved_state["style_variant"],
        slide,
        deck,
        state,
    )
    resolved_state["skill_profile"] = _choose_skill_profile(
        resolved_state["slide_type"],
        resolved_state["template_family"],
        state,
    )

    results: List[Dict[str, Any]] = []
    merged_patch: Dict[str, Any] = {}
    aggregated_load_skills: List[str] = []
    aggregated_page_skill_directives: List[str] = []
    aggregated_text_constraints: Dict[str, Any] = {}
    aggregated_image_policy: Dict[str, Any] = {}
    page_design_intent = ""

    for skill in requested_skills:
        row = _build_skill_row(skill, resolved_state, requested_skills, slide, deck)
        results.append(row)
        row_patch = _as_dict(row.get("patch"))
        if row_patch:
            merged_patch.update(row_patch)
            resolved_state.update(row_patch)
        outputs = _as_dict(row.get("outputs"))
        if isinstance(outputs.get("recommended_load_skills"), list):
            aggregated_load_skills.extend([str(item or "") for item in outputs.get("recommended_load_skills") or []])
        if isinstance(outputs.get("page_skill_directives"), list):
            aggregated_page_skill_directives.extend(
                [str(item or "").strip() for item in outputs.get("page_skill_directives") or [] if str(item or "").strip()]
            )
        if isinstance(outputs.get("text_constraints"), dict):
            aggregated_text_constraints.update(outputs.get("text_constraints") or {})
        if isinstance(outputs.get("image_policy"), dict):
            aggregated_image_policy.update(outputs.get("image_policy") or {})
        if not page_design_intent:
            page_design_intent = _normalize_text(outputs.get("page_design_intent"), "")

    context = {
        "agent_type": _agent_type_for_slide_type(_normalize_text(resolved_state.get("slide_type"), "content").lower()),
        "style_variant": _normalize_text(resolved_state.get("style_variant"), "soft"),
        "palette_key": _normalize_text(resolved_state.get("palette_key"), "platinum_white_gold"),
        "template_family": _normalize_text(resolved_state.get("template_family"), "dashboard_dark"),
        "skill_profile": _normalize_text(resolved_state.get("skill_profile"), "general-content"),
        "recommended_load_skills": _dedupe_skills(aggregated_load_skills),
        "page_skill_directives": list(dict.fromkeys([item for item in aggregated_page_skill_directives if item])),
        "text_constraints": aggregated_text_constraints,
        "image_policy": aggregated_image_policy,
        "page_design_intent": page_design_intent
        or f"{_normalize_text(resolved_state.get('slide_type'), 'content')} page with {_normalize_text(resolved_state.get('layout_grid'), 'split_2')} layout",
        "sources": list(_SOURCES),
    }
    if not context["recommended_load_skills"]:
        context["recommended_load_skills"] = _recommended_skills(
            slide_type=_normalize_text(resolved_state.get("slide_type"), "content").lower(),
            render_path=_normalize_text(resolved_state.get("render_path"), "pptxgenjs").lower(),
            requested_skills=requested_skills,
            deck=deck,
        )
    if not context.get("page_skill_directives"):
        context["page_skill_directives"] = _page_skill_directives(
            _normalize_text(resolved_state.get("slide_type"), "content"),
            _normalize_text(resolved_state.get("layout_grid"), "split_2"),
            _normalize_text(resolved_state.get("render_path"), "pptxgenjs"),
        )
    if not context.get("text_constraints"):
        context["text_constraints"] = _text_constraints(
            _normalize_text(resolved_state.get("slide_type"), "content"),
            _normalize_text(resolved_state.get("layout_grid"), "split_2"),
        )
    if not context.get("image_policy"):
        context["image_policy"] = _image_policy(
            _normalize_text(resolved_state.get("slide_type"), "content"),
            _normalize_text(resolved_state.get("layout_grid"), "split_2"),
        )

    merged_patch.setdefault("agent_type", context["agent_type"])
    merged_patch.setdefault("style_variant", context["style_variant"])
    merged_patch.setdefault("palette_key", context["palette_key"])
    merged_patch.setdefault("template_family", context["template_family"])
    merged_patch.setdefault("skill_profile", context["skill_profile"])
    merged_patch.setdefault("load_skills", context["recommended_load_skills"])

    return {
        "version": 1,
        "results": results,
        "patch": merged_patch,
        "context": context,
        "note": "ppt_direct_skill_runtime_ok",
    }


def _read_stdin_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception:
        parsed = {}
    return _as_dict(parsed)


def _write_json_stdout(payload: Dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(raw.encode("utf-8", errors="replace"))
    else:
        sys.stdout.write(raw)
    sys.stdout.flush()


def main() -> int:
    payload = _read_stdin_payload()
    output = execute_direct_skill_runtime(payload)
    _write_json_stdout(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

