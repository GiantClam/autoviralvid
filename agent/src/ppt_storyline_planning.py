"""Generic storyline planning helpers driven by research key points."""

from __future__ import annotations

import re
from typing import Dict, List, Sequence

from src.schemas.ppt_outline import StickyNote


_NAVIGATION_TOKENS = {
    "classroom",
    "teaching",
    "education",
    "lesson",
    "school",
    "student",
    "training",
    "课堂",
    "教学",
    "教育",
    "课程",
    "高中",
    "学生",
    "教师",
}

_BOILERPLATE_PREFIXES = {
    "先说明",
    "再交代",
    "最后解释",
    "梳理围绕",
    "拆解",
    "说明",
    "指出",
    "讨论",
}


def is_instructional_context(context_blob: str) -> bool:
    blob = str(context_blob or "").lower()
    return any(token in blob for token in _NAVIGATION_TOKENS)


def _extract_topic_seed(topic: str) -> str:
    text = str(topic or "").strip()
    m = re.search(r"主题为[“\"](.+?)[”\"]", text)
    if m:
        return str(m.group(1) or "").strip()
    return text


def _normalize_point(value: str, fallback: str) -> str:
    text = str(value or "").strip()
    return text[:30] if text else fallback[:30]


def _dedupe_points(data_points: Sequence[str], topic_seed: str) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in list(data_points or []) + [topic_seed]:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text[:120])
    return out


def _semantic_profile(point: str) -> dict:
    text = str(point or "")
    lower = text.lower()
    if any(token in text for token in ("定义", "背景", "概念", "是什么")):
        return {"layout": "split_2", "density": "medium", "elements": ["definition", "list"], "anchor": "concept"}
    if any(token in text for token in ("参与方", "角色", "职责", "主体", "要素")):
        return {"layout": "asymmetric_2", "density": "medium", "elements": ["roles", "comparison", "list"], "anchor": "roles"}
    if any(token in text for token in ("流程", "步骤", "阶段", "路径", "机制", "结构")):
        return {"layout": "split_2", "density": "medium", "elements": ["process", "timeline", "list"], "anchor": "process"}
    if any(token in text for token in ("案例", "证据", "数据", "实证", "example", "case")):
        return {"layout": "bento_5", "density": "medium", "elements": ["case", "evidence", "image"], "anchor": "case"}
    if any(token in text for token in ("影响", "联系", "启示", "意义", "作用", "impact")):
        return {"layout": "split_2", "density": "medium", "elements": ["insight", "list"], "anchor": "impact"}
    if any(token in text for token in ("争议", "风险", "约束", "挑战", "趋势", "未来", "risk", "trend")):
        return {"layout": "asymmetric_2", "density": "medium", "elements": ["trend", "insight", "list"], "anchor": "trend"}
    return {"layout": "split_2", "density": "medium", "elements": ["list", "insight"], "anchor": "text"}


def _split_subject_focus(text: str) -> tuple[str, str]:
    value = str(text or "").strip()
    if not value:
        return "主题", ""
    parts = re.split(r"[：:]", value, maxsplit=1)
    if len(parts) > 1:
        return parts[0].strip(), parts[1].strip()
    m = re.search(r"(.+?)在(.+?)中的(.+)$", value)
    if m:
        subject = str(m.group(1) or "").strip()
        focus = " ".join(str(item or "").strip() for item in m.groups()[1:] if str(item or "").strip())
        return subject, focus
    m = re.search(r"(.+?)的(.+)$", value)
    if m:
        return str(m.group(1) or "").strip(), str(m.group(2) or "").strip()
    return value, ""


def _compact_focus_seed(text: str) -> str:
    value = str(text or "").strip(" ：:")
    if not value:
        return ""
    value = re.sub(r"^(理解|认识|解码|解析|探究|把握|观察|说明|分析|其对|它对|关于)\s*", "", value)
    value = re.sub(r"^(如何|怎样|为什么)\s*", "", value)
    value = re.sub(r"的(影响|意义|作用|启示|联系|路径)$", "", value)
    value = re.sub(r"^(对|在)\s*", "", value)
    return value.strip(" ：:")


def _dedupe_point_rows(rows: Sequence[str], title: str = "") -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    title_key = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(title or "").lower())
    for raw in rows:
        text = str(raw or "").strip()
        if not text:
            continue
        key = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", text.lower())
        if not key or key in seen:
            continue
        if key == title_key:
            continue
        seen.add(key)
        out.append(text[:120])
    return out


def build_instructional_topic_points(topic_seed: str, *, prefer_zh: bool) -> List[str]:
    subject, focus = _split_subject_focus(topic_seed)
    subject = _compact_focus_seed(subject) or subject
    focus_seed = _compact_focus_seed(focus)
    if prefer_zh:
        rows = [
            f"什么是{subject}",
            f"{subject}的关键阶段",
            f"{subject}中的主要角色",
            f"{subject}的核心规则与程序",
            f"{subject}如何影响{focus_seed}" if focus_seed else f"{subject}的现实影响",
            f"与{subject}相关的案例与证据",
            f"{subject}中的争议与思考",
        ]
    else:
        rows = [
            f"What is {subject}",
            f"Key stages of {subject}",
            f"Main actors in {subject}",
            f"Rules and procedures behind {subject}",
            f"How {subject} shapes {focus_seed}" if focus_seed else f"Real-world impact of {subject}",
            f"Cases and evidence around {subject}",
            f"Debates and takeaways on {subject}",
        ]
    return _dedupe_point_rows(rows, title=topic_seed)


def build_research_storyline_notes(
    *,
    topic: str,
    total_pages: int,
    data_points: Sequence[str],
    page_anchors: Dict[int, str] | None = None,
    instructional_context: bool = False,
) -> List[StickyNote]:
    page_anchors = page_anchors or {}
    topic_seed = _extract_topic_seed(topic)
    points = _dedupe_points(data_points, topic_seed)
    prefer_zh = bool(re.search(r"[\u4e00-\u9fff]", topic_seed))
    navigation_title = "内容导航" if prefer_zh else "Table of Contents"
    ending_title = "总结与启示" if prefer_zh else "Summary & Takeaways"

    slots = total_pages - 2
    use_navigation = total_pages >= 8
    if use_navigation:
        slots -= 1

    middle_points = points[: max(0, slots)]
    if len(middle_points) < slots:
        fillers = (
            build_instructional_topic_points(topic_seed, prefer_zh=prefer_zh)
            if instructional_context
            else [
                f"{topic_seed}的核心概念",
                f"{topic_seed}的关键机制",
                f"{topic_seed}的代表性案例",
                f"{topic_seed}的趋势与挑战",
                f"{topic_seed}的总结与启示",
            ]
        )
        for filler in fillers:
            if len(middle_points) >= slots:
                break
            if filler not in middle_points:
                middle_points.append(filler)

    notes: List[StickyNote] = [
        StickyNote(
            page_number=1,
            core_message=_normalize_point(str(page_anchors.get(1) or topic_seed), topic_seed),
            layout_hint="cover",
            content_density="low",
            data_elements=[],
            visual_anchor="title",
            key_points=points[:3] if len(points) >= 3 else [topic_seed, topic_seed, topic_seed],
            speaker_notes=str(topic_seed)[:200],
        )
    ]

    page_number = 2
    if use_navigation:
        notes.append(
            StickyNote(
                page_number=page_number,
                core_message=_normalize_point(str(page_anchors.get(page_number) or navigation_title), navigation_title),
                layout_hint="asymmetric_2",
                content_density="low",
                data_elements=["toc", "agenda"],
                visual_anchor="toc",
                key_points=middle_points[:6] if len(middle_points) >= 3 else points[:6],
                speaker_notes=("先看课程地图，再进入概念、机制、案例与思考。" if prefer_zh else "Start with the lesson map, then move through concepts, mechanisms, cases, and reflection.")[:200],
            )
        )
        page_number += 1

    for point in middle_points:
        if page_number >= total_pages:
            break
        profile = _semantic_profile(point)
        evidence = []
        for candidate in points:
            if candidate == point:
                continue
            evidence.append(candidate)
            if len(evidence) >= 3:
                break
        while len(evidence) < 3:
            evidence.append(point)
        notes.append(
            StickyNote(
                page_number=page_number,
                core_message=_normalize_point(str(page_anchors.get(page_number) or point), point),
                layout_hint=profile["layout"],
                content_density=profile["density"],
                data_elements=list(profile["elements"]),
                visual_anchor=str(profile["anchor"]),
                key_points=evidence[:3],
                speaker_notes=str(point)[:200],
            )
        )
        page_number += 1

    while page_number < total_pages:
        notes.append(
            StickyNote(
                page_number=page_number,
                core_message=_normalize_point(str(page_anchors.get(page_number) or (points[-1] if points else topic_seed)), topic_seed),
                layout_hint="split_2",
                content_density="medium",
                data_elements=["list", "insight"],
                visual_anchor="text",
                key_points=(points[-3:] if len(points) >= 3 else [topic_seed, topic_seed, topic_seed]),
                speaker_notes=(points[-1] if points else topic_seed)[:200],
            )
        )
        page_number += 1

    notes.append(
        StickyNote(
            page_number=total_pages,
            core_message=_normalize_point(str(page_anchors.get(total_pages) or ending_title), ending_title),
            layout_hint="summary",
            content_density="low",
            data_elements=["summary", "action" if not instructional_context else "question"],
            visual_anchor="summary",
            key_points=(points[-3:] if len(points) >= 3 else [topic_seed, topic_seed, topic_seed]),
            speaker_notes=ending_title[:200],
        )
    )

    layout_rotation = ["split_2", "asymmetric_2", "bento_5", "timeline", "grid_3"]
    normalized_notes: List[StickyNote] = []
    for idx, note in enumerate(notes):
        updated = note
        if idx > 0 and note.layout_hint == normalized_notes[-1].layout_hint:
            for candidate in layout_rotation:
                prev_layout = normalized_notes[-1].layout_hint
                next_layout = notes[idx + 1].layout_hint if idx + 1 < len(notes) else "summary"
                if candidate in {prev_layout, next_layout}:
                    continue
                updated = note.model_copy(update={"layout_hint": candidate})
                break
        normalized_notes.append(updated)
    return normalized_notes


def expand_semantic_support_points(
    *,
    core_message: str,
    related_points: Sequence[str] | None = None,
    instructional_context: bool = False,
) -> List[str]:
    title = str(core_message or "").strip()
    related = [str(item or "").strip() for item in (related_points or []) if str(item or "").strip()]
    profile = _semantic_profile(title)
    anchor = str(profile.get("anchor") or "text")
    subject, focus = _split_subject_focus(title)
    subject = _compact_focus_seed(subject) or subject
    focus_seed = _compact_focus_seed(focus)

    if instructional_context:
        if anchor == "concept":
            base = [
                f"概念边界：{subject}指什么，不包括什么",
                f"核心问题：{subject}通常包含哪些关键环节",
                f"课堂提示：为什么先理解{subject}再讨论后续影响",
            ]
        elif anchor == "roles":
            base = [
                f"关键主体：谁会参与或影响{subject}",
                "角色分工：不同主体分别掌握哪些权力、责任或资源",
                "互动关系：主体之间如何合作、博弈或相互制衡",
            ]
        elif anchor == "process":
            base = [
                f"起点：{subject}通常从哪里开始",
                "推进：哪些程序决定它能否继续向前",
                "转折点：哪个环节最可能改变最终结果",
            ]
        elif anchor == "impact":
            target = focus_seed or "更广泛环境"
            base = [
                f"传导起点：{subject}先改变哪些规则、预期或利益分配",
                f"外部影响：这些变化如何进一步传导到{target}",
                "反馈效应：外部变化又会怎样反过来影响原有规则",
            ]
        elif anchor == "case":
            base = [
                f"案例背景：哪一个事件最能说明{subject}",
                "关键证据：从规则、数据或结果里抓住最重要的信息",
                "课堂结论：这个案例说明了什么共性机制",
            ]
        elif anchor == "trend":
            base = [
                f"争议焦点：围绕{subject}最大的分歧是什么",
                "现实约束：推进过程中最难突破的限制来自哪里",
                "延伸思考：未来变化最可能从哪些方向出现",
            ]
        else:
            base = [
                f"核心信息：关于{subject}最值得记住的是什么",
                "逻辑关系：这些信息之间如何构成因果或递进结构",
                "结论提示：这一页最终要回答哪个关键问题",
            ]
    else:
        if anchor == "concept":
            base = [
                f"定义边界：{subject}指向什么、排除什么",
                f"形成背景：{subject}为何会成为当前讨论重点",
                f"理解价值：把{subject}放回整体脉络会更容易判断后续影响",
            ]
        elif anchor == "roles":
            base = [
                f"主体识别：围绕{subject}最关键的参与方是谁",
                "职责分配：不同主体分别负责提出、推动或约束什么",
                "关系结构：主体互动如何塑造最终结果",
            ]
        elif anchor == "process":
            base = [
                f"结构拆解：{subject}包含哪些主要阶段",
                "衔接逻辑：前后环节如何推动结果逐步成形",
                "关键节点：哪一步最可能带来方向性变化",
            ]
        elif anchor == "impact":
            target = focus_seed or "外部环境"
            base = [
                f"作用路径：{subject}先影响内部规则，再传导到{target}",
                "影响层次：区分直接后果、间接后果与反馈效应",
                "结果映射：把机制变化和现实结果一一对应起来",
            ]
        elif anchor == "case":
            base = [
                f"典型案例：选择最能解释{subject}的一组事实材料",
                "证据抓手：优先保留能支撑核心判断的数据或现象",
                "迁移启示：案例之外还能得到什么一般性结论",
            ]
        elif anchor == "trend":
            base = [
                f"当前争议：围绕{subject}仍然没有达成共识的部分是什么",
                "现实约束：有哪些限制会影响推进节奏和效果",
                "后续趋势：未来最值得持续观察的新变量是什么",
            ]
        else:
            base = [
                f"关键判断：关于{subject}这一页真正要回答的问题是什么",
                "证据结构：把概念、事实和结论整理成清晰顺序",
                "逻辑关系：避免标题复述，突出因果、对比或递进",
            ]

    merged = _dedupe_point_rows([*related, *base], title=title)
    filtered = [
        item for item in merged
        if not any(item.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES)
    ]
    return (filtered or merged or [title])[:4]
