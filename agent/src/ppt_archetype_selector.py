"""Top-k archetype selector with confidence and layout-fit rerank."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.ppt_layout_solver import solve_slide_layout


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _catalog_path() -> Path:
    return _repo_root() / "scripts" / "minimax" / "templates" / "archetype-catalog.json"


def _normalize_key(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _normalize_object(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: Dict[str, str] = {}
    for key, val in value.items():
        nk = _normalize_key(key)
        nv = _normalize_key(val)
        if nk and nv:
            out[nk] = nv
    return out


def _normalize_list(value: Any) -> List[str]:
    rows = value if isinstance(value, list) else []
    out: List[str] = []
    seen: set[str] = set()
    for row in rows:
        key = _normalize_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


_CATALOG_CACHE: Dict[str, Any] | None = None


def load_archetype_catalog() -> Dict[str, Any]:
    global _CATALOG_CACHE
    if isinstance(_CATALOG_CACHE, dict):
        return _CATALOG_CACHE
    path = _catalog_path()
    fallback = {
        "version": "v2",
        "archetypes": ["thesis_assertion", "evidence_cards_3", "comparison_2col"],
        "role_defaults": {"content": "thesis_assertion"},
        "layout_overrides": {},
        "semantic_overrides": {},
    }
    if not path.exists():
        _CATALOG_CACHE = fallback
        return _CATALOG_CACHE
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _CATALOG_CACHE = fallback
        return _CATALOG_CACHE
    catalog = {
        "version": str(parsed.get("version") or "v2").strip() or "v2",
        "archetypes": _normalize_list(parsed.get("archetypes")),
        "role_defaults": _normalize_object(parsed.get("role_defaults")),
        "layout_overrides": _normalize_object(parsed.get("layout_overrides")),
        "semantic_overrides": _normalize_object(parsed.get("semantic_overrides")),
    }
    if not catalog["archetypes"]:
        catalog["archetypes"] = fallback["archetypes"]
    _CATALOG_CACHE = catalog
    return catalog


def _block_type(block: Dict[str, Any]) -> str:
    return _normalize_key(block.get("block_type") or block.get("type"))


def _slide_page_role(slide: Dict[str, Any]) -> str:
    role = _normalize_key(slide.get("page_role") or slide.get("slide_type"))
    return role if role in {"cover", "toc", "divider", "summary"} else "content"


def _seed_scores(slide: Dict[str, Any], catalog: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
    allowed = catalog.get("archetypes") if isinstance(catalog.get("archetypes"), list) else []
    scores: Dict[str, float] = {item: 0.05 for item in allowed}
    reasons: Dict[str, List[str]] = {item: [] for item in allowed}

    role = _slide_page_role(slide)
    semantic = _normalize_key(
        slide.get("semantic_type")
        or slide.get("semantic_subtype")
        or slide.get("content_subtype")
        or slide.get("subtype")
    )
    layout = _normalize_key(slide.get("layout_grid") or slide.get("layout"))

    explicit = _normalize_key(slide.get("archetype"))
    if explicit in scores:
        scores[explicit] += 0.85
        reasons[explicit].append("explicit_archetype")

    role_default = _normalize_key((catalog.get("role_defaults") or {}).get(role) or "")
    if role_default in scores:
        scores[role_default] += 0.45
        reasons[role_default].append(f"role_default:{role}")

    semantic_override = _normalize_key((catalog.get("semantic_overrides") or {}).get(semantic) or "")
    if semantic_override in scores:
        scores[semantic_override] += 0.5
        reasons[semantic_override].append(f"semantic_override:{semantic}")

    layout_override = _normalize_key((catalog.get("layout_overrides") or {}).get(layout) or "")
    if layout_override in scores:
        scores[layout_override] += 0.35
        reasons[layout_override].append(f"layout_override:{layout}")

    block_types = {
        _block_type(block)
        for block in (slide.get("blocks") if isinstance(slide.get("blocks"), list) else [])
        if isinstance(block, dict)
    }
    if block_types & {"chart", "kpi", "table"}:
        for key in ("dashboard_kpi_4", "chart_single_focus", "chart_dual_compare"):
            if key in scores:
                scores[key] += 0.18
                reasons[key].append("has_data_block")
    if "image" in block_types:
        for key in ("media_showcase_1p2s", "comparison_2col"):
            if key in scores:
                scores[key] += 0.12
                reasons[key].append("has_image_block")
    if block_types & {"workflow", "diagram"}:
        if "process_flow_4step" in scores:
            scores["process_flow_4step"] += 0.22
            reasons["process_flow_4step"].append("has_diagram_block")
    if "timeline" in block_types and "timeline_horizontal" in scores:
        scores["timeline_horizontal"] += 0.22
        reasons["timeline_horizontal"].append("has_timeline_block")
    if "comparison" in block_types and "comparison_2col" in scores:
        scores["comparison_2col"] += 0.18
        reasons["comparison_2col"].append("has_comparison_block")
    if "quote" in block_types and "quote_hero" in scores:
        scores["quote_hero"] += 0.22
        reasons["quote_hero"].append("has_quote_block")

    return scores, reasons


def _candidate_sort_key(item: Tuple[str, float]) -> Tuple[float, str]:
    return (float(item[1]), str(item[0]))


def _layout_fit_bonus(slide: Dict[str, Any], archetype: str) -> Tuple[float, Dict[str, Any]]:
    solution = solve_slide_layout(slide, archetype=archetype)
    status = str(solution.get("status") or "").strip().lower()
    if status == "ok":
        return 0.16, solution
    if status == "underflow":
        return -0.05, solution
    if status == "overflow":
        return -0.09, solution
    return -0.03, solution


def _build_candidate_row(
    *,
    archetype: str,
    base_score: float,
    reasons: List[str],
    fit_bonus: float,
    layout_solution: Dict[str, Any],
) -> Dict[str, Any]:
    score = max(0.0, min(1.0, base_score + fit_bonus))
    return {
        "archetype": archetype,
        "score": round(score, 4),
        "base_score": round(max(0.0, min(1.0, base_score)), 4),
        "fit_bonus": round(float(fit_bonus), 4),
        "status": str(layout_solution.get("status") or "ok"),
        "reasons": reasons[:6] if reasons else [],
    }


def _confidence(candidates: List[Dict[str, Any]]) -> float:
    if not candidates:
        return 0.0
    top = float(candidates[0].get("score") or 0.0)
    second = float(candidates[1].get("score") or 0.0) if len(candidates) > 1 else 0.0
    margin = max(0.0, top - second)
    absolute = max(0.0, min(1.0, top))
    conf = 0.55 * absolute + 0.45 * min(1.0, margin * 2.8)
    return round(max(0.05, min(0.99, conf)), 4)


def select_slide_archetype(
    slide: Dict[str, Any],
    *,
    top_k: int = 3,
    rerank_window: int = 6,
) -> Dict[str, Any]:
    catalog = load_archetype_catalog()
    scores, reasons = _seed_scores(slide if isinstance(slide, dict) else {}, catalog)
    ranked = sorted(scores.items(), key=_candidate_sort_key, reverse=True)
    shortlisted = ranked[: max(1, int(rerank_window))]

    rows: List[Dict[str, Any]] = []
    for archetype, base_score in shortlisted:
        fit_bonus, layout_solution = _layout_fit_bonus(slide, archetype)
        rows.append(
            _build_candidate_row(
                archetype=archetype,
                base_score=float(base_score),
                reasons=reasons.get(archetype, []),
                fit_bonus=fit_bonus,
                layout_solution=layout_solution,
            )
        )
    rows.sort(key=lambda row: (float(row.get("score") or 0.0), str(row.get("archetype") or "")), reverse=True)
    top_rows = rows[: max(1, int(top_k))]
    selected = str(top_rows[0].get("archetype") or "thesis_assertion")
    return {
        "selected": selected,
        "confidence": _confidence(top_rows),
        "candidates": top_rows,
        "rerank_version": "v1",
    }

