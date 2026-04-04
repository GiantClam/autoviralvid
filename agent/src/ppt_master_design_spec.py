"""ppt-master inspired design-spec + render-path helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set

from src.ppt_visual_identity import canonicalize_theme_recipe, resolve_style_variant, resolve_tone


_LIGHT_TEMPLATE_FAMILIES = {
    "neural_blueprint_light",
    "ops_lifecycle_light",
    "consulting_warm_light",
}

_COMPLEX_LAYOUTS = {
    "timeline",
    "roadmap",
    "workflow",
    "swimlane",
    "matrix_2x2",
    "matrix_3x3",
    "architecture",
    "org_chart",
    "process_map",
    "journey_map",
    "ecosystem_map",
    "value_chain",
    "capability_map",
    "network_map",
    "infographic_strip",
    "storyline",
    "bento_5",
    "bento_6",
}

_COMPLEX_BLOCK_TYPES = {
    "workflow",
    "diagram",
    "sankey",
    "funnel",
    "matrix",
    "org_chart",
    "architecture",
    "mindmap",
    "treemap",
    "heatmap",
    "gauge",
    "pyramid",
    "swot",
    "process",
    "relationship",
    "timeline",
    "roadmap",
    "mind_map",
    "journey",
    "ecosystem",
    "value_chain",
    "capability",
    "infographic",
    "data_visualization",
    "dashboard",
    "radialbar",
    "sunburst",
    "rose",
    "radar_area",
    "bubble_map",
    "choropleth",
    "marimekko",
    "mekko",
    "boxplot",
    "violin",
    "candlestick",
    "wordcloud",
    "network",
    "alluvial",
    "streamgraph",
    "bullet",
    "variance",
    "pareto",
}

_COMPLEX_CHART_TYPES = {
    "sankey",
    "funnel",
    "waterfall",
    "treemap",
    "heatmap",
    "gauge",
    "pyramid",
    "sunburst",
    "radialbar",
    "rose",
    "radar_area",
    "bubble_map",
    "choropleth",
    "marimekko",
    "mekko",
    "boxplot",
    "violin",
    "candlestick",
    "wordcloud",
    "network",
    "alluvial",
    "streamgraph",
    "bullet",
    "variance",
    "pareto",
}

_TEXTUAL_BLOCK_TYPES = {
    "title",
    "subtitle",
    "body",
    "list",
    "quote",
    "icon_text",
    "text",
    "table",
}

_STYLE_FONTS = {
    "sharp": ("Bahnschrift SemiBold", "Segoe UI"),
    "soft": ("Aptos Display", "Aptos"),
    "rounded": ("Trebuchet MS", "Segoe UI"),
    "pill": ("Gill Sans MT", "Segoe UI"),
}

_STYLE_TITLE_SIZE = {
    "sharp": 24,
    "soft": 26,
    "rounded": 27,
    "pill": 28,
}

_STYLE_BODY_SIZE = {
    "sharp": 14,
    "soft": 15,
    "rounded": 16,
    "pill": 16,
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SPLIT_TOKENS_RE = re.compile(r"[\s,;|/]+")

_SEMANTIC_COMPLEX_SLIDE_TYPES = {
    "timeline",
    "workflow",
    "diagram",
    "architecture",
    "org_chart",
    "matrix",
    "swot",
    "roadmap",
    "relationship",
    "dashboard",
    "data_visualization",
    "infographic",
    "process_map",
    "journey_map",
    "ecosystem_map",
    "value_chain",
    "capability_map",
    "network_map",
    "operating_model",
    "strategy_map",
}

_SEMANTIC_COMPLEX_SUBTYPES = {
    "timeline",
    "roadmap",
    "swimlane",
    "workflow",
    "process",
    "diagram",
    "architecture",
    "org_chart",
    "matrix",
    "swot",
    "relationship",
    "journey",
    "ecosystem",
    "value_chain",
    "capability",
    "network",
    "infographic",
    "dashboard",
    "data_visualization",
}


def _clean_hex(value: Any, fallback: str) -> str:
    text = str(value or "").strip().replace("#", "")
    return text.upper() if re.fullmatch(r"[0-9A-Fa-f]{6}", text) else fallback


def _prefer_zh(*parts: Any) -> bool:
    return _CJK_RE.search(" ".join(str(p or "") for p in parts)) is not None


def _normalize_style(style_variant: str) -> str:
    normalized = str(style_variant or "").strip().lower()
    if normalized in {"sharp", "soft", "rounded", "pill"}:
        return normalized
    return "soft"


def _normalize_density(value: str) -> str:
    density = str(value or "").strip().lower()
    if density in {"sparse", "balanced", "dense"}:
        return density
    return "balanced"


def _normalize_tone(value: str) -> str:
    tone = str(value or "").strip().lower()
    if tone in {"light", "dark"}:
        return tone
    return "auto"


def _block_types(slide: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for item in slide.get("blocks") or []:
        if not isinstance(item, dict):
            continue
        t = str(item.get("block_type") or item.get("type") or "").strip().lower()
        if t:
            out.add(t)
    for item in slide.get("elements") or []:
        if not isinstance(item, dict):
            continue
        t = str(item.get("type") or "").strip().lower()
        if t:
            out.add(t)
    return out


def _has_complex_chart_subtype(slide: Dict[str, Any]) -> bool:
    for container in (slide.get("blocks") or [], slide.get("elements") or []):
        if not isinstance(container, list):
            continue
        for item in container:
            if not isinstance(item, dict):
                continue
            btype = str(item.get("block_type") or item.get("type") or "").strip().lower()
            if btype not in {"chart", "data_visualization"}:
                continue
            data = item.get("data")
            content = item.get("content")
            if not isinstance(data, dict) and isinstance(content, dict):
                data = content
            data = data if isinstance(data, dict) else {}
            subtype = str(
                data.get("chart_type")
                or data.get("type")
                or item.get("chart_type")
                or ""
            ).strip().lower()
            if subtype in _COMPLEX_CHART_TYPES:
                return True
    return False


def _semantic_tokens(value: Any) -> Set[str]:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text:
        return set()
    return {item for item in _SPLIT_TOKENS_RE.split(text) if item}


def _collect_semantic_markers(slide: Dict[str, Any]) -> Set[str]:
    fields = (
        slide.get("slide_type"),
        slide.get("type"),
        slide.get("content_subtype"),
        slide.get("subtype"),
        slide.get("semantic_type"),
        slide.get("semantic_subtype"),
        slide.get("layout_intent"),
        slide.get("intent"),
    )
    out: Set[str] = set()
    for item in fields:
        out |= _semantic_tokens(item)
    return out


def choose_render_path(slide: Dict[str, Any], *, svg_mode: str = "on") -> str:
    """Return per-slide render path: pptxgenjs|svg."""
    explicit = str(slide.get("render_path") or "").strip().lower()
    if explicit in {"pptxgenjs", "svg"}:
        if svg_mode == "off" and explicit == "svg":
            return "pptxgenjs"
        return explicit

    slide_type = str(slide.get("slide_type") or "").strip().lower()
    if slide_type in {"cover", "summary", "toc", "divider", "hero_1"}:
        return "pptxgenjs"
    layout = str(slide.get("layout_grid") or slide.get("layout") or "").strip().lower()
    block_types = _block_types(slide)
    semantic_markers = _collect_semantic_markers(slide)

    if svg_mode != "off":
        if layout in _COMPLEX_LAYOUTS:
            return "svg"
        if block_types & _COMPLEX_BLOCK_TYPES:
            return "svg"
        if _has_complex_chart_subtype(slide):
            return "svg"
        if slide_type in _SEMANTIC_COMPLEX_SLIDE_TYPES:
            return "svg"
        if semantic_markers & _SEMANTIC_COMPLEX_SUBTYPES:
            return "svg"
    return "pptxgenjs"


def apply_render_paths(
    slides: Iterable[Dict[str, Any]],
    *,
    svg_mode: str = "on",
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    normalized_svg_mode = str(svg_mode or "on").strip().lower()
    for raw in slides:
        slide = dict(raw if isinstance(raw, dict) else {})
        slide["render_path"] = choose_render_path(slide, svg_mode=normalized_svg_mode)
        out.append(slide)
    return out


def build_design_spec(
    *,
    theme: Dict[str, Any] | None = None,
    template_family: str = "",
    style_variant: str = "soft",
    theme_recipe: str = "auto",
    tone: str = "auto",
    visual_preset: str = "auto",
    visual_density: str = "balanced",
    visual_priority: bool = True,
    topic: str = "",
) -> Dict[str, Any]:
    """Build a normalized design_spec contract for Node rendering."""
    source = dict(theme or {})
    recipe = canonicalize_theme_recipe(
        theme_recipe
        or source.get("theme_recipe")
        or source.get("recipe")
        or "auto",
        fallback="consulting_clean",
    )
    style = _normalize_style(
        resolve_style_variant(
            style_variant or source.get("style") or "auto",
            theme_recipe=recipe,
            fallback="soft",
        )
    )
    normalized_tone = _normalize_tone(
        resolve_tone(
            tone
            or source.get("tone")
            or source.get("theme_tone")
            or source.get("preferred_tone")
            or "auto",
            theme_recipe=recipe,
            fallback="auto",
        )
    )
    density = _normalize_density(visual_density)
    family = str(template_family or source.get("template_family") or "").strip().lower()
    prefer_zh = _prefer_zh(topic, source.get("title"), source.get("subtitle"))
    en_title, en_body = _STYLE_FONTS.get(style, _STYLE_FONTS["soft"])
    title_font = "Microsoft YaHei" if prefer_zh else en_title
    body_font = "Microsoft YaHei" if prefer_zh else en_body

    base_margin = 0.45
    if density == "sparse":
        base_margin = 0.52
    elif density == "dense":
        base_margin = 0.36

    return {
        "colors": {
            "primary": _clean_hex(source.get("primary"), "2F7BFF"),
            "secondary": _clean_hex(source.get("secondary"), "12B6F5"),
            "accent": _clean_hex(source.get("accent"), "18E0D1"),
            "light": _clean_hex(source.get("light") or source.get("borderColor"), "1E335E"),
            "bg": _clean_hex(source.get("bg"), "060B17"),
            "text_primary": _clean_hex(source.get("darkText"), "E8F0FF"),
            "text_secondary": _clean_hex(source.get("mutedText"), "95A8CC"),
            "success": _clean_hex(source.get("success"), "22C55E"),
            "warning": _clean_hex(source.get("danger"), "EF4444"),
        },
        "typography": {
            "title_font": title_font,
            "body_font": body_font,
            "title_size": int(_STYLE_TITLE_SIZE.get(style, 26)),
            "body_size": int(_STYLE_BODY_SIZE.get(style, 15)),
            "caption_size": 11,
        },
        "spacing": {
            "page_margin": base_margin,
            "card_gap": 0.2 if density != "dense" else 0.14,
            "card_radius": 0.1 if style in {"soft", "rounded", "pill"} else 0.03,
            "header_height": 0.68 if density != "dense" else 0.62,
        },
        "visual": {
            "style_recipe": style,
            "theme_recipe": recipe,
            "tone": normalized_tone,
            "backdrop_type": str(visual_preset or "auto"),
            "visual_priority": bool(visual_priority),
            "visual_density": density,
            "icon_style": "outlined",
            "template_family": family,
            "light_template": normalized_tone == "light" or family in _LIGHT_TEMPLATE_FAMILIES,
        },
        "render_policy": {
            "svg_complex_layouts": sorted(_COMPLEX_LAYOUTS),
            "svg_complex_block_types": sorted(_COMPLEX_BLOCK_TYPES),
            "textual_block_types": sorted(_TEXTUAL_BLOCK_TYPES),
        },
    }
