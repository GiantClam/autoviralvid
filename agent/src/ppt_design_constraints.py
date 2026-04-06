"""Deterministic pre-render design constraint checks for PPT payloads."""

from __future__ import annotations

import re
from typing import Any, Dict, List


_GENERIC_COPY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^(先说明|再交代|最后解释|梳理围绕|拆解|说明|指出|讨论)",
        r"(提炼当前页最关键的三个信息点|把核心概念、证据与结论组织成清晰结构)",
        r"(避免只罗列标题|突出解释关系与因果逻辑)",
    )
]


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_hex_color(value: Any) -> str:
    text = _normalize_text(value).lstrip("#")
    if len(text) == 3 and all(ch in "0123456789abcdefABCDEF" for ch in text):
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        return ""
    return text.upper()


def _is_neutral_color(hex_color: str) -> bool:
    normalized = _normalize_hex_color(hex_color)
    if not normalized:
        return True
    r = int(normalized[0:2], 16)
    g = int(normalized[2:4], 16)
    b = int(normalized[4:6], 16)
    return max(r, g, b) - min(r, g, b) <= 18


def _to_float(value: Any) -> float | None:
    try:
        num = float(value)
    except Exception:
        return None
    if num <= 0:
        return None
    return num


def _style_dicts(slide: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for element in slide.get("elements") or []:
        if isinstance(element, dict):
            style = element.get("style")
            if isinstance(style, dict):
                rows.append(style)
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        style = block.get("style")
        if isinstance(style, dict):
            rows.append(style)
        content = block.get("content")
        if isinstance(content, dict):
            content_style = content.get("style")
            if isinstance(content_style, dict):
                rows.append(content_style)
    theme = slide.get("theme")
    if isinstance(theme, dict):
        rows.append(theme)
    return rows


def _block_text(block: Dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        for key in ("title", "body", "text", "label", "caption", "description", "summary"):
            value = _normalize_text(content.get(key))
            if value:
                return value
    data = block.get("data") if isinstance(block.get("data"), dict) else {}
    for key in ("title", "label", "description", "text"):
        value = _normalize_text(data.get(key))
        if value:
            return value
    return ""


def _is_terminal(slide: Dict[str, Any]) -> bool:
    slide_type = _normalize_text(slide.get("slide_type") or slide.get("page_type") or "").lower()
    return slide_type in {"cover", "toc", "summary", "divider", "hero_1", "section"}


def _check_terminal_title_echo(slide: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    title = _normalize_text(slide.get("title"))
    if not title:
        return issues
    normalized_title = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", title.lower())
    if not normalized_title:
        return issues
    seen = 0
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        text = _block_text(block)
        key = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", text.lower())
        if key and key == normalized_title:
            seen += 1
    if seen > 1:
        issues.append("terminal_title_echo")
    return issues


def _check_middle_hero_layout(slide: Dict[str, Any]) -> List[str]:
    if _is_terminal(slide):
        return []
    layout = _normalize_text(slide.get("layout_grid") or slide.get("layout") or "").lower()
    if layout == "hero_1":
        return ["middle_slide_hero_layout"]
    return []


def _check_generic_copy(slide: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        block_type = _normalize_text(block.get("block_type") or block.get("type")).lower()
        if block_type not in {"body", "list", "quote", "comparison"}:
            continue
        text = _block_text(block)
        if text and any(pattern.search(text) for pattern in _GENERIC_COPY_PATTERNS):
            issues.append("generic_support_copy")
            break
    return issues


def _check_three_color_rule(slide: Dict[str, Any]) -> List[str]:
    colors: set[str] = set()
    for style in _style_dicts(slide):
        for key in ("color", "backgroundColor", "borderColor", "accentColor", "fill", "stroke"):
            normalized = _normalize_hex_color(style.get(key))
            if normalized and not _is_neutral_color(normalized):
                colors.add(normalized)
    if len(colors) > 3:
        return ["three_color_violation"]
    return []


def _check_whitespace_ratio(slide: Dict[str, Any]) -> List[str]:
    rows = [row for row in (slide.get("elements") or []) if isinstance(row, dict)]
    if not rows:
        return []
    widths = [
        _to_float(row.get("width"))
        for row in rows
        if _to_float(row.get("width")) is not None and _to_float(row.get("height")) is not None
    ]
    heights = [
        _to_float(row.get("height"))
        for row in rows
        if _to_float(row.get("width")) is not None and _to_float(row.get("height")) is not None
    ]
    if not widths or not heights:
        return []
    pixel_like = max(widths) > 50 or max(heights) > 50
    canvas_area = float(1920 * 1080) if pixel_like else float(10 * 5.625)
    occupied_area = 0.0
    for row in rows:
        width = _to_float(row.get("width"))
        height = _to_float(row.get("height"))
        if width is None or height is None:
            continue
        occupied_area += width * height
    if occupied_area <= 0 or canvas_area <= 0:
        return []
    whitespace_ratio = max(0.0, min(1.0, (canvas_area - occupied_area) / canvas_area))
    if whitespace_ratio < 0.15:
        return ["insufficient_whitespace"]
    return []


def _check_font_size_constraints(slide: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for element in slide.get("elements") or []:
        if not isinstance(element, dict):
            continue
        style = element.get("style") if isinstance(element.get("style"), dict) else {}
        font_size = _to_float(style.get("fontSize"))
        if font_size is None:
            continue
        is_title = bool(element.get("is_title")) or _normalize_text(element.get("type")).lower() in {"title", "headline"}
        if is_title and font_size < 24:
            issues.append("title_font_too_small")
        if not is_title and _normalize_text(element.get("type")).lower() == "text" and font_size < 18:
            issues.append("body_font_too_small")
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        block_type = _normalize_text(block.get("block_type") or block.get("type")).lower()
        style = block.get("style") if isinstance(block.get("style"), dict) else {}
        content = block.get("content") if isinstance(block.get("content"), dict) else {}
        font_size = _to_float(style.get("fontSize")) or _to_float(content.get("fontSize"))
        if font_size is None:
            continue
        if block_type in {"title", "subtitle"} and font_size < 24:
            issues.append("title_font_too_small")
        if block_type in {"body", "list", "quote", "comparison", "kpi", "chart"} and font_size < 18:
            issues.append("body_font_too_small")
    deduped: List[str] = []
    for issue in issues:
        if issue not in deduped:
            deduped.append(issue)
    return deduped


def _check_single_decision_source(render_payload: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    decision = render_payload.get("design_decision_v1") if isinstance(render_payload.get("design_decision_v1"), dict) else {}
    deck = decision.get("deck") if isinstance(decision.get("deck"), dict) else {}
    for key in ("style_variant", "palette_key", "theme_recipe", "tone"):
        payload_value = _normalize_text(render_payload.get(key)).lower()
        deck_value = _normalize_text(deck.get(key)).lower()
        if payload_value and deck_value and payload_value != deck_value:
            issues.append(f"decision_mismatch:{key}")
    return issues


def validate_render_payload_design(render_payload: Dict[str, Any]) -> Dict[str, Any]:
    slides = render_payload.get("slides") if isinstance(render_payload.get("slides"), list) else []
    deck_issues = _check_single_decision_source(render_payload)
    slide_rows: List[Dict[str, Any]] = []
    for idx, raw_slide in enumerate(slides):
        if not isinstance(raw_slide, dict):
            continue
        slide_id = _normalize_text(raw_slide.get("slide_id") or raw_slide.get("id") or f"slide-{idx + 1}")
        issues = [
            *_check_middle_hero_layout(raw_slide),
            *_check_generic_copy(raw_slide),
            *_check_three_color_rule(raw_slide),
            *_check_whitespace_ratio(raw_slide),
            *_check_font_size_constraints(raw_slide),
            *(_check_terminal_title_echo(raw_slide) if _is_terminal(raw_slide) else []),
        ]
        slide_rows.append({"slide_id": slide_id, "issues": issues})
    all_slide_issues = [issue for row in slide_rows for issue in row.get("issues") or []]
    return {
        "passed": not deck_issues and not all_slide_issues,
        "deck_issues": deck_issues,
        "slides": slide_rows,
        "issue_count": len(deck_issues) + len(all_slide_issues),
    }
