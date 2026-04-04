"""Planning helpers for sticky-note outline layout recommendation."""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from collections import Counter
from typing import Any, Dict, List

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

_TEXT_BLOCK_TYPES = {"title", "subtitle", "body", "list", "quote", "icon_text", "text"}
_VISUAL_BLOCK_TYPES = {"image", "chart", "kpi", "workflow", "diagram", "table"}
_SENTENCE_SPLIT_RE = re.compile(r"[;；。！？!?，,、\n\r]+")
_BULLET_PREFIX_RE = re.compile(r"^[\s\-*+•·●○◆▶✓]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_DIGIT_RE = re.compile(r"\d")
_GENERIC_TITLE_KEYS = {
    "market analysis",
    "analysis",
    "overview",
    "summary",
    "introduction",
    "product features",
    "market",
    "strategy",
    "市场分析",
    "市场机会",
    "产品特性",
    "产品能力",
    "产品方案",
    "业务概览",
    "总结",
    "方案能力",
}
_ASSERTIVE_HINTS_ZH = {"提升", "增长", "下降", "降低", "实现", "超过", "达成", "驱动", "突破", "改善"}
_ASSERTIVE_HINTS_EN = {"increase", "decrease", "reduce", "grow", "improve", "reach", "drive", "boost", "cut"}
_DENSITY_HINT_BY_LAYOUT = {
    "grid_4": "high",
    "bento_5": "high",
    "bento_6": "high",
    "grid_3": "medium",
    "split_2": "medium",
    "asymmetric_2": "medium",
    "timeline": "medium",
    "hero_1": "low",
    "cover": "breathing",
    "summary": "breathing",
    "section": "breathing",
    "divider": "breathing",
}
_SVG_ROUTE_ELEMENTS = {"workflow", "diagram", "sankey", "funnel", "waterfall", "matrix"}
_HIGH_DENSITY_LAYOUTS = {"grid_4", "bento_5", "bento_6"}
_MEDIUM_DENSITY_LAYOUTS = {"grid_3", "split_2", "asymmetric_2", "timeline"}
_LOW_DENSITY_LAYOUTS = {"hero_1"}
_BREATHING_LAYOUTS = {"section", "cover", "summary", "divider"}
_DENSITY_DOWNGRADE_MAP: Dict[str, LayoutType] = {
    "bento_6": "split_2",
    "bento_5": "grid_3",
    "grid_4": "grid_3",
    "grid_3": "asymmetric_2",
    "timeline": "split_2",
    "split_2": "hero_1",
    "asymmetric_2": "hero_1",
}


@dataclass
class SlideContentStrategy:
    assertion: str
    evidence: List[str]
    data_anchor: str
    page_role: str
    density_hint: str
    render_path: str


def _norm_text_key(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%+.-]", "", str(value or "").strip().lower())


def _is_text_heavy_slide(slide: Dict[str, Any]) -> bool:
    slide_type = str(slide.get("slide_type") or slide.get("page_type") or "").strip().lower()
    if slide_type in {"cover", "toc", "summary", "section", "divider", "hero_1"}:
        return False
    layout = str(slide.get("layout_grid") or slide.get("layout") or "").strip().lower()
    if layout == "hero_1":
        return False
    return True


def _collect_block_text(block: Dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        parts: List[str] = []
        for key in ("text", "body", "content", "title", "label", "caption", "description"):
            val = str(content.get(key) or "").strip()
            if val:
                parts.append(val)
        return " ".join(parts)
    return ""


def _split_bullet_candidates(text: str) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    out: List[str] = []
    for seg in _SENTENCE_SPLIT_RE.split(raw):
        item = _BULLET_PREFIX_RE.sub("", str(seg or "").strip())
        if len(item) < 2:
            continue
        limit = 72 if _CJK_RE.search(item) else 120
        remaining = item
        while len(remaining) > limit:
            split_at = max(
                remaining.rfind(" ", 0, limit + 1),
                remaining.rfind("，", 0, limit + 1),
                remaining.rfind(",", 0, limit + 1),
                remaining.rfind("、", 0, limit + 1),
            )
            if split_at < max(12, int(limit * 0.45)):
                split_at = limit
            chunk = remaining[:split_at].strip(" ，,、;；")
            if len(chunk) >= 2:
                out.append(chunk)
            remaining = remaining[split_at:].strip(" ，,、;；")
        if len(remaining) >= 2:
            out.append(remaining)
    dedup: List[str] = []
    seen = set()
    for item in out:
        key = _norm_text_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    return dedup


def _chunk_bullets(
    bullets: List[str],
    *,
    max_bullets_per_slide: int,
    max_chars_per_slide: int,
    max_continuation_pages: int,
) -> List[List[str]]:
    chunks: List[List[str]] = []
    current: List[str] = []
    current_chars = 0
    for bullet in bullets:
        bullet_len = max(1, len(str(bullet)))
        should_roll = (
            current
            and (
                len(current) >= max_bullets_per_slide
                or (current_chars + bullet_len) > max_chars_per_slide
            )
        )
        if should_roll:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(str(bullet))
        current_chars += bullet_len
    if current:
        chunks.append(current)
    if not chunks:
        return []
    cap = max(1, int(max_continuation_pages))
    if len(chunks) <= cap:
        return chunks
    merged = chunks[: cap - 1]
    tail: List[str] = []
    for rest in chunks[cap - 1 :]:
        tail.extend(rest)
    if len(tail) > max_bullets_per_slide:
        clipped = tail[: max_bullets_per_slide]
        last = clipped[-1]
        if not str(last).endswith("..."):
            clipped[-1] = f"{str(last)[: max(2, len(str(last)) - 3)]}..."
        tail = clipped
    merged.append(tail)
    return merged


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


def density_level_for_layout(layout: str) -> str:
    normalized = str(layout or "").strip().lower()
    if normalized in _HIGH_DENSITY_LAYOUTS:
        return "high"
    if normalized in _LOW_DENSITY_LAYOUTS:
        return "low"
    if normalized in _BREATHING_LAYOUTS:
        return "breathing"
    return "medium"


def _downgrade_layout(layout: LayoutType, *, target_levels: set[str]) -> LayoutType:
    current = str(layout or "").strip().lower() or "split_2"
    visited = {current}
    while density_level_for_layout(current) not in target_levels:
        nxt = _DENSITY_DOWNGRADE_MAP.get(current)
        if not nxt:
            break
        current = str(nxt).strip().lower()
        if current in visited:
            break
        visited.add(current)
    return current  # type: ignore[return-value]


def enforce_density_rhythm(
    layouts: List[LayoutType],
    *,
    max_consecutive_high: int = 2,
    window_size: int = 5,
    require_low_or_breathing_per_window: int = 1,
) -> List[LayoutType]:
    """Enforce deck-wide density cadence.

    Hard rules:
    1) No 3 consecutive high-density layouts.
    2) Every 5 middle pages should include at least one low/breathing page.
    """
    if len(layouts) <= 2:
        return list(layouts)

    out = [str(item or "").strip().lower() or "split_2" for item in layouts]
    middle_start = 1
    middle_end = len(out) - 1
    if middle_end <= middle_start:
        return out  # type: ignore[return-value]

    max_high = max(1, int(max_consecutive_high))
    seq = 0
    for idx in range(middle_start, middle_end):
        level = density_level_for_layout(out[idx])
        if level == "high":
            seq += 1
        else:
            seq = 0
        if seq <= max_high:
            continue
        out[idx] = _downgrade_layout(out[idx], target_levels={"medium", "low", "breathing"})
        seq = 0 if density_level_for_layout(out[idx]) != "high" else 1

    win = max(2, int(window_size))
    required = max(1, int(require_low_or_breathing_per_window))
    changed = True
    while changed:
        changed = False
        for start in range(middle_start, middle_end):
            end = min(middle_end, start + win)
            if end - start < win:
                break
            window_levels = [density_level_for_layout(out[pos]) for pos in range(start, end)]
            have_low = sum(1 for level in window_levels if level in {"low", "breathing"})
            if have_low >= required:
                continue

            candidate_positions = list(range(start, end))
            candidate_positions.sort(
                key=lambda pos: (density_level_for_layout(out[pos]) != "high", -pos),
            )
            for pos in candidate_positions:
                downgraded = _downgrade_layout(out[pos], target_levels={"low", "breathing"})
                if density_level_for_layout(downgraded) not in {"low", "breathing"}:
                    continue
                prev_layout = out[pos - 1] if pos - 1 >= 0 else ""
                next_layout = out[pos + 1] if pos + 1 < len(out) else ""
                if downgraded == prev_layout or downgraded == next_layout:
                    continue
                if downgraded == out[pos]:
                    continue
                out[pos] = downgraded
                changed = True
                break

    return out  # type: ignore[return-value]


def _dedupe_texts(items: List[str], *, limit: int) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in items:
        text = str(raw or "").strip()
        if not text:
            continue
        key = _norm_text_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _is_generic_title(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return normalized in _GENERIC_TITLE_KEYS


def _looks_assertive_title(text: str, *, is_zh: bool) -> bool:
    value = str(text or "").strip()
    if len(value) < 4:
        return False
    lowered = value.lower()
    if _DIGIT_RE.search(value):
        return True
    if is_zh:
        return any(token in value for token in _ASSERTIVE_HINTS_ZH)
    return any(token in lowered for token in _ASSERTIVE_HINTS_EN)


def _pick_data_anchor(items: List[str], *, fallback: str) -> str:
    candidates = [str(item or "").strip() for item in items if str(item or "").strip()]
    for item in candidates:
        if _DIGIT_RE.search(item):
            return item[:140]
    if candidates:
        return candidates[0][:140]
    return str(fallback or "").strip()[:140]


def _infer_page_role(note: StickyNote, lower_elements: List[str]) -> str:
    layout = str(note.layout_hint or "").strip().lower()
    if layout in {"cover"}:
        return "transition"
    if layout in {"summary"}:
        return "summary"
    if {"kpi", "chart", "table"} & set(lower_elements):
        return "evidence"
    if {"timeline", "workflow", "roadmap", "process"} & set(lower_elements):
        return "transition"
    return "argument"


def _infer_render_path(note: StickyNote, lower_elements: List[str]) -> str:
    layout = str(note.layout_hint or "").strip().lower()
    if layout == "timeline":
        return "svg"
    if set(lower_elements) & _SVG_ROUTE_ELEMENTS:
        return "svg"
    return "pptxgenjs"


def _build_assertion_title(
    *,
    core_message: str,
    data_anchor: str,
    page_role: str,
    is_zh: bool,
) -> str:
    core = str(core_message or "").strip()
    anchor = str(data_anchor or "").strip()
    candidates = [core, anchor]
    for item in candidates:
        text = str(item or "").strip()
        if not text:
            continue
        if _is_generic_title(text) and len(text) <= 14:
            continue
        # Root-cause fix: avoid verbose boilerplate title prefixes that
        # repeatedly trigger title clipping and visual monotony.
        return text[:96]

    if page_role == "summary":
        return "总结与行动建议" if is_zh else "Summary and Next Steps"
    if page_role == "transition":
        return "关键流程与机制" if is_zh else "Key Process and Mechanism"
    if page_role == "evidence":
        return "关键证据与案例" if is_zh else "Key Evidence and Cases"
    return "核心观点" if is_zh else "Core Claim"


def build_slide_content_strategy(
    note: StickyNote,
    *,
    is_zh: bool,
    research_points: List[str] | None = None,
) -> SlideContentStrategy:
    lower_elements = [str(item or "").strip().lower() for item in (note.data_elements or []) if str(item or "").strip()]
    page_role = _infer_page_role(note, lower_elements)
    density_hint = _DENSITY_HINT_BY_LAYOUT.get(str(note.layout_hint or "").strip().lower(), "medium")
    render_path = _infer_render_path(note, lower_elements)

    evidence_seed: List[str] = []
    for text in note.key_points or []:
        evidence_seed.extend(_split_bullet_candidates(str(text or "")))
    if not evidence_seed and research_points:
        for text in research_points[:4]:
            evidence_seed.extend(_split_bullet_candidates(str(text or "")))
    if not evidence_seed and note.core_message:
        evidence_seed = [str(note.core_message)]
    evidence = _dedupe_texts(evidence_seed, limit=4)

    data_anchor = _pick_data_anchor(
        [*evidence, *(note.key_points or []), *((research_points or [])[:4])],
        fallback=note.core_message,
    )
    assertion = _build_assertion_title(
        core_message=note.core_message,
        data_anchor=data_anchor,
        page_role=page_role,
        is_zh=is_zh,
    )
    evidence = [
        item
        for item in evidence
        if _norm_text_key(item) and _norm_text_key(item) != _norm_text_key(assertion)
    ]
    if not evidence:
        evidence = [data_anchor] if data_anchor else [assertion]

    return SlideContentStrategy(
        assertion=assertion[:220],
        evidence=evidence[:4],
        data_anchor=data_anchor[:140],
        page_role=page_role,
        density_hint=density_hint,
        render_path=render_path,
    )


def enforce_layout_diversity(
    layouts: List[LayoutType],
    *,
    max_type_ratio: float = 0.45,
    max_top2_ratio: float = 0.65,
    abab_max_run: int = 4,
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
    dominant_guard = 0
    while True:
        dominant_guard += 1
        if dominant_guard > max(8, total * 8):
            break
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

    # Rule 2.5: Top-2 layout combination ratio should not exceed threshold.
    top2_guard = 0
    while True:
        top2_guard += 1
        if top2_guard > max(8, total * 8):
            break
        counts = Counter(out)
        top2 = counts.most_common(2)
        if len(top2) < 2:
            break
        top2_limit = max(2, math.floor(total * max(0.1, min(1.0, max_top2_ratio))))
        dominant_types = {top2[0][0], top2[1][0]}
        if top2[0][1] + top2[1][1] <= top2_limit:
            break
        changed = False
        for idx in range(middle_start, middle_end):
            if out[idx] not in dominant_types:
                continue
            out[idx] = _pick_replacement(idx, blocked=dominant_types)
            changed = True
            counts = Counter(out)
            top2 = counts.most_common(2)
            if len(top2) < 2:
                break
            dominant_types = {top2[0][0], top2[1][0]}
            if top2[0][1] + top2[1][1] <= top2_limit:
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

    # Final guard: break long ABAB alternation loops.
    def _abab_run_length(start: int) -> int:
        if start + 3 >= total:
            return 0
        first = out[start]
        second = out[start + 1]
        if first == second:
            return 0
        cursor = start + 2
        run = 2
        expected = first
        while cursor < total and out[cursor] == expected:
            run += 1
            expected = second if expected == first else first
            cursor += 1
        return run

    run_threshold = max(4, int(abab_max_run))
    for idx in range(middle_start, middle_end):
        if _abab_run_length(idx) < run_threshold:
            continue
        target = min(idx + 2, middle_end - 1)
        out[target] = _pick_replacement(target, blocked={out[idx], out[idx + 1]})
    return out


def enforce_template_family_cohesion(
    families: List[str],
    *,
    locked_mask: List[bool] | None = None,
    max_type_ratio: float = 0.55,
    max_top2_ratio: float = 0.8,
    max_switch_ratio: float = 0.75,
    abab_max_run: int = 6,
) -> List[str]:
    """Reduce per-slide family jitter while preserving locked pages."""
    if len(families) <= 2:
        return list(families)
    out = [str(item or "").strip().lower() for item in families]
    n = len(out)
    if locked_mask is None or len(locked_mask) != n:
        locked = [False] * n
    else:
        locked = [bool(item) for item in locked_mask]
    editable_indices = [idx for idx, is_locked in enumerate(locked) if not is_locked]
    editable_total = len(editable_indices)
    type_limit = max(1, math.floor(editable_total * max(0.1, min(1.0, max_type_ratio)))) if editable_total else 1
    top2_limit = max(2, math.floor(editable_total * max(0.1, min(1.0, max_top2_ratio)))) if editable_total else 2

    def _switch_ratio() -> float:
        if len(editable_indices) <= 1:
            return 0.0
        values = [out[idx] for idx in editable_indices]
        switches = 0
        for i in range(1, len(values)):
            if values[i] != values[i - 1]:
                switches += 1
        return switches / max(1, len(values) - 1)

    def _violates_caps(idx: int, candidate: str) -> bool:
        if not editable_indices:
            return False
        candidate = str(candidate or "").strip().lower()
        values = []
        for i in editable_indices:
            values.append(candidate if i == idx else out[i])
        counts = Counter(values)
        if counts and max(counts.values()) > type_limit:
            return True
        top2 = counts.most_common(2)
        if len(top2) >= 2 and (top2[0][1] + top2[1][1]) > top2_limit:
            return True
        return False

    def _replace_at(idx: int, value: str, *, respect_caps: bool = False) -> bool:
        if idx < 0 or idx >= n or locked[idx]:
            return False
        candidate = str(value or "").strip().lower()
        if not candidate or candidate == out[idx]:
            return False
        if respect_caps and _violates_caps(idx, candidate):
            return False
        out[idx] = candidate
        return True

    # Pass 1: kill high-frequency oscillation patterns first (ABAB).
    threshold = max(4, int(abab_max_run))
    for start in range(0, n - 3):
        first = out[start]
        second = out[start + 1]
        if first == second:
            continue
        run = 2
        expected = first
        cursor = start + 2
        while cursor < n and out[cursor] == expected:
            run += 1
            expected = second if expected == first else first
            cursor += 1
        if run < threshold:
            continue
        pivot = min(start + 2, n - 2)
        if not _replace_at(pivot, out[pivot - 1]):
            _replace_at(pivot, out[min(pivot + 1, n - 1)])

    def _reduce_switches() -> None:
        guard = 0
        switch_limit = max(0.0, min(1.0, max_switch_ratio))
        while _switch_ratio() > switch_limit and guard < n * 6:
            guard += 1
            changed = False
            # Prefer collapsing editable A-B-A patterns.
            for pos in range(1, len(editable_indices) - 1):
                idx = editable_indices[pos]
                prev_idx = editable_indices[pos - 1]
                next_idx = editable_indices[pos + 1]
                if out[prev_idx] == out[next_idx] and out[idx] != out[prev_idx]:
                    out[idx] = out[prev_idx]
                    changed = True
                    break
            if changed:
                continue
            # Fallback: change the rarer side of an editable switch pair.
            counts = Counter(out[idx] for idx in editable_indices) if editable_indices else Counter(out)
            for pos in range(1, len(editable_indices)):
                idx = editable_indices[pos]
                prev_idx = editable_indices[pos - 1]
                if out[idx] == out[prev_idx]:
                    continue
                left = out[prev_idx]
                right = out[idx]
                target_idx = idx if counts[right] <= counts[left] else prev_idx
                target_value = left if target_idx == idx else right
                if _replace_at(target_idx, target_value, respect_caps=True):
                    changed = True
                    break
            if not changed:
                break

    # Pass 2: reduce excessive switching before ratio balancing.
    _reduce_switches()

    # Pass 3: avoid over-concentration in one or top-2 families.
    def _apply_ratio_cap(cap_ratio: float, cap_topk: int) -> None:
        editable_total = len(editable_indices)
        if editable_total <= 1:
            return
        limit = max(1, math.floor(editable_total * max(0.1, min(1.0, cap_ratio))))
        guard = 0
        while True:
            guard += 1
            if guard > max(8, editable_total * 8):
                break
            counts = Counter(out[idx] for idx in editable_indices)
            top = counts.most_common(cap_topk)
            over = sum(count for _, count in top)
            if over <= limit:
                break
            blocked = {name for name, _ in top}
            replacement = None
            for name, _count in counts.most_common()[::-1]:
                if name not in blocked:
                    replacement = name
                    break
            if not replacement:
                break
            changed = False
            for idx in editable_indices:
                if idx <= 0 or idx >= n - 1:
                    continue
                if out[idx] not in blocked:
                    continue
                prev_family = out[idx - 1]
                next_family = out[idx + 1]
                if prev_family == next_family and prev_family not in blocked:
                    out[idx] = prev_family
                else:
                    out[idx] = replacement
                changed = True
                break
            if not changed:
                break

    _apply_ratio_cap(max_type_ratio, 1)
    _apply_ratio_cap(max_top2_ratio, 2)
    # Pass 4: ratio balancing can re-introduce jitter; smooth once more.
    _reduce_switches()
    return out


def paginate_content_overflow(
    slides: List[Dict[str, Any]],
    *,
    max_bullets_per_slide: int = 6,
    max_chars_per_slide: int = 360,
    max_continuation_pages: int = 3,
) -> List[Dict[str, Any]]:
    """Split text-heavy slides into continuation pages to reduce overflow risk."""
    if not slides:
        return []
    expanded: List[Dict[str, Any]] = []
    for index, raw_slide in enumerate(slides):
        slide = copy.deepcopy(raw_slide if isinstance(raw_slide, dict) else {})
        # Idempotency guard: continuation pages should not be split again
        # during retry loops, otherwise page count keeps expanding.
        if (
            slide.get("continuation_of")
            or slide.get("continuation_index") is not None
            or slide.get("continuation_total") is not None
            or slide.get("is_continuation")
        ):
            expanded.append(slide)
            continue
        if not _is_text_heavy_slide(slide):
            expanded.append(slide)
            continue

        blocks = slide.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            expanded.append(slide)
            continue

        text_blocks = [
            b
            for b in blocks
            if isinstance(b, dict) and str(b.get("block_type") or b.get("type") or "").strip().lower() in _TEXT_BLOCK_TYPES
        ]
        text_candidates: List[str] = []
        for block in text_blocks:
            text_candidates.extend(_split_bullet_candidates(_collect_block_text(block)))
        if len(text_candidates) < (max_bullets_per_slide + 1):
            expanded.append(slide)
            continue

        chunks = _chunk_bullets(
            text_candidates,
            max_bullets_per_slide=max(3, int(max_bullets_per_slide)),
            max_chars_per_slide=max(120, int(max_chars_per_slide)),
            max_continuation_pages=max(1, int(max_continuation_pages)),
        )
        if len(chunks) <= 1:
            expanded.append(slide)
            continue

        source_id = str(slide.get("slide_id") or slide.get("id") or f"slide-{index + 1}").strip() or f"slide-{index + 1}"
        title_text = str(slide.get("title") or "").strip() or f"Slide {index + 1}"
        title_block = next(
            (
                copy.deepcopy(b)
                for b in blocks
                if isinstance(b, dict)
                and str(b.get("block_type") or b.get("type") or "").strip().lower() == "title"
            ),
            {
                "block_type": "title",
                "card_id": "title",
                "position": "top",
                "content": title_text,
                "emphasis": [],
            },
        )
        non_text_blocks = [
            copy.deepcopy(b)
            for b in blocks
            if isinstance(b, dict)
            and str(b.get("block_type") or b.get("type") or "").strip().lower() not in _TEXT_BLOCK_TYPES
        ]
        anchor_blocks = [
            copy.deepcopy(b)
            for b in non_text_blocks
            if str(b.get("block_type") or b.get("type") or "").strip().lower() in _VISUAL_BLOCK_TYPES
        ]
        if not anchor_blocks and non_text_blocks:
            anchor_blocks = [copy.deepcopy(non_text_blocks[0])]

        for chunk_idx, chunk in enumerate(chunks):
            new_slide = copy.deepcopy(slide)
            continuation = chunk_idx > 0
            continued_title = title_text
            if continuation:
                continued_title = (
                    f"{title_text}（续）"
                    if _CJK_RE.search(title_text)
                    else f"{title_text} (cont.)"
                )
            title_block_item = copy.deepcopy(title_block)
            title_block_item["content"] = continued_title
            text_block = {
                "block_type": "list",
                "card_id": "list_main" if not continuation else f"list_cont_{chunk_idx + 1}",
                "position": "left" if anchor_blocks else "center",
                "content": ";".join(chunk),
                "emphasis": chunk[:2],
            }
            new_blocks: List[Dict[str, Any]] = [title_block_item]
            if continuation:
                if anchor_blocks:
                    new_blocks.append(copy.deepcopy(anchor_blocks[0]))
            else:
                new_blocks.extend(copy.deepcopy(non_text_blocks))
            new_blocks.append(text_block)

            if continuation:
                new_slide["slide_id"] = f"{source_id}-cont-{chunk_idx + 1}"
            else:
                new_slide["slide_id"] = source_id
            new_slide["title"] = continued_title
            new_slide["blocks"] = new_blocks
            new_slide["continuation_of"] = source_id
            new_slide["continuation_index"] = chunk_idx + 1
            new_slide["continuation_total"] = len(chunks)
            new_slide["is_continuation"] = continuation
            expanded.append(new_slide)

    for idx, slide in enumerate(expanded, start=1):
        slide["page_number"] = idx
    return expanded
