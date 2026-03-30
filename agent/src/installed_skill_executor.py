"""Installed skill executor for PPT planning/runtime patches.

The executor is called by ``src.ppt_subagent_executor`` (stdin/stdout JSON),
but it is also used directly by ``src.ppt_service`` in the main export path.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
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
    ("绉戞妧", "pure_tech_blue"),
    ("鏋舵瀯", "pure_tech_blue"),
    ("娴佺▼", "education_charts"),
    ("鍩硅", "education_charts"),
    ("鏁欒偛", "education_charts"),
    ("鍖荤枟", "modern_wellness"),
    ("鍝佺墝", "energetic"),
    ("钀ラ攢", "energetic"),
    ("铻嶈祫", "business_authority"),
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
    ("??", "sharp"),
    ("??", "sharp"),
    ("??", "sharp"),
    ("??", "rounded"),
    ("??", "soft"),
]

_SECTION_HINT_RE = re.compile(
    r"(section|chapter|part|agenda|toc|directory|phase)\b",
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

_GENERIC_COVER_TEMPLATE_OVERRIDES = {
    "",
    "auto",
    "dashboard_dark",
    "bento_2x2_dark",
    "bento_mosaic_dark",
    "split_media_dark",
}
_CONTENT_LAYOUT_ROTATION: List[str] = ["split_2", "grid_3", "grid_4", "asymmetric_2", "timeline"]
_CONTENT_LAYOUT_SET = set(_CONTENT_LAYOUT_ROTATION)
_CONTENT_LAYOUT_MAX_RATIO = 0.5
_CONTENT_LAYOUT_MAX_SPLIT_RATIO = 0.34


def _normalize_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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


def _dedupe_text_list(raw_values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in raw_values:
        text = _normalize_text(item, "")
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _env_flag(name: str, default: str = "false") -> bool:
    text = _normalize_text(os.getenv(name, default), default).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _as_bool(value: Any, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _parse_command_args(raw_value: str) -> List[str]:
    text = _normalize_text(raw_value, "")
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [_normalize_text(item, "") for item in parsed if _normalize_text(item, "")]
    except Exception:
        pass
    try:
        return [item for item in shlex.split(text, posix=False) if _normalize_text(item, "")]
    except Exception:
        return [item for item in text.split() if _normalize_text(item, "")]


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    text = _normalize_text(raw_text, "")
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    for line in reversed(text.splitlines()):
        row = line.strip()
        if not row.startswith("{"):
            continue
        try:
            parsed = json.loads(row)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _invoke_direct_skill_runtime(
    *,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    requested_skills: List[str],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    if not _env_flag("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "true"):
        return {"enabled": False, "reason": "direct_skill_runtime_disabled", "row": {}}

    bin_name = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_BIN", ""), "uv")

    args = _parse_command_args(os.getenv("PPT_DIRECT_SKILL_RUNTIME_ARGS", ""))
    if not args:
        args = ["run", "python", "-m", "src.ppt_direct_skill_runtime"]
    timeout_sec_raw = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_TIMEOUT_SEC", "25"), "25")
    try:
        timeout_sec = max(5, int(timeout_sec_raw))
    except Exception:
        timeout_sec = 25
    cwd = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_CWD", ""), "")
    if not cwd:
        cwd = str(Path(__file__).resolve().parents[1])
    payload = {
        "version": 1,
        "requested_skills": requested_skills,
        "slide": slide,
        "deck": deck,
        "state": state,
        "sources": list(_SOURCES),
    }

    try:
        proc = subprocess.run(
            [bin_name, *args],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
            cwd=cwd,
        )
    except Exception as exc:
        return {
            "enabled": True,
            "reason": f"direct_skill_runtime_failed:{_normalize_text(str(exc), 'invoke_failed')}",
            "parsed": {},
        }

    if int(proc.returncode) != 0:
        detail = _normalize_text(proc.stderr, "") or _normalize_text(proc.stdout, "") or f"exit_{proc.returncode}"
        return {
            "enabled": True,
            "reason": f"direct_skill_runtime_nonzero:{detail[:180]}",
            "parsed": {},
        }

    parsed = _parse_json_object(_normalize_text(proc.stdout, ""))
    if not parsed:
        return {"enabled": True, "reason": "direct_skill_runtime_invalid_output", "parsed": {}}
    return {"enabled": True, "reason": "", "parsed": parsed}


def _normalize_runtime_row(raw_row: Dict[str, Any], default_skill: str = "") -> Dict[str, Any]:
    row = _as_dict(raw_row)
    skill = _normalize_skill_key(row.get("skill") or default_skill)
    patch = _as_dict(row.get("patch") or row.get("slide_patch"))
    outputs = _as_dict(row.get("outputs") or row.get("context"))
    status = _normalize_text(row.get("status"), "").lower()
    if status not in {"applied", "noop", "error"}:
        status = "applied" if patch or outputs else "noop"
    note = _normalize_text(row.get("note"), "")
    return {
        "skill": skill or _normalize_text(default_skill, ""),
        "status": status,
        "patch": patch,
        "outputs": outputs,
        "note": note or "direct_skill_runtime",
        "source": "direct_skill_runtime",
    }


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


def _parse_used_content_layouts(deck: Dict[str, Any]) -> List[str]:
    raw = deck.get("used_content_layouts") if isinstance(deck.get("used_content_layouts"), list) else []
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
        return max(0, page_number - 2)
    return len(used_layouts)


def _pick_content_layout(current: str, slide: Dict[str, Any], deck: Dict[str, Any]) -> str:
    locked = _as_bool(slide.get("layout_lock"), False)
    if locked and current:
        return current

    used_layouts = _parse_used_content_layouts(deck)
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


def _infer_slide_type(slide: Dict[str, Any], deck: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        slide.get("slide_type") or slide.get("page_type") or slide.get("subtype"),
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

    blob = _slide_text_blob(slide, deck)
    if _SECTION_HINT_RE.search(blob):
        return "divider"
    return "content"


def _infer_layout(slide_type: str, slide: Dict[str, Any], deck: Dict[str, Any]) -> str:
    current = _normalize_text(slide.get("layout_grid") or slide.get("layout"), "").lower()
    if slide_type == "content":
        return _pick_content_layout(current, slide, deck)
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


def _infer_render_path(slide_type: str, layout_grid: str, slide: Dict[str, Any], deck: Dict[str, Any]) -> str:
    current = _normalize_text(slide.get("render_path"), "").lower()
    if current in {"pptxgenjs", "svg", "png_fallback"}:
        return current
    # Keep svg/png as explicit opt-in to avoid accidental overlay-heavy renders.
    return "pptxgenjs"


def _choose_palette(deck: Dict[str, Any], slide: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        slide.get("palette_key") or deck.get("palette_key"),
        "",
    )
    if explicit and explicit.lower() != "auto":
        return explicit
    blob = _slide_text_blob(slide, deck)
    for hint, palette in _PALETTE_HINTS:
        if hint in blob:
            return palette
    return "platinum_white_gold"


def _choose_style(deck: Dict[str, Any], slide: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        slide.get("style_variant")
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


def _choose_template_family(slide_type: str, style_variant: str, slide: Dict[str, Any]) -> str:
    locked = _as_bool(slide.get("template_lock"), False)
    explicit = _normalize_text(
        slide.get("template_family") or slide.get("template_id"),
        "",
    ).lower()
    mapping = _STYLE_TEMPLATE_BY_TYPE.get(style_variant, _STYLE_TEMPLATE_BY_TYPE["soft"])
    if slide_type == "cover" and not locked:
        if explicit in _GENERIC_COVER_TEMPLATE_OVERRIDES:
            return mapping.get("cover", "hero_dark")
    if explicit and explicit != "auto":
        return explicit
    return mapping.get(slide_type, mapping.get("content", "dashboard_dark"))


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


def _choose_skill_profile(slide_type: str, template_family: str) -> str:
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


def _recommended_skills(
    *,
    slide_type: str,
    render_path: str,
    requested_skills: List[str],
    deck: Dict[str, Any] | None = None,
) -> List[str]:
    skills: List[str] = ["slide-making-skill", "design-style-skill", "ppt-orchestra-skill"]
    template_family = _normalize_text(deck.get("template_family") if isinstance(deck, dict) else "", "").lower()
    if template_family and template_family not in {"auto"}:
        skills.append("ppt-editing-skill")
    if slide_type in {"cover", "toc", "summary", "divider"}:
        skills.append("color-font-skill")
    if render_path in {"svg", "png_fallback"}:
        skills.append("pptx")
    skills.extend(requested_skills)
    return _dedupe_skills(skills)


def _build_skill_row(
    *,
    skill: str,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    requested_skills: List[str],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
    note = ""

    slide_type = _normalize_text(state.get("slide_type"), "content").lower()
    layout_grid = _normalize_text(state.get("layout_grid"), "split_2").lower()
    render_path = _normalize_text(state.get("render_path"), "pptxgenjs").lower()
    style_variant = _normalize_text(state.get("style_variant"), "soft").lower()
    palette_key = _normalize_text(state.get("palette_key"), "platinum_white_gold")
    template_family = _normalize_text(state.get("template_family"), "")

    if skill == "ppt-orchestra-skill":
        patch["slide_type"] = slide_type
        patch["layout_grid"] = layout_grid
        patch["render_path"] = render_path
        patch["agent_type"] = _agent_type_for_slide_type(slide_type)
        outputs["recommended_load_skills"] = _recommended_skills(
            slide_type=slide_type,
            render_path=render_path,
            requested_skills=requested_skills,
            deck=deck,
        )
        outputs["page_skill_directives"] = _page_skill_directives(slide_type, layout_grid, render_path)
        outputs["page_design_intent"] = (
            f"{slide_type} slide using {layout_grid} layout with {render_path} render path; "
            "prioritize readability, single-title hierarchy, and visual consistency."
        )
    elif skill == "slide-making-skill":
        patch["layout_grid"] = layout_grid
        patch["render_path"] = render_path
        patch["agent_type"] = _agent_type_for_slide_type(slide_type)
        outputs["theme_contract"] = {
            "keys": ["primary", "secondary", "accent", "light", "bg"],
            "layout_16x9": True,
        }
        outputs["text_constraints"] = _text_constraints(slide_type, layout_grid)
        outputs["image_policy"] = _image_policy(slide_type, layout_grid)
        if slide_type != "cover":
            outputs["page_badge_required"] = True
    elif skill == "design-style-skill":
        patch["style_variant"] = style_variant
        patch["template_family"] = template_family
        patch["skill_profile"] = _normalize_text(state.get("skill_profile"), "general-content")
        outputs["style_recipe"] = style_variant
    elif skill == "color-font-skill":
        patch["palette_key"] = palette_key
        outputs["font_pair"] = {
            "en": "Arial",
            "zh": "Microsoft YaHei",
        }
    elif skill == "ppt-editing-skill":
        outputs["template_edit_pipeline"] = "unpack->xml-edit->clean->pack"
        outputs["template_edit_engine"] = "xml_with_python_pptx_fallback"
        outputs["placeholder_strategy"] = "markitdown+token-replace"
        patch["skill_profile"] = "template-edit"
    elif skill == "pptx":
        if render_path == "pptxgenjs":
            blob = _slide_text_blob(slide, deck)
            if _TIMELINE_HINT_RE.search(blob):
                patch["render_path"] = "svg"
        outputs["qa_pipeline"] = "markitdown+ooxml"
    else:
        note = "unknown_skill_passthrough"

    status = "applied" if patch or outputs else "noop"
    if not note and status == "noop":
        note = "noop"
    return {
        "skill": skill,
        "status": status,
        "patch": patch,
        "outputs": outputs,
        "note": note,
        "source": "builtin_fallback",
    }


def execute_installed_skill_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    request = _as_dict(payload)
    requested_skills = _dedupe_skills(request.get("requested_skills"))
    slide = _as_dict(request.get("slide"))
    deck = _as_dict(request.get("deck"))
    if not deck:
        deck = _as_dict(request.get("context"))

    slide_type = _infer_slide_type(slide, deck)
    layout_grid = _infer_layout(slide_type, slide, deck)
    render_path = _infer_render_path(slide_type, layout_grid, slide, deck)
    style_variant = _choose_style(deck, slide)
    palette_key = _choose_palette(deck, slide)
    template_family = _choose_template_family(slide_type, style_variant, slide)
    skill_profile = _choose_skill_profile(slide_type, template_family)

    state: Dict[str, Any] = {
        "slide_type": slide_type,
        "layout_grid": layout_grid,
        "render_path": render_path,
        "style_variant": style_variant,
        "palette_key": palette_key,
        "template_family": template_family,
        "skill_profile": skill_profile,
    }

    require_direct_runtime = _env_flag("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "true")
    direct_runtime = _invoke_direct_skill_runtime(
        slide=slide,
        deck=deck,
        requested_skills=requested_skills,
        state=state,
    )
    direct_parsed = _as_dict(direct_runtime.get("parsed"))
    direct_context = _as_dict(direct_parsed.get("context"))
    direct_rows_raw = direct_parsed.get("results")
    direct_rows: List[Dict[str, Any]] = []
    if isinstance(direct_rows_raw, list):
        for row in direct_rows_raw:
            if not isinstance(row, dict):
                continue
            direct_rows.append(_normalize_runtime_row(row))
    elif direct_parsed:
        # Backward-compatible single-row runtime response.
        default_skill = requested_skills[0] if requested_skills else ""
        direct_rows.append(_normalize_runtime_row(direct_parsed, default_skill=default_skill))

    results: List[Dict[str, Any]] = []
    merged_patch: Dict[str, Any] = {}
    aggregated_load_skills: List[str] = []
    fulfilled_skills: set[str] = set()

    for row in direct_rows:
        skill_key = _normalize_skill_key(row.get("skill"))
        if skill_key:
            fulfilled_skills.add(skill_key)
        row_patch = _as_dict(row.get("patch"))
        if row_patch:
            merged_patch.update(row_patch)
            state.update(row_patch)
        outputs = _as_dict(row.get("outputs"))
        if isinstance(outputs.get("recommended_load_skills"), list):
            aggregated_load_skills.extend(
                [str(item or "") for item in outputs.get("recommended_load_skills") or []]
            )
        results.append(row)

    direct_patch = _as_dict(direct_parsed.get("patch") or direct_parsed.get("slide_patch"))
    if direct_patch:
        merged_patch.update(direct_patch)
        state.update(direct_patch)
    if isinstance(direct_context.get("recommended_load_skills"), list):
        aggregated_load_skills.extend(
            [str(item or "") for item in direct_context.get("recommended_load_skills") or []]
        )

    unresolved_skills: List[str] = [
        skill for skill in requested_skills if _normalize_skill_key(skill) not in fulfilled_skills
    ]
    direct_reason = _normalize_text(direct_runtime.get("reason"), "")
    if require_direct_runtime and (direct_reason or unresolved_skills):
        for skill in unresolved_skills:
            results.append(
                {
                    "skill": skill,
                    "status": "error",
                    "patch": {},
                    "outputs": {},
                    "note": direct_reason or f"direct_skill_runtime_unresolved:{skill}",
                    "source": "direct_skill_runtime",
                }
            )
    else:
        for skill in unresolved_skills:
            row = _build_skill_row(
                skill=skill,
                slide=slide,
                deck=deck,
                requested_skills=requested_skills,
                state=state,
            )
            row_patch = _as_dict(row.get("patch"))
            if row_patch:
                merged_patch.update(row_patch)
                state.update(row_patch)
            outputs = _as_dict(row.get("outputs"))
            if isinstance(outputs.get("recommended_load_skills"), list):
                aggregated_load_skills.extend(
                    [str(item or "") for item in outputs.get("recommended_load_skills") or []]
                )
            results.append(row)

    context = {
        "agent_type": _agent_type_for_slide_type(_normalize_text(state.get("slide_type"), "content").lower()),
        "style_variant": _normalize_text(state.get("style_variant"), "soft"),
        "palette_key": _normalize_text(state.get("palette_key"), "platinum_white_gold"),
        "template_family": _normalize_text(state.get("template_family"), "dashboard_dark"),
        "skill_profile": _normalize_text(state.get("skill_profile"), "general-content"),
        "recommended_load_skills": _dedupe_skills(aggregated_load_skills),
        "page_skill_directives": _page_skill_directives(
            _normalize_text(state.get("slide_type"), "content"),
            _normalize_text(state.get("layout_grid"), "split_2"),
            _normalize_text(state.get("render_path"), "pptxgenjs"),
        ),
        "text_constraints": _text_constraints(
            _normalize_text(state.get("slide_type"), "content"),
            _normalize_text(state.get("layout_grid"), "split_2"),
        ),
        "image_policy": _image_policy(
            _normalize_text(state.get("slide_type"), "content"),
            _normalize_text(state.get("layout_grid"), "split_2"),
        ),
        "page_design_intent": (
            f"{_normalize_text(state.get('slide_type'), 'content')} page with "
            f"{_normalize_text(state.get('layout_grid'), 'split_2')} layout"
        ),
        "sources": list(_SOURCES),
    }
    if _normalize_text(direct_context.get("agent_type"), ""):
        context["agent_type"] = _normalize_text(direct_context.get("agent_type"), context["agent_type"])
    if _normalize_text(direct_context.get("style_variant"), ""):
        context["style_variant"] = _normalize_text(direct_context.get("style_variant"), context["style_variant"])
    if _normalize_text(direct_context.get("palette_key"), ""):
        context["palette_key"] = _normalize_text(direct_context.get("palette_key"), context["palette_key"])
    if _normalize_text(direct_context.get("template_family"), ""):
        context["template_family"] = _normalize_text(direct_context.get("template_family"), context["template_family"])
    if _normalize_text(direct_context.get("skill_profile"), ""):
        context["skill_profile"] = _normalize_text(direct_context.get("skill_profile"), context["skill_profile"])
    if isinstance(direct_context.get("page_skill_directives"), list):
        context["page_skill_directives"] = _dedupe_text_list(
            [str(item or "") for item in direct_context.get("page_skill_directives") or []]
        )
    if isinstance(direct_context.get("text_constraints"), dict):
        context["text_constraints"] = _as_dict(direct_context.get("text_constraints"))
    if isinstance(direct_context.get("image_policy"), dict):
        context["image_policy"] = _as_dict(direct_context.get("image_policy"))
    if _normalize_text(direct_context.get("page_design_intent"), ""):
        context["page_design_intent"] = _normalize_text(
            direct_context.get("page_design_intent"),
            context["page_design_intent"],
        )
    if not context["recommended_load_skills"]:
        context["recommended_load_skills"] = _recommended_skills(
            slide_type=_normalize_text(state.get("slide_type"), "content").lower(),
            render_path=_normalize_text(state.get("render_path"), "pptxgenjs").lower(),
            requested_skills=requested_skills,
            deck=deck,
        )

    if context["agent_type"]:
        merged_patch.setdefault("agent_type", context["agent_type"])
    if context["style_variant"]:
        merged_patch.setdefault("style_variant", context["style_variant"])
    if context["palette_key"]:
        merged_patch.setdefault("palette_key", context["palette_key"])
    if context["template_family"]:
        merged_patch.setdefault("template_family", context["template_family"])
    if context["skill_profile"]:
        merged_patch.setdefault("skill_profile", context["skill_profile"])
    if context["recommended_load_skills"]:
        merged_patch.setdefault("load_skills", context["recommended_load_skills"])

    return {
        "version": 1,
        "results": results,
        "patch": merged_patch,
        "context": context,
        "note": "installed_skill_executor_ok",
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
    output = execute_installed_skill_request(payload)
    _write_json_stdout(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

