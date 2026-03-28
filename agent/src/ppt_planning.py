"""Planning helpers for sticky-note outline layout recommendation."""

from __future__ import annotations

import math
from collections import Counter
from typing import List

from src.schemas.ppt_outline import LayoutType, StickyNote


MIDDLE_LAYOUTS: List[LayoutType] = [
    "split_2",
    "asymmetric_2",
    "grid_3",
    "grid_4",
    "bento_5",
    "bento_6",
    "timeline",
]


def recommend_layout(note: StickyNote, position_in_deck: int, total_pages: int) -> LayoutType:
    """Recommend layout by content properties and deck position."""
    if position_in_deck <= 0:
        return "cover"
    if position_in_deck >= max(0, total_pages - 1):
        return "summary"

    data_count = len(note.data_elements or [])
    if data_count >= 4:
        return "bento_6"
    if data_count == 3:
        return "grid_3"

    msg = str(note.core_message or "").lower()
    if any(token in msg for token in ("对比", "vs", "比较", "优劣", "before", "after", "benchmark")):
        return "split_2"
    if any(token in msg for token in ("时间", "历程", "流程", "步骤", "阶段", "timeline", "roadmap")):
        return "timeline"
    if any(token in msg for token in ("四", "象限", "维度", "swot", "matrix", "quadrant")):
        return "grid_4"

    density = str(note.content_density or "medium").lower()
    if density == "high":
        return "bento_5"
    if density == "low":
        return "asymmetric_2"
    return "split_2"


def enforce_layout_diversity(
    layouts: List[LayoutType],
    *,
    max_type_ratio: float = 0.45,
    min_layout_variety_for_long: int = 4,
) -> List[LayoutType]:
    """Post-process layouts to avoid adjacent repeats and over-dominance."""
    if len(layouts) <= 2:
        return list(layouts)

    out = list(layouts)
    total = len(out)
    middle_start = 1
    middle_end = total - 1
    limit = max(1, math.floor(total * max(0.1, min(1.0, max_type_ratio))))

    def _pick_replacement(idx: int, blocked: set[str]) -> LayoutType:
        counts = Counter(out)
        candidates = sorted(
            MIDDLE_LAYOUTS,
            key=lambda name: (counts.get(name, 0), MIDDLE_LAYOUTS.index(name)),
        )
        for candidate in candidates:
            if candidate in blocked:
                continue
            prev_layout = out[idx - 1] if idx - 1 >= 0 else ""
            next_layout = out[idx + 1] if idx + 1 < total else ""
            if candidate == prev_layout or candidate == next_layout:
                continue
            return candidate
        # deterministic fallback
        return "split_2"

    # Rule 1: adjacent layouts cannot repeat in middle slides.
    for idx in range(middle_start, middle_end):
        prev_layout = out[idx - 1]
        cur_layout = out[idx]
        if cur_layout != prev_layout:
            continue
        out[idx] = _pick_replacement(idx, blocked={cur_layout})

    # Rule 2: any one layout type ratio should not exceed limit.
    while True:
        counts = Counter(out)
        dominant = None
        for name, count in counts.items():
            if count > limit:
                dominant = name
                break
        if not dominant:
            break
        changed = False
        for idx in range(middle_start, middle_end):
            if out[idx] != dominant:
                continue
            out[idx] = _pick_replacement(idx, blocked={dominant})
            changed = True
            counts = Counter(out)
            if counts.get(dominant, 0) <= limit:
                break
        if not changed:
            break

    # Rule 3: long decks should use enough distinct middle layouts.
    if total >= 10:
        current_middle = out[middle_start:middle_end]
        current_set = set(current_middle)
        need = max(1, int(min_layout_variety_for_long)) - len(current_set)
        if need > 0:
            missing = [name for name in MIDDLE_LAYOUTS if name not in current_set]
            idx_candidates = [
                idx
                for idx in range(middle_start, middle_end)
                if out[idx] in current_set
            ]
            idx_candidates.sort(key=lambda i: Counter(current_middle).get(out[i], 0), reverse=True)
            cursor = 0
            for layout_name in missing:
                if need <= 0 or cursor >= len(idx_candidates):
                    break
                idx = idx_candidates[cursor]
                cursor += 1
                out[idx] = _pick_replacement(idx, blocked=set())
                if out[idx] != layout_name:
                    out[idx] = layout_name
                need -= 1

    # Final guard: no adjacent duplicates in entire deck.
    for idx in range(1, total):
        if out[idx] == out[idx - 1] and middle_start <= idx < middle_end:
            out[idx] = _pick_replacement(idx, blocked={out[idx]})
    return out

