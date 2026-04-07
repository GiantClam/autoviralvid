"""Core storyline planning helpers for research-driven PPT generation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from src.schemas.ppt_outline import StickyNote


_BOILERPLATE_PREFIXES = {
    "先说",
    "再交代",
    "最后",
    "梳理",
    "说明",
    "指出",
    "讨论",
    "核心问题",
    "课堂提示",
    "关键主体",
    "角色分工",
    "互动关系",
    "起点",
    "推进",
    "转折",
    "案例背景",
    "关键证据",
    "课堂结论",
    "争议焦点",
    "现实约束",
    "结论提示",
}


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _normalize_key(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").lower())


def _dedupe_point_rows(rows: Sequence[str], title: str = "") -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    title_key = _normalize_key(title)
    for raw in rows:
        text = str(raw or "").strip()
        if not text:
            continue
        key = _normalize_key(text)
        if not key or key in seen or key == title_key:
            continue
        seen.add(key)
        out.append(text[:120])
    return out


def _extract_topic_seed(topic: str) -> str:
    text = str(topic or "").strip()
    if not text:
        return ""
    quoted = re.findall(r"[\"']([^\"']{3,160})[\"']", text)
    if quoted:
        return max((item.strip() for item in quoted), key=len)
    return text[:120]


def _split_subject_focus(text: str) -> tuple[str, str]:
    value = str(text or "").strip()
    if not value:
        return "主题", ""
    for sep in ("：", ":", "，", ","):
        if sep in value:
            left, right = value.split(sep, 1)
            if left.strip() and right.strip():
                return left.strip(), right.strip()
    m = re.search(r"(.+?)对(.+?)的", value)
    if m:
        return str(m.group(1) or "").strip(), str(m.group(2) or "").strip()
    return value, ""


def _clip_core_message(text: str) -> str:
    return str(text or "").strip()[:30]


def _generic_topic_points(topic_seed: str, *, prefer_zh: bool) -> List[str]:
    subject, focus = _split_subject_focus(topic_seed)
    if prefer_zh:
        rows = [
            f"{subject}的背景与定义",
            f"{subject}的关键机制与结构",
            f"{subject}的主要参与方与角色",
            f"{subject}在国际关系中的影响路径",
            f"{subject}的代表案例与数据证据",
            f"{subject}面临的争议风险与约束",
            f"{(focus or subject)}的结论与启示",
        ]
    else:
        rows = [
            f"Background and definition of {subject}",
            f"Key mechanisms and structure of {subject}",
            f"Main stakeholders and roles in {subject}",
            f"How {subject} influences international relations",
            f"Representative cases and supporting evidence for {subject}",
            f"Risks, tradeoffs, and controversies around {subject}",
            f"Conclusions and implications of {(focus or subject)}",
        ]
    return _dedupe_point_rows(rows, title=topic_seed)


def _semantic_profile(point: str) -> Dict[str, Any]:
    text = str(point or "")
    lower = text.lower()
    if any(token in lower for token in ("what is", "definition", "concept")) or any(
        token in text for token in ("定义", "概念", "背景")
    ):
        return {"layout": "split_2", "elements": ["definition", "list"], "anchor": "concept"}
    if any(token in lower for token in ("actor", "role", "stakeholder")) or any(
        token in text for token in ("角色", "参与", "主体")
    ):
        return {"layout": "asymmetric_2", "elements": ["roles", "comparison", "list"], "anchor": "roles"}
    if any(token in lower for token in ("process", "mechanism", "workflow")) or any(
        token in text for token in ("流程", "机制", "步骤")
    ):
        return {"layout": "timeline", "elements": ["process", "timeline", "list"], "anchor": "process"}
    if any(token in lower for token in ("case", "evidence", "data")) or any(
        token in text for token in ("案例", "证据", "数据")
    ):
        return {"layout": "bento_5", "elements": ["case", "evidence", "image"], "anchor": "case"}
    if any(token in lower for token in ("impact", "implication", "effect")) or any(
        token in text for token in ("影响", "启示", "意义")
    ):
        return {"layout": "split_2", "elements": ["insight", "list"], "anchor": "impact"}
    if any(token in lower for token in ("risk", "debate", "trend")) or any(
        token in text for token in ("风险", "争议", "趋势")
    ):
        return {"layout": "asymmetric_2", "elements": ["trend", "insight", "list"], "anchor": "trend"}
    return {"layout": "split_2", "elements": ["list", "insight"], "anchor": "text"}


def _chunk_key_points(points: List[str], idx: int, *, prefer_zh: bool, topic_seed: str) -> List[str]:
    window = points[idx: idx + 3]
    if len(window) < 3:
        window.extend(points[: max(0, 3 - len(window))])
    if len(window) < 3:
        fallback = (
            ["关键事实", "核心机制", "结论提示"]
            if prefer_zh
            else ["Key fact", "Core mechanism", "Conclusion"]
        )
        window.extend(fallback[: max(0, 3 - len(window))])
    return _dedupe_point_rows(window, title=topic_seed)[:4]


def build_research_storyline_notes(
    *,
    topic: str,
    total_pages: int,
    data_points: Sequence[str],
    page_anchors: Dict[int, str] | None = None,
) -> List[StickyNote]:
    page_anchors = page_anchors or {}
    page_count = max(1, int(total_pages or 1))
    topic_seed = _extract_topic_seed(topic) or "Topic"
    source_points = [str(item or "").strip() for item in (data_points or []) if str(item or "").strip()]
    prefer_zh = _has_cjk(topic_seed) or any(_has_cjk(item) for item in source_points)

    points = _dedupe_point_rows(source_points, title=topic_seed)
    fillers = _generic_topic_points(topic_seed, prefer_zh=prefer_zh)
    for filler in fillers:
        if len(points) >= max(8, page_count):
            break
        if _normalize_key(filler) not in {_normalize_key(p) for p in points}:
            points.append(filler)
    if not points:
        points = [topic_seed]

    navigation_title = "内容导航" if prefer_zh else "Table of Contents"
    summary_title = "总结与启示" if prefer_zh else "Summary & Takeaways"

    notes: List[StickyNote] = []
    notes.append(
        StickyNote(
            page_number=1,
            core_message=_clip_core_message(str(page_anchors.get(1) or topic_seed)),
            layout_hint="cover",
            content_density="low",
            data_elements=[],
            visual_anchor="title",
            key_points=_chunk_key_points(points, 0, prefer_zh=prefer_zh, topic_seed=topic_seed),
            speaker_notes=str(topic_seed)[:200],
        )
    )

    next_page = 2
    use_toc = page_count >= 8
    if use_toc and next_page <= page_count - 1:
        notes.append(
            StickyNote(
                page_number=next_page,
                core_message=_clip_core_message(
                    str(page_anchors.get(next_page) or navigation_title)
                ),
                layout_hint="grid_3",
                content_density="medium",
                data_elements=["toc", "agenda"],
                visual_anchor="toc",
                key_points=_chunk_key_points(points, 0, prefer_zh=prefer_zh, topic_seed=topic_seed),
                speaker_notes="",
            )
        )
        next_page += 1

    middle_end = page_count - 1
    layout_cycle = ["split_2", "asymmetric_2", "hero_1", "grid_3", "split_2", "asymmetric_2"]
    middle_idx = 0
    for page_no in range(next_page, middle_end + 1):
        if page_no == page_count:
            break
        source = points[middle_idx] if middle_idx < len(points) else fillers[middle_idx % len(fillers)]
        core = _clip_core_message(str(page_anchors.get(page_no) or source or topic_seed))
        profile = _semantic_profile(core)
        notes.append(
            StickyNote(
                page_number=page_no,
                core_message=core,
                layout_hint=str(profile.get("layout") or layout_cycle[middle_idx % len(layout_cycle)]),
                content_density="medium",
                data_elements=[str(x) for x in (profile.get("elements") or ["list"])],
                visual_anchor=str(profile.get("anchor") or "text"),
                key_points=_chunk_key_points(points, middle_idx, prefer_zh=prefer_zh, topic_seed=topic_seed),
                speaker_notes=core[:200],
            )
        )
        middle_idx += 1

    if page_count > 1:
        notes.append(
            StickyNote(
                page_number=page_count,
                core_message=_clip_core_message(
                    str(page_anchors.get(page_count) or summary_title)
                ),
                layout_hint="summary",
                content_density="medium",
                data_elements=["summary"],
                visual_anchor="summary",
                key_points=_chunk_key_points(points, max(0, len(points) - 3), prefer_zh=prefer_zh, topic_seed=topic_seed),
                speaker_notes=("归纳核心结论并给出可执行建议。" if prefer_zh else "Summarize key conclusions and provide actionable takeaways.")[:200],
            )
        )

    notes = sorted(notes, key=lambda n: int(n.page_number))
    if len(notes) > page_count:
        notes = notes[:page_count]
    while len(notes) < page_count:
        page_no = len(notes) + 1
        notes.append(
            StickyNote(
                page_number=page_no,
                core_message=_clip_core_message(
                    summary_title if page_no == page_count else topic_seed
                ),
                layout_hint=("summary" if page_no == page_count else "split_2"),
                content_density="medium",
                data_elements=["summary"] if page_no == page_count else ["list"],
                visual_anchor=("summary" if page_no == page_count else "text"),
                key_points=_chunk_key_points(points, 0, prefer_zh=prefer_zh, topic_seed=topic_seed),
                speaker_notes=topic_seed[:200],
            )
        )
    return notes


def expand_semantic_support_points(
    *,
    core_message: str,
    related_points: Sequence[str] | None = None,
) -> List[str]:
    title = str(core_message or "").strip() or "Key message"
    related = _dedupe_point_rows([str(item or "").strip() for item in (related_points or [])], title=title)
    prefer_zh = _has_cjk(title) or any(_has_cjk(item) for item in related)

    base = (
        [
            f"核心信息：{title}",
            f"证据线索：{(related[0] if related else title + '的关键事实')}",
            f"结论提示：从多方视角评估{title}",
        ]
        if prefer_zh
        else [
            f"Core takeaway: {title}",
            f"Evidence cue: {(related[0] if related else 'key facts behind ' + title)}",
            f"Conclusion hint: evaluate {title} from multiple perspectives",
        ]
    )

    merged = _dedupe_point_rows([*related, *base], title=title)
    filtered = [
        item
        for item in merged
        if item and item != title and not any(item.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES)
    ]

    out = (filtered or merged or [title])[:4]
    while len(out) < 3:
        out.append(("补充证据线索" if prefer_zh else "Add one supporting evidence line"))
    return out[:4]

