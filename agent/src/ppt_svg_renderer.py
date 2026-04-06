"""Deterministic slide-to-SVG renderer used by the DrawingML export path."""

from __future__ import annotations

import html
import re
from typing import Any, Dict, Iterable, List

_HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")
_SVG_TAG_RE = re.compile(r"<svg\b", re.IGNORECASE)

_CANVAS_W = 1280
_CANVAS_H = 720


def _pick_svg_candidate(value: Any) -> str:
    text = str(value or "").strip()
    if text and _SVG_TAG_RE.search(text):
        return text
    return ""


def resolve_slide_svg_markup(slide: Dict[str, Any]) -> str:
    """Return pre-rendered SVG markup if present on a slide payload."""
    for key in ("svg_markup", "svg", "svgMarkup"):
        picked = _pick_svg_candidate(slide.get(key))
        if picked:
            return picked

    blocks = slide.get("blocks")
    if not isinstance(blocks, list):
        return ""
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("block_type") or block.get("type") or "").strip().lower()
        if block_type != "svg":
            continue
        content = block.get("content")
        picked = _pick_svg_candidate(content)
        if picked:
            return picked
        if isinstance(content, dict):
            for key in ("svg", "markup", "svg_markup"):
                picked = _pick_svg_candidate(content.get(key))
                if picked:
                    return picked
    return ""


def _hex(value: Any, fallback: str) -> str:
    text = str(value or "").strip().replace("#", "")
    if _HEX_RE.fullmatch(text):
        return f"#{text.upper()}"
    return fallback


def _collect_text_lines(slide: Dict[str, Any], *, max_lines: int = 9) -> List[str]:
    blocks = slide.get("blocks")
    if not isinstance(blocks, list):
        return []
    lines: List[str] = []
    seen: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = str(block.get("block_type") or block.get("type") or "").strip().lower()
        if btype == "title":
            continue
        candidates: List[str] = []
        content = block.get("content")
        if isinstance(content, str):
            candidates.extend([item.strip() for item in re.split(r"[\n;；]+", content) if item.strip()])
        elif isinstance(content, dict):
            for key in ("title", "text", "body", "label", "caption", "description"):
                value = str(content.get(key) or "").strip()
                if value:
                    candidates.append(value)
        data = block.get("data")
        if isinstance(data, dict):
            for key in ("title", "label", "description", "summary"):
                value = str(data.get(key) or "").strip()
                if value:
                    candidates.append(value)
        for raw in candidates:
            normalized = re.sub(r"\s+", " ", raw).strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            lines.append(normalized)
            if len(lines) >= max_lines:
                return lines
    return lines


def _escape_items(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    for item in items:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if text:
            out.append(html.escape(text, quote=True))
    return out


def render_slide_svg_markup(
    *,
    slide: Dict[str, Any],
    slide_index: int,
    slide_count: int,
    deck_title: str,
    design_spec: Dict[str, Any] | None = None,
) -> str:
    """Render a structured slide payload into a single SVG page."""
    spec = dict(design_spec or {})
    colors = spec.get("colors") if isinstance(spec.get("colors"), dict) else {}
    primary = _hex(colors.get("primary"), "#1E3A5F")
    secondary = _hex(colors.get("secondary"), "#2F7BFF")
    accent = _hex(colors.get("accent"), "#18E0D1")
    bg = _hex(colors.get("bg"), "#0B1220")
    text_primary = _hex(colors.get("text_primary"), "#F4F8FF")
    text_secondary = _hex(colors.get("text_secondary"), "#BFD0E8")

    slide_type = str(slide.get("slide_type") or "content").strip().lower()
    title = str(slide.get("title") or "").strip()
    if not title:
        title = f"Slide {slide_index + 1}"

    lines = _collect_text_lines(slide, max_lines=10)
    escaped_title = html.escape(title, quote=True)
    escaped_deck_title = html.escape(str(deck_title or "").strip(), quote=True)
    escaped_lines = _escape_items(lines)

    subtitle = escaped_lines[0] if escaped_lines else escaped_deck_title or " "
    if slide_type in {"cover"}:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_CANVAS_W}" height="{_CANVAS_H}" '
            f'viewBox="0 0 {_CANVAS_W} {_CANVAS_H}">'
            "<defs>"
            f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0%" stop-color="{bg}"/>'
            f'<stop offset="100%" stop-color="{primary}"/>'
            "</linearGradient>"
            "</defs>"
            f'<rect width="{_CANVAS_W}" height="{_CANVAS_H}" fill="url(#bg)"/>'
            f'<rect x="88" y="96" width="14" height="120" rx="7" fill="{accent}"/>'
            f'<text x="128" y="220" fill="{text_primary}" font-size="64" font-family="Microsoft YaHei, Segoe UI, Arial" font-weight="700">{escaped_title}</text>'
            f'<text x="132" y="284" fill="{text_secondary}" font-size="30" font-family="Microsoft YaHei, Segoe UI, Arial">{subtitle}</text>'
            f'<text x="132" y="640" fill="{text_secondary}" font-size="22" font-family="Microsoft YaHei, Segoe UI, Arial">Page 1 / {max(1, slide_count)}</text>'
            "</svg>"
        )

    if slide_type in {"toc"}:
        toc_items = escaped_lines[:8] if escaped_lines else [f"Section {i + 1}" for i in range(5)]
        rows = []
        y = 210
        for idx, item in enumerate(toc_items, start=1):
            rows.append(
                f'<text x="150" y="{y}" fill="{text_primary}" font-size="34" font-family="Microsoft YaHei, Segoe UI, Arial">{idx}. {item}</text>'
            )
            y += 58
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_CANVAS_W}" height="{_CANVAS_H}" '
            f'viewBox="0 0 {_CANVAS_W} {_CANVAS_H}">'
            f'<rect width="{_CANVAS_W}" height="{_CANVAS_H}" fill="{bg}"/>'
            f'<text x="120" y="130" fill="{accent}" font-size="52" font-family="Microsoft YaHei, Segoe UI, Arial" font-weight="700">{escaped_title}</text>'
            + "".join(rows)
            + "</svg>"
        )

    if slide_type in {"divider"}:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_CANVAS_W}" height="{_CANVAS_H}" '
            f'viewBox="0 0 {_CANVAS_W} {_CANVAS_H}">'
            f'<rect width="{_CANVAS_W}" height="{_CANVAS_H}" fill="{primary}"/>'
            f'<rect x="160" y="312" width="960" height="96" rx="48" fill="{secondary}" fill-opacity="0.45"/>'
            f'<text x="640" y="380" text-anchor="middle" fill="{text_primary}" font-size="60" font-family="Microsoft YaHei, Segoe UI, Arial" font-weight="700">{escaped_title}</text>'
            "</svg>"
        )

    bullets = escaped_lines[:7] if escaped_lines else [f"Key point {i + 1}" for i in range(4)]
    bullet_rows: List[str] = []
    y = 226
    for item in bullets:
        bullet_rows.append(
            f'<circle cx="136" cy="{y - 8}" r="6" fill="{accent}"/>'
            f'<text x="154" y="{y}" fill="{text_primary}" font-size="30" font-family="Microsoft YaHei, Segoe UI, Arial">{item}</text>'
        )
        y += 64

    footer = f"Page {slide_index + 1} / {max(1, slide_count)}"
    if slide_type == "summary":
        footer = "Summary"

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_CANVAS_W}" height="{_CANVAS_H}" '
        f'viewBox="0 0 {_CANVAS_W} {_CANVAS_H}">'
        f'<rect width="{_CANVAS_W}" height="{_CANVAS_H}" fill="{bg}"/>'
        f'<rect x="72" y="74" width="1136" height="572" rx="28" fill="#0F1B33" stroke="{primary}" stroke-width="2"/>'
        f'<text x="112" y="150" fill="{accent}" font-size="48" font-family="Microsoft YaHei, Segoe UI, Arial" font-weight="700">{escaped_title}</text>'
        + "".join(bullet_rows)
        + f'<text x="112" y="676" fill="{text_secondary}" font-size="20" font-family="Microsoft YaHei, Segoe UI, Arial">{footer}</text>'
        + "</svg>"
    )
