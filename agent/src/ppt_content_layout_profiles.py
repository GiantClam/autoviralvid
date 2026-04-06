"""Archetype-driven content layout planning for PPT content pages."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set

from src.ppt_archetype_selector import select_slide_archetype


_COMPARISON_TOKENS = (
    "vs",
    "versus",
    "compare",
    "comparison",
    "before",
    "after",
    "tradeoff",
    "benchmark",
    "对比",
    "比较",
    "传统",
    "方案",
    "优势",
    "劣势",
    "前后",
)
_DATA_TOKENS = (
    "kpi",
    "metric",
    "metrics",
    "trend",
    "dashboard",
    "scorecard",
    "chart",
    "data",
    "增长",
    "指标",
    "趋势",
    "转化",
    "占比",
    "收入",
)
_PROCESS_TOKENS = (
    "workflow",
    "process",
    "pipeline",
    "roadmap",
    "lifecycle",
    "step",
    "机制",
    "流程",
    "阶段",
    "路径",
)
_SHOWCASE_TOKENS = (
    "image",
    "gallery",
    "showcase",
    "case",
    "visual",
    "photo",
    "案例",
    "展示",
    "画面",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize_key(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list(value: Any) -> List[str]:
    rows = value if isinstance(value, list) else []
    out: List[str] = []
    seen: Set[str] = set()
    for row in rows:
        key = _normalize_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


@lru_cache(maxsize=1)
def _load_synthesis_spec() -> Dict[str, Dict[str, Any]]:
    fallback = {
        "default": {
            "template_whitelist": ["consulting_warm_light", "split_media_dark", "comparison_cards_light"],
            "required_blocks": ["title", "body", "list"],
            "optional_blocks": ["image"],
            "dual_text": True,
            "semantic_page_type": "content",
        }
    }
    path = Path(__file__).resolve().parent / "ppt_specs" / "archetype-synthesis-spec.json"
    if not path.exists():
        return fallback
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    out: Dict[str, Dict[str, Any]] = {}
    for raw_key, raw_value in parsed.items():
        key = _normalize_key(raw_key)
        if not key or not isinstance(raw_value, dict):
            continue
        out[key] = {
            "template_whitelist": _normalize_list(raw_value.get("template_whitelist")),
            "required_blocks": _normalize_list(raw_value.get("required_blocks")),
            "optional_blocks": _normalize_list(raw_value.get("optional_blocks")),
            "dual_text": bool(raw_value.get("dual_text", True)),
            "semantic_page_type": _normalize_key(raw_value.get("semantic_page_type") or "content") or "content",
        }
    if "default" not in out:
        out["default"] = fallback["default"]
    return out


def _has_numeric_signal(items: Sequence[str]) -> bool:
    blob = " ".join(_normalize_text(item) for item in items if _normalize_text(item))
    if not blob:
        return False
    return bool(re.search(r"\d+(?:\.\d+)?%?", blob))


def _contains_any(blob: str, tokens: Sequence[str]) -> bool:
    haystack = str(blob or "").lower()
    return any(token and str(token).lower() in haystack for token in tokens)


def _normalize_elements(data_elements: Sequence[str]) -> Set[str]:
    return {
        _normalize_key(item)
        for item in (data_elements or [])
        if _normalize_key(item)
    }


def _is_comparison_signal(*, title: str, evidence: Sequence[str], elements: Set[str]) -> bool:
    blob = " ".join([title, *[_normalize_text(item) for item in evidence]])
    return bool(
        {"comparison", "versus", "vs"} & elements
        or _contains_any(blob, _COMPARISON_TOKENS)
    )


def _is_data_signal(*, title: str, evidence: Sequence[str], elements: Set[str]) -> bool:
    blob = " ".join([title, *[_normalize_text(item) for item in evidence]])
    return bool(
        {"chart", "kpi", "table", "data"} & elements
        or _contains_any(blob, _DATA_TOKENS)
        or _has_numeric_signal([title, *evidence])
    )


def _is_process_signal(*, title: str, evidence: Sequence[str], elements: Set[str]) -> bool:
    blob = " ".join([title, *[_normalize_text(item) for item in evidence]])
    return bool(
        {"workflow", "diagram", "timeline", "roadmap", "process"} & elements
        or _contains_any(blob, _PROCESS_TOKENS)
    )


def _is_showcase_signal(*, title: str, visual_anchor: str, elements: Set[str]) -> bool:
    blob = " ".join([title, _normalize_text(visual_anchor)])
    return bool(
        {"image", "gallery", "showcase", "case"} & elements
        or _normalize_key(visual_anchor) in {"image", "case", "photo", "visual"}
        or _contains_any(blob, _SHOWCASE_TOKENS)
    )


def _infer_semantic_type(
    *,
    title: str,
    evidence: Sequence[str],
    visual_anchor: str,
    elements: Set[str],
    layout_hint: str,
) -> str:
    if _is_comparison_signal(title=title, evidence=evidence, elements=elements):
        return "comparison"
    if _is_process_signal(title=title, evidence=evidence, elements=elements):
        return "roadmap" if _normalize_key(layout_hint) == "timeline" else "workflow"
    if _is_data_signal(title=title, evidence=evidence, elements=elements):
        return "data_visualization"
    if _is_showcase_signal(title=title, visual_anchor=visual_anchor, elements=elements):
        return "showcase"
    return "content"


def _seed_block_types(
    *,
    title: str,
    evidence: Sequence[str],
    visual_anchor: str,
    elements: Set[str],
    layout_hint: str,
) -> List[str]:
    block_types: Set[str] = {"body", "list"}
    if _is_comparison_signal(title=title, evidence=evidence, elements=elements):
        block_types.add("comparison")
    if _is_data_signal(title=title, evidence=evidence, elements=elements):
        block_types.add("chart")
        if "table" in elements:
            block_types.add("table")
        if "kpi" in elements or _has_numeric_signal([title, *evidence]):
            block_types.add("kpi")
    if _is_process_signal(title=title, evidence=evidence, elements=elements):
        block_types.add("workflow")
    if _is_showcase_signal(title=title, visual_anchor=visual_anchor, elements=elements):
        block_types.add("image")
    if _normalize_key(layout_hint) in {"bento_5", "asymmetric_2"}:
        block_types.add("image")
    return sorted(block_types)


def _profile_for_archetype(archetype: str) -> Dict[str, Any]:
    spec = _load_synthesis_spec()
    normalized = _normalize_key(archetype)
    return dict(spec.get(normalized) or spec["default"])


def _preferred_archetype(
    *,
    semantic_type: str,
    visual_anchor: str,
    elements: Set[str],
    layout_hint: str,
) -> str:
    layout = _normalize_key(layout_hint)
    anchor = _normalize_key(visual_anchor)
    semantic = _normalize_key(semantic_type)
    if semantic == "workflow":
        return "process_flow_4step"
    if semantic == "roadmap":
        return "timeline_horizontal"
    if semantic == "comparison":
        return "chart_dual_compare" if {"chart", "kpi", "table"} & elements else "comparison_2col"
    if semantic == "data_visualization":
        return "dashboard_kpi_4" if {"kpi", "table"} & elements else "chart_single_focus"
    if semantic == "showcase":
        return "media_showcase_1p2s"
    if anchor in {"roles", "trend"} and layout in {"split_2", "asymmetric_2"}:
        return "comparison_2col"
    if anchor == "case":
        return "evidence_cards_3"
    return "thesis_assertion"


def _block_flags(profile: Dict[str, Any]) -> Dict[str, bool]:
    blocks = set(_normalize_list(profile.get("required_blocks")) + _normalize_list(profile.get("optional_blocks")))
    return {
        "chart": "chart" in blocks,
        "kpi": "kpi" in blocks,
        "image": "image" in blocks,
        "comparison": "comparison" in blocks,
        "dual_text": bool(profile.get("dual_text", True)),
    }


def build_content_layout_plan(
    *,
    title: str,
    evidence: Sequence[str],
    visual_anchor: str,
    data_elements: Sequence[str],
    layout_hint: str,
) -> Dict[str, Any]:
    elements = _normalize_elements(data_elements)
    semantic_type = _infer_semantic_type(
        title=title,
        evidence=evidence,
        visual_anchor=visual_anchor,
        elements=elements,
        layout_hint=layout_hint,
    )
    seed_block_types = _seed_block_types(
        title=title,
        evidence=evidence,
        visual_anchor=visual_anchor,
        elements=elements,
        layout_hint=layout_hint,
    )
    seed_slide = {
        "slide_type": "content",
        "layout_grid": ("split_2" if _normalize_key(layout_hint) == "hero_1" else _normalize_key(layout_hint)) or "split_2",
        "semantic_type": semantic_type,
        "blocks": [
            {"block_type": "title", "content": _normalize_text(title) or "Content"},
            *[
                {"block_type": block_type, "content": _normalize_text(title) or block_type}
                for block_type in seed_block_types
            ],
        ],
    }
    archetype_plan = select_slide_archetype(seed_slide, top_k=3, rerank_window=6)
    selected = _normalize_key(archetype_plan.get("selected") or "")
    preferred = _preferred_archetype(
        semantic_type=semantic_type,
        visual_anchor=visual_anchor,
        elements=elements,
        layout_hint=layout_hint,
    )
    archetype = preferred or selected or "thesis_assertion"
    if selected and selected not in {"cover_hero", "toc_compact", "section_divider", "summary_action", "quote_hero"}:
        candidate_rows = archetype_plan.get("candidates") if isinstance(archetype_plan, dict) else []
        candidate_keys = {
            _normalize_key((row or {}).get("archetype") if isinstance(row, dict) else row)
            for row in (candidate_rows if isinstance(candidate_rows, list) else [])
        }
        if not preferred or preferred not in candidate_keys:
            archetype = selected
    profile = _profile_for_archetype(archetype)
    return {
        "archetype": archetype,
        "archetype_plan": archetype_plan,
        "semantic_page_type": profile.get("semantic_page_type") or semantic_type,
        "template_whitelist": list(profile.get("template_whitelist") or []),
        "block_flags": _block_flags(profile),
        "required_blocks": list(profile.get("required_blocks") or []),
        "optional_blocks": list(profile.get("optional_blocks") or []),
        "dual_text": bool(profile.get("dual_text", True)),
    }


def choose_content_layout_profile(
    *,
    title: str,
    evidence: Sequence[str],
    visual_anchor: str,
    data_elements: Sequence[str],
    layout_hint: str,
) -> str:
    return str(
        build_content_layout_plan(
            title=title,
            evidence=evidence,
            visual_anchor=visual_anchor,
            data_elements=data_elements,
            layout_hint=layout_hint,
        ).get("archetype")
        or "thesis_assertion"
    )


def profile_block_types(profile: str) -> Dict[str, bool]:
    return _block_flags(_profile_for_archetype(profile))


def profile_template_whitelist(profile: str) -> List[str]:
    return list(_profile_for_archetype(profile).get("template_whitelist") or [])
