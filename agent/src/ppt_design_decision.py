"""Unified design decision helpers for PPT export pipeline.

This module centralizes visual decision fields so Python orchestration and
Node rendering consume the same source of truth (`design_decision_v1`).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping

CANONICAL_DECISION_TRACE_OWNER = "agent/src/ppt_design_decision.py"
FINAL_OWNER_ASSERTION_OWNER = "agent/src/ppt_service_v2.py"

_DECK_FIELDS = (
    "style_variant",
    "palette_key",
    "theme_recipe",
    "tone",
    "template_family",
    "quality_profile",
    "route_mode",
    "skill_profile",
)

_SLIDE_FIELDS = (
    "style_variant",
    "palette_key",
    "theme_recipe",
    "tone",
    "template_family",
    "layout_grid",
    "render_path",
    "skill_profile",
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _slide_id(slide: Mapping[str, Any], index: int) -> str:
    for key in ("slide_id", "id", "page_number"):
        raw = _normalize_text(slide.get(key))
        if raw:
            return raw
    return f"slide-{index + 1}"


def _is_auto(value: str) -> bool:
    normalized = _normalize_text(value).lower()
    return normalized in {"", "auto", "none", "null", "undefined"}


def normalize_design_decision_v1(raw: Any) -> Dict[str, Any]:
    data = raw if isinstance(raw, Mapping) else {}
    deck_raw = data.get("deck") if isinstance(data.get("deck"), Mapping) else {}
    slides_raw = data.get("slides") if isinstance(data.get("slides"), list) else []
    trace_raw = data.get("decision_trace") if isinstance(data.get("decision_trace"), list) else []

    deck: Dict[str, str] = {}
    for field in _DECK_FIELDS:
        text = _normalize_text(deck_raw.get(field))
        if text:
            deck[field] = text

    slides: List[Dict[str, str]] = []
    seen: set[str] = set()
    for idx, row in enumerate(slides_raw):
        if not isinstance(row, Mapping):
            continue
        sid = _normalize_text(row.get("slide_id"))
        if not sid:
            continue
        if sid in seen:
            continue
        seen.add(sid)
        item: Dict[str, str] = {"slide_id": sid}
        for field in _SLIDE_FIELDS:
            text = _normalize_text(row.get(field))
            if text:
                item[field] = text
        if len(item) > 1:
            slides.append(item)
        if len(slides) >= 200:
            break

    trace: List[Dict[str, Any]] = []
    for row in trace_raw[:40]:
        if not isinstance(row, Mapping):
            continue
        source = _normalize_text(row.get("source") or row.get("stage"))
        if not source:
            continue
        owned_fields = row.get("owned_fields")
        normalized_owned_fields: List[str] = []
        if isinstance(owned_fields, list):
            for item in owned_fields:
                text = _normalize_text(item)
                if text:
                    normalized_owned_fields.append(text)
        owner_path = _normalize_text(row.get("owner"))
        trace.append(
            {
                "source": source,
                "detail": _normalize_text(row.get("detail") or row.get("message")),
                "confidence": float(row.get("confidence") or 0.0),
                "owner": owner_path or CANONICAL_DECISION_TRACE_OWNER,
                "owned_fields": normalized_owned_fields,
            }
        )

    return {
        "version": "v1",
        "deck": deck,
        "slides": slides,
        "decision_trace": trace,
    }


def build_design_decision_v1(
    *,
    style_variant: str = "",
    palette_key: str = "",
    theme_recipe: str = "",
    tone: str = "",
    template_family: str = "",
    quality_profile: str = "",
    route_mode: str = "",
    skill_profile: str = "",
    slides: List[Dict[str, Any]] | None = None,
    decision_source: str = "",
    decision_trace: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    deck: Dict[str, str] = {}
    for field, value in (
        ("style_variant", style_variant),
        ("palette_key", palette_key),
        ("theme_recipe", theme_recipe),
        ("tone", tone),
        ("template_family", template_family),
        ("quality_profile", quality_profile),
        ("route_mode", route_mode),
        ("skill_profile", skill_profile),
    ):
        text = _normalize_text(value)
        if text and not _is_auto(text):
            deck[field] = text

    rows: List[Dict[str, str]] = []
    for idx, raw_slide in enumerate(slides or []):
        if not isinstance(raw_slide, Mapping):
            continue
        sid = _slide_id(raw_slide, idx)
        row: Dict[str, str] = {"slide_id": sid}
        for field in _SLIDE_FIELDS:
            value = _normalize_text(raw_slide.get(field))
            if not value or _is_auto(value):
                continue
            row[field] = value
        if len(row) <= 1:
            continue
        rows.append(row)
        if len(rows) >= 200:
            break

    trace = [dict(item) for item in (decision_trace or []) if isinstance(item, Mapping)]
    if decision_source:
        trace.append(
            {
                "source": decision_source,
                "detail": "decision_built",
                "confidence": 1.0,
                "owner": CANONICAL_DECISION_TRACE_OWNER,
                "owned_fields": list(_DECK_FIELDS),
            }
        )

    return normalize_design_decision_v1(
        {
            "version": "v1",
            "deck": deck,
            "slides": rows,
            "decision_trace": trace,
        }
    )


def decision_deck_value(decision: Mapping[str, Any] | None, key: str, default: str = "") -> str:
    normalized = normalize_design_decision_v1(decision)
    value = _normalize_text(normalized.get("deck", {}).get(key))
    return value if value else _normalize_text(default)


def apply_design_decision_to_slides(
    slides: List[Dict[str, Any]],
    decision: Mapping[str, Any] | None,
) -> List[Dict[str, Any]]:
    normalized = normalize_design_decision_v1(decision)
    deck = normalized.get("deck") if isinstance(normalized.get("deck"), Mapping) else {}
    rows = normalized.get("slides") if isinstance(normalized.get("slides"), list) else []
    by_slide: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        sid = _normalize_text(row.get("slide_id"))
        if sid and sid not in by_slide:
            by_slide[sid] = dict(row)

    out: List[Dict[str, Any]] = []
    for idx, raw in enumerate(slides or []):
        if not isinstance(raw, Mapping):
            continue
        slide = dict(raw)
        sid = _slide_id(slide, idx)
        row = by_slide.get(sid, {})
        for field in _SLIDE_FIELDS:
            row_picked = _normalize_text(row.get(field))
            if field in {"layout_grid", "render_path"} and row_picked and not _is_auto(row_picked):
                slide[field] = row_picked
                continue
            current = _normalize_text(slide.get(field))
            if current and not _is_auto(current):
                continue
            picked = row_picked
            if not picked:
                if field in {"style_variant", "palette_key", "theme_recipe", "tone", "template_family", "skill_profile"}:
                    picked = _normalize_text(deck.get(field))
            if picked and not _is_auto(picked):
                slide[field] = picked
        out.append(slide)
    return out


def attach_design_decision_v1(
    payload: Dict[str, Any],
    *,
    decision: Mapping[str, Any] | None = None,
    decision_source: str = "",
    decision_trace: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    out = dict(payload or {})
    if isinstance(decision, Mapping):
        normalized = normalize_design_decision_v1(decision)
    else:
        normalized = build_design_decision_v1(
            style_variant=_normalize_text(out.get("style_variant")),
            palette_key=_normalize_text(out.get("palette_key")),
            theme_recipe=_normalize_text(out.get("theme_recipe")),
            tone=_normalize_text(out.get("tone")),
            template_family=_normalize_text(out.get("template_family")),
            quality_profile=_normalize_text(out.get("quality_profile")),
            route_mode=_normalize_text(out.get("route_mode")),
            skill_profile=_normalize_text(out.get("skill_profile")),
            slides=out.get("slides") if isinstance(out.get("slides"), list) else [],
            decision_source=decision_source,
            decision_trace=decision_trace,
        )
    out["design_decision_v1"] = normalized
    if isinstance(out.get("slides"), list):
        out["slides"] = apply_design_decision_to_slides(out["slides"], normalized)
    for field in ("style_variant", "palette_key", "theme_recipe", "tone", "template_family", "skill_profile"):
        current = _normalize_text(out.get(field))
        if current and not _is_auto(current):
            continue
        decided = decision_deck_value(normalized, field, "")
        if decided and not _is_auto(decided):
            out[field] = decided
    return out


def freeze_retry_visual_identity(
    slides: List[Dict[str, Any]],
    decision: Mapping[str, Any] | None,
) -> List[Dict[str, Any]]:
    normalized = normalize_design_decision_v1(decision)
    prefilled = apply_design_decision_to_slides(
        [dict(raw) for raw in (slides or []) if isinstance(raw, Mapping)],
        normalized,
    )
    deck = normalized.get("deck") if isinstance(normalized.get("deck"), Mapping) else {}
    style_variant = _normalize_text(deck.get("style_variant"))
    palette_key = _normalize_text(deck.get("palette_key"))
    theme_recipe = _normalize_text(deck.get("theme_recipe"))
    tone = _normalize_text(deck.get("tone"))
    template_family = _normalize_text(deck.get("template_family"))
    skill_profile = _normalize_text(deck.get("skill_profile"))
    out: List[Dict[str, Any]] = []
    for raw in prefilled:
        slide = deepcopy(dict(raw))
        if style_variant:
            slide["style_variant"] = style_variant
        if palette_key:
            slide["palette_key"] = palette_key
        if theme_recipe:
            slide["theme_recipe"] = theme_recipe
        if tone:
            slide["tone"] = tone
        if template_family:
            slide["template_family"] = template_family
            slide["template_id"] = template_family
        if skill_profile and not _normalize_text(slide.get("skill_profile")):
            slide["skill_profile"] = skill_profile
        out.append(slide)
    return out


