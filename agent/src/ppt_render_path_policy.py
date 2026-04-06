"""Central render-path policy for template-first PPT generation."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set


DEFAULT_PPTXGENJS_SLIDE_TYPES = {"cover", "summary", "toc", "divider", "section", "hero_1"}

SVG_EXCEPTION_LAYOUTS = {
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
}

SVG_EXCEPTION_BLOCK_TYPES = {
    "workflow",
    "diagram",
    "sankey",
    "funnel",
    "matrix",
    "org_chart",
    "architecture",
    "mindmap",
    "mind_map",
    "treemap",
    "heatmap",
    "gauge",
    "pyramid",
    "process",
    "relationship",
    "timeline",
    "roadmap",
    "journey",
    "ecosystem",
    "value_chain",
    "capability",
    "network",
    "alluvial",
    "streamgraph",
    "wordcloud",
    "choropleth",
    "marimekko",
    "mekko",
    "boxplot",
    "violin",
    "candlestick",
    "bullet",
    "variance",
    "pareto",
}

SVG_EXCEPTION_CHART_TYPES = {
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

SVG_EXCEPTION_SLIDE_TYPES = {
    "timeline",
    "workflow",
    "diagram",
    "architecture",
    "org_chart",
    "matrix",
    "roadmap",
    "relationship",
    "process_map",
    "journey_map",
    "ecosystem_map",
    "value_chain",
    "capability_map",
    "network_map",
    "operating_model",
    "strategy_map",
}

SVG_EXCEPTION_SUBTYPES = {
    "timeline",
    "roadmap",
    "swimlane",
    "workflow",
    "process",
    "diagram",
    "architecture",
    "org_chart",
    "matrix",
    "relationship",
    "journey",
    "ecosystem",
    "value_chain",
    "capability",
    "network",
}

_TEXT_HEAVY_BLOCK_TYPES = {"title", "subtitle", "body", "list", "quote", "icon_text", "text", "table"}
_LONG_TEXT_RE = re.compile(r"\S{80,}")
_SPLIT_TOKENS_RE = re.compile(r"[\s,;|/]+")


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _block_types(slide: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for item in slide.get("blocks") or []:
        if isinstance(item, dict):
            key = _normalize(item.get("block_type") or item.get("type"))
            if key:
                out.add(key)
    for item in slide.get("elements") or []:
        if isinstance(item, dict):
            key = _normalize(item.get("type"))
            if key:
                out.add(key)
    return out


def _chart_types(slide: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for item in slide.get("blocks") or []:
        if not isinstance(item, dict):
            continue
        if _normalize(item.get("block_type") or item.get("type")) != "chart":
            continue
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        content = item.get("content") if isinstance(item.get("content"), dict) else {}
        chart_type = _normalize(data.get("chart_type") or content.get("chart_type") or item.get("chart_type"))
        if chart_type:
            out.add(chart_type)
    return out


def _semantic_markers(slide: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for raw in (slide.get("content_subtype"), slide.get("semantic_subtype")):
        text = _normalize(raw)
        if not text:
            continue
        out.update(token for token in _SPLIT_TOKENS_RE.split(text) if token)
    return out


def _has_split_or_merge_applied(slide: Dict[str, Any]) -> bool:
    return bool(
        slide.get("continuation_of")
        or slide.get("is_continuation")
        or slide.get("continuation_total") is not None
        or slide.get("continuation_index") is not None
        or slide.get("merged_from_underflow")
        or slide.get("underflow_merge_applied")
    )


def _split_merge_exhausted(slide: Dict[str, Any]) -> bool:
    return bool(
        slide.get("split_merge_exhausted")
        or slide.get("split_merge_failed")
        or slide.get("split_merge_structural_failure")
    )


def _is_text_or_data_heavy_signal(slide: Dict[str, Any]) -> bool:
    if _normalize(slide.get("content_density")) == "high":
        return True
    texts: List[str] = []
    for field in ("title", "subtitle", "body", "text"):
        text = str(slide.get(field) or "").strip()
        if text:
            texts.append(text)
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if _normalize(block.get("block_type") or block.get("type")) not in _TEXT_HEAVY_BLOCK_TYPES:
            continue
        content = block.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, dict):
            for key in ("text", "body", "title", "label", "caption", "description"):
                value = str(content.get(key) or "").strip()
                if value:
                    texts.append(value)
    joined = " ".join(item for item in texts if item)
    if len(joined) >= 280 or _LONG_TEXT_RE.search(joined):
        return True
    bullet_like_count = 0
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if _normalize(block.get("block_type") or block.get("type")) not in {"list", "body", "text"}:
            continue
        content = str(block.get("content") or "")
        bullet_like_count += max(content.count(";"), content.count("；"), content.count("\n"))
    return bullet_like_count >= 6


def _has_template_fallback(slide: Dict[str, Any]) -> bool:
    return bool(_normalize(slide.get("template_family") or slide.get("template_id"))) or bool(slide.get("template_lock"))


def _explicit_exception_marker(slide: Dict[str, Any]) -> bool:
    if slide.get("single_slide_intent_required") or slide.get("structural_expression_failure"):
        return True
    exception = _normalize(slide.get("svg_exception_category") or slide.get("render_path_policy_exception"))
    return bool(exception)


def _decision(
    render_path: str,
    reason: str,
    *,
    allowed_exception_reasons: List[str],
    forbidden_triggers: List[str],
) -> Dict[str, Any]:
    return {
        "render_path": render_path,
        "reason": reason,
        "allowed_exception_reasons": allowed_exception_reasons,
        "forbidden_triggers": forbidden_triggers,
    }


def classify_render_path(slide: Dict[str, Any], *, svg_mode: str = "on") -> Dict[str, Any]:
    svg_mode_norm = _normalize(svg_mode) or "on"
    explicit = _normalize(slide.get("render_path"))
    slide_type = _normalize(slide.get("slide_type"))
    layout = _normalize(slide.get("layout_grid") or slide.get("layout"))
    block_types = _block_types(slide)
    chart_types = _chart_types(slide)
    semantic_markers = _semantic_markers(slide)
    split_merge_applied = _has_split_or_merge_applied(slide)
    split_merge_exhausted = _split_merge_exhausted(slide)
    explicit_exception = _explicit_exception_marker(slide)

    forbidden_triggers: List[str] = []
    if _is_text_or_data_heavy_signal(slide):
        forbidden_triggers.append("density_only")
    if _has_template_fallback(slide):
        forbidden_triggers.append("template_fallback_available")
    if split_merge_applied:
        forbidden_triggers.append("split_or_merge_already_applied")
    if not split_merge_exhausted:
        forbidden_triggers.append("split_merge_not_exhausted")

    allowed_exception_reasons: List[str] = []
    if layout in SVG_EXCEPTION_LAYOUTS:
        allowed_exception_reasons.append(f"layout:{layout}")
    allowed_exception_reasons.extend(f"block:{item}" for item in sorted(block_types & SVG_EXCEPTION_BLOCK_TYPES))
    allowed_exception_reasons.extend(f"chart:{item}" for item in sorted(chart_types & SVG_EXCEPTION_CHART_TYPES))
    if slide_type in SVG_EXCEPTION_SLIDE_TYPES:
        allowed_exception_reasons.append(f"slide_type:{slide_type}")
    allowed_exception_reasons.extend(f"semantic:{item}" for item in sorted(semantic_markers & SVG_EXCEPTION_SUBTYPES))
    if explicit_exception:
        allowed_exception_reasons.append("explicit_exception_marker")

    if explicit in {"pptxgenjs", "svg", "png_fallback"}:
        chosen = "pptxgenjs" if svg_mode_norm == "off" and explicit == "svg" else explicit
        return _decision(
            chosen,
            "explicit_render_path",
            allowed_exception_reasons=allowed_exception_reasons,
            forbidden_triggers=forbidden_triggers,
        )
    if slide_type in DEFAULT_PPTXGENJS_SLIDE_TYPES:
        return _decision(
            "pptxgenjs",
            "default_terminal_or_template_slide",
            allowed_exception_reasons=allowed_exception_reasons,
            forbidden_triggers=forbidden_triggers,
        )
    if svg_mode_norm == "off":
        return _decision(
            "pptxgenjs",
            "svg_mode_off",
            allowed_exception_reasons=allowed_exception_reasons,
            forbidden_triggers=forbidden_triggers,
        )
    if split_merge_applied and not explicit_exception:
        return _decision(
            "pptxgenjs",
            "split_merge_first_keep_template",
            allowed_exception_reasons=allowed_exception_reasons,
            forbidden_triggers=forbidden_triggers,
        )
    if allowed_exception_reasons:
        if not explicit_exception and not split_merge_exhausted:
            return _decision(
                "pptxgenjs",
                "split_merge_first_required",
                allowed_exception_reasons=allowed_exception_reasons,
                forbidden_triggers=forbidden_triggers,
            )
        return _decision(
            "svg",
            allowed_exception_reasons[0],
            allowed_exception_reasons=allowed_exception_reasons,
            forbidden_triggers=forbidden_triggers,
        )
    return _decision(
        "pptxgenjs",
        "default_template_route",
        allowed_exception_reasons=allowed_exception_reasons,
        forbidden_triggers=forbidden_triggers,
    )


def choose_render_path_by_policy(slide: Dict[str, Any], *, svg_mode: str = "on") -> str:
    return str(classify_render_path(slide, svg_mode=svg_mode).get("render_path") or "pptxgenjs")


def allow_visual_critic_svg_fallback(slide: Dict[str, Any], issue_codes: Iterable[str]) -> bool:
    codes = {str(item or "").strip().lower() for item in issue_codes if str(item or "").strip()}
    if not ({"card_overlap", "visual_card_overlap_ratio_high"} & codes):
        return False
    decision = classify_render_path(slide, svg_mode="on")
    return str(decision.get("render_path") or "") == "svg"
