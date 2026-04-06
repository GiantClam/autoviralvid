"""Deterministic layout solver for archetype slot capacity checks.

Phase-T2 objective:
- provide explicit overflow/underflow diagnostics per slide
- expose fixed action ladders to avoid opaque random retries
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

_TEXTUAL_BLOCK_TYPES = {
    "title",
    "subtitle",
    "text",
    "body",
    "list",
    "quote",
    "icon_text",
    "comparison",
}
_VISUAL_BLOCK_TYPES = {"image", "chart", "kpi", "table", "workflow", "diagram"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_spec_path() -> Path:
    return Path(__file__).resolve().parent / "ppt_specs" / "archetype-slot-spec.json"


def load_archetype_slot_spec(path: Path | None = None) -> Dict[str, Any]:
    target = Path(path or _default_spec_path())
    if not target.exists():
        return {"default": {"text_slots": 2, "min_text_blocks": 1, "max_text_blocks": 4, "char_capacity_per_slot": 90}}
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {"default": {"text_slots": 2, "min_text_blocks": 1, "max_text_blocks": 4, "char_capacity_per_slot": 90}}
    if isinstance(parsed, dict):
        return parsed
    return {"default": {"text_slots": 2, "min_text_blocks": 1, "max_text_blocks": 4, "char_capacity_per_slot": 90}}


def _block_type(block: Dict[str, Any]) -> str:
    return str(block.get("block_type") or block.get("type") or "").strip().lower()


def _extract_block_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, (int, float)):
        return str(content)
    if isinstance(content, list):
        values = [_extract_block_text(item) for item in content]
        return " ".join(item for item in values if item).strip()
    if isinstance(content, dict):
        pieces: List[str] = []
        for key in ("title", "label", "value", "text", "content", "description", "summary"):
            value = content.get(key)
            if value is None:
                continue
            txt = _extract_block_text(value)
            if txt:
                pieces.append(txt)
        return " ".join(pieces).strip()
    return ""


def solve_slide_layout(
    slide: Dict[str, Any],
    *,
    archetype: str | None = None,
    slot_spec: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    spec = slot_spec or load_archetype_slot_spec()
    archetype_name = str(archetype or slide.get("archetype") or "").strip().lower()
    archetype_cfg = spec.get(archetype_name) if isinstance(spec, dict) else None
    if not isinstance(archetype_cfg, dict):
        archetype_cfg = spec.get("default") if isinstance(spec, dict) else None
    if not isinstance(archetype_cfg, dict):
        archetype_cfg = {}

    text_slots = max(1, int(archetype_cfg.get("text_slots") or 2))
    min_text_blocks = max(1, int(archetype_cfg.get("min_text_blocks") or 1))
    max_text_blocks = max(min_text_blocks, int(archetype_cfg.get("max_text_blocks") or 4))
    char_capacity_per_slot = max(40, int(archetype_cfg.get("char_capacity_per_slot") or 90))
    total_char_capacity = text_slots * char_capacity_per_slot

    blocks = slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
    text_blocks = []
    visual_block_count = 0
    total_text_chars = 0
    for raw in blocks:
        if not isinstance(raw, dict):
            continue
        bt = _block_type(raw)
        if bt in _VISUAL_BLOCK_TYPES:
            visual_block_count += 1
        if bt not in _TEXTUAL_BLOCK_TYPES or bt == "title":
            continue
        text_blocks.append(raw)
        total_text_chars += len(_extract_block_text(raw.get("content")))

    overflow_actions: List[str] = []
    underflow_actions: List[str] = []
    status = "ok"
    recommended_variant = "balanced"

    if len(text_blocks) > max_text_blocks or total_text_chars > total_char_capacity:
        status = "overflow"
        recommended_variant = "dense"
        overflow_actions.append("compress_text")
        if len(text_blocks) > max_text_blocks + 1 or total_text_chars > int(total_char_capacity * 1.35):
            overflow_actions.append("downgrade_layout_density")
    elif len(text_blocks) < min_text_blocks or total_text_chars < int(total_char_capacity * 0.30):
        status = "underflow"
        recommended_variant = "airy"
        if visual_block_count <= 0:
            underflow_actions.append("add_visual_anchor")

    return {
        "status": status,
        "archetype": archetype_name or "default",
        "metrics": {
            "text_slots": text_slots,
            "min_text_blocks": min_text_blocks,
            "max_text_blocks": max_text_blocks,
            "char_capacity_per_slot": char_capacity_per_slot,
            "total_char_capacity": total_char_capacity,
            "text_block_count": len(text_blocks),
            "total_text_chars": total_text_chars,
            "visual_block_count": visual_block_count,
        },
        "recommended_variant": recommended_variant,
        "overflow_actions": overflow_actions,
        "underflow_actions": underflow_actions,
    }
