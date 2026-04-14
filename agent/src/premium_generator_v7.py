"""V7 generator: planner + mapper + strong post-validation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections import Counter
from math import ceil
from typing import Any, Dict, List, Tuple

from src.schemas.ppt_v7 import DialogueLine, PresentationData, SlideAction, SlideData

logger = logging.getLogger("ppt_v7")
MODEL = os.getenv("CONTENT_LLM_MODEL", "openai/gpt-4o-mini")

SLIDE_TYPES: List[str] = [
    "cover",
    "toc",
    "grid_2",
    "grid_3",
    "quote_stat",
    "timeline",
    "divider",
    "summary",
]

_CONTENT_TYPES = ["grid_2", "grid_3", "quote_stat", "timeline"]
_BANNED_PREFIXES = (
    "这一页",
    "在这一页",
    "这张幻灯片",
    "接下来我们看",
    "数据都是实打实的",
    "让我们来看看",
    "如图所示",
)


PLANNER_PROMPT = """你是顶尖商业演示架构师。请输出结构化大纲 JSON。

必须满足:
1) 相邻页 slide_type 不能相同
2) 任一 slide_type 占比不超过总页数 30%
3) 首尾规则: 第1页 cover, 第2页 toc, 最后一页 summary
4) 内容页使用: grid_2 / grid_3 / quote_stat / timeline
5) 每 3-4 页插入 divider 过渡页

输出格式:
{
  "title": "标题",
  "design_system": "tech_blue",
  "slides": [
    {
      "slide_index": 1,
      "slide_type": "grid_2",
      "key_message": "20字以内核心信息",
      "data_points": ["含数字的数据点1", "含数字的数据点2"]
    }
  ]
}
只输出 JSON。"""


MAPPER_PROMPT = """你是高级 Marp 视觉设计师。将结构化页面映射成 Marp + 剧本 + 动效。

要求:
1) markdown 屏幕可见文字 <= 40 字
2) 必须包含 1-2 个 <mark>...</mark>
3) script 使用 host/student 角色，避免模板化开头
4) 每页至少一个 action，支持: highlight/circle/appear_items/zoom_in
5) detailed explanation 放 script，不堆砌在 markdown

输出格式:
{
  "slide_type": "grid_2",
  "markdown": "# 标题\\n\\n- 要点A\\n- 要点B，<mark>340%</mark>",
  "script": [
    {"role":"host","text":"..."},
    {"role":"student","text":"..."}
  ],
  "bg_image_keyword": "industrial automation factory",
  "actions": [
    {"type":"highlight","keyword":"340%","startFrame":24}
  ]
}
只输出 JSON。"""


def _extract_json(text: str) -> Dict[str, Any]:
    raw = (text or "").strip().replace("\ufffd", "")
    if not raw:
        raise ValueError("empty llm response")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    for m in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL):
        chunk = m.group(1).strip()
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue

    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        chunk = raw[start : end + 1]
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"cannot parse json: {raw[:400]}")


_MARKDOWN_HEADING_RE = re.compile(r"(?m)^\s*##+\s*(.+?)\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|(?:\d+[.)、]))\s+(.+?)\s*$")


def _strip_markdown_text(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"[*_#>\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ：:，,。；;")


def _extract_markdown_sections(raw: str) -> List[Tuple[str, str]]:
    matches = list(_MARKDOWN_HEADING_RE.finditer(raw or ""))
    if not matches:
        return []

    sections: List[Tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
        heading = match.group(1).strip()
        body = raw[start:end].strip()
        sections.append((heading, body))
    return sections


def _extract_markdown_label(body: str, labels: List[str]) -> str:
    for raw_line in (body or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        normalized = _strip_markdown_text(line)
        compact = normalized.replace(" ", "").lower()
        for label in labels:
            token = label.replace(" ", "").lower()
            if compact.startswith(token):
                value = normalized[len(label) :].lstrip("：: ").strip()
                if value:
                    return value
    return ""


def _extract_markdown_points(body: str) -> List[str]:
    points: List[str] = []
    for raw_line in (body or "").splitlines():
        line = raw_line.strip()
        if not line or line == "---":
            continue
        bullet = _LIST_ITEM_RE.match(line)
        candidate = bullet.group(1) if bullet else ""
        if not candidate and line.startswith("**") and line.endswith("**"):
            continue
        if not candidate and any(token in line for token in ("- ", "* ", "• ")):
            candidate = line
        candidate = _strip_markdown_text(candidate)
        if len(candidate) < 4:
            continue
        points.append(candidate)

    deduped: List[str] = []
    seen = set()
    for point in points:
        key = point.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(point)
        if len(deduped) >= 5:
            break
    return deduped


def _guess_slide_type_from_markdown(
    heading: str,
    body: str,
    slide_index: int,
    total_sections: int,
    points: List[str],
) -> str:
    heading_text = _strip_markdown_text(heading).lower()
    body_text = _strip_markdown_text(body).lower()
    signal = f"{heading_text} {body_text}"

    if slide_index == 1 or any(token in signal for token in ("封面", "title", "cover")):
        return "cover"
    if slide_index == 2 or any(token in signal for token in ("目录", "agenda", "toc", "contents")):
        return "toc"
    if slide_index == total_sections or any(
        token in signal for token in ("总结", "summary", "conclusion", "结论", "thanks")
    ):
        return "summary"
    if any(token in signal for token in ("过渡", "章节", "section", "divider", "transition")):
        return "divider"
    if any(token in signal for token in ("阶段", "历程", "timeline", "路径", "roadmap")):
        return "timeline"
    if any(token in signal for token in ("观点", "结论", "stat", "quote", "数据")) and points:
        return "quote_stat"
    if len(points) >= 3:
        return "grid_3"
    return "grid_2"


def _markdown_outline_to_plan(raw: str, target_count: int) -> Dict[str, Any]:
    sections = _extract_markdown_sections(raw)
    if not sections:
        raise ValueError("planner response did not contain markdown sections")

    slides: List[Dict[str, Any]] = []
    for ordinal, (heading, body) in enumerate(sections, start=1):
        title = _extract_markdown_label(body, ["标题", "Title", "主题", "Topic", "页面标题"])
        if not title:
            heading_text = _strip_markdown_text(heading)
            title = re.sub(r"^(?:第?\s*\d+\s*[页pP]?[:：.\-、]?\s*)", "", heading_text).strip() or heading_text

        points = _extract_markdown_points(body)
        key_message = (
            _extract_markdown_label(body, ["核心结论", "关键结论", "核心信息", "Key Message", "Main Message"])
            or title
            or f"第{ordinal}页核心观点"
        )
        slide_type = _guess_slide_type_from_markdown(heading, body, ordinal, len(sections), points)
        slides.append(
            {
                "slide_index": ordinal,
                "slide_type": slide_type,
                "key_message": _trim_text(key_message, 32),
                "data_points": [_trim_text(point, 40) for point in points if point][:5],
            }
        )

    plan_title = (
        _extract_markdown_label(raw, ["主题", "Title", "标题"])
        or slides[0]["key_message"]
        or "商业演示文稿"
    )
    logger.warning(
        "[v7] planner returned markdown instead of JSON, recovered %d sections into plan",
        len(slides),
    )
    return {
        "title": _trim_text(plan_title, 80) or "商业演示文稿",
        "design_system": "tech_blue",
        "slides": slides[: max(1, target_count)],
    }


def _extract_planner_payload(text: str, target_count: int) -> Dict[str, Any]:
    try:
        return _extract_json(text)
    except ValueError:
        return _markdown_outline_to_plan(text, target_count)


def _trim_text(text: str, max_len: int) -> str:
    txt = re.sub(r"\s+", " ", (text or "").strip())
    return txt if len(txt) <= max_len else txt[:max_len].rstrip(" ,，。；;:：")


def _visible_text_len(markdown: str) -> int:
    text = re.sub(r"<[^>]+>", "", markdown or "")
    text = re.sub(r"[`*_>#-]", " ", text)
    text = re.sub(r"\s+", "", text)
    return len(text)


def _find_mark_keyword(markdown: str) -> str:
    m = re.search(r"<mark>(.*?)</mark>", markdown or "", re.DOTALL)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def _ensure_mark(markdown: str, fallback_keyword: str) -> str:
    if "<mark>" in markdown:
        return markdown
    keyword = _trim_text(fallback_keyword, 12) or "核心指标"
    if "\n" in markdown:
        return f"{markdown}\n\n<mark>{keyword}</mark>"
    return f"{markdown} <mark>{keyword}</mark>"


def _compact_markdown(slide_type: str, title: str, keyword: str) -> str:
    t = _trim_text(title, 16) or "核心结论"
    k = _trim_text(keyword, 12) or "关键数据"
    if slide_type in {"cover", "divider", "summary"}:
        return f"<!-- _class: lead -->\n\n# {t}\n\n<mark>{k}</mark>"
    if slide_type == "toc":
        return f"# {t}\n\n- <mark>{k}</mark>\n- 核心章节"
    return f"# {t}\n\n<mark>{k}</mark>"


def _normalize_script(script: Any, title: str, points: List[str]) -> List[Dict[str, str]]:
    lines: List[Dict[str, str]] = []
    if isinstance(script, list):
        for raw in script[:3]:
            if isinstance(raw, dict):
                role = raw.get("role", "host")
                text = str(raw.get("text", "")).strip()
            else:
                role = "host"
                text = str(raw).strip()
            if not text:
                continue
            role = role if role in {"host", "student"} else "host"
            for prefix in _BANNED_PREFIXES:
                if text.startswith(prefix):
                    text = text[len(prefix) :].lstrip("，,：: ")
            text = _trim_text(text, 90)
            if len(text) >= 8:
                lines.append({"role": role, "text": text})

    if lines:
        return lines

    key = _trim_text(points[0], 18) if points else "增长指标"
    host = _trim_text(f"{title}最关键的变化是{key}，这背后是流程改造而不是口号。", 70)
    student = _trim_text("这个变化在成本和交付周期上，具体带来多大改善？", 42)
    return [{"role": "host", "text": host}, {"role": "student", "text": student}]


def _normalize_actions(
    mapped_actions: Any,
    slide_type: str,
    markdown: str,
    data_points: List[str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if isinstance(mapped_actions, list):
        for action in mapped_actions:
            if not isinstance(action, dict):
                continue
            t = str(action.get("type", "")).strip()
            if t == "draw_circle":
                t = "circle"
            elif t in {"spotlight", "underline"}:
                t = "highlight"
            payload: Dict[str, Any] = {"type": t}
            if "startFrame" in action:
                payload["startFrame"] = max(0, int(action.get("startFrame") or 0))
            if t == "highlight":
                payload["keyword"] = str(action.get("keyword") or _find_mark_keyword(markdown)).strip()
            if t == "circle":
                payload["x"] = float(action.get("x") or 960)
                payload["y"] = float(action.get("y") or 430)
                payload["r"] = float(action.get("r") or 110)
            if t == "appear_items":
                items = action.get("items")
                if isinstance(items, list):
                    payload["items"] = [str(i).strip() for i in items if str(i).strip()][:5]
            if t == "zoom_in":
                payload["region"] = str(action.get("region") or "center")
            out.append(payload)

    if not out:
        mark_kw = _find_mark_keyword(markdown)
        if slide_type in {"grid_2", "grid_3"}:
            items = [p for p in data_points[:3] if p]
            if items:
                out.append(
                    {
                        "type": "appear_items",
                        "items": items,
                        "startFrame": 26,
                    }
                )
        if mark_kw:
            out.append({"type": "highlight", "keyword": mark_kw, "startFrame": 22})
        elif slide_type == "timeline":
            out.append({"type": "circle", "x": 960, "y": 430, "r": 100, "startFrame": 30})
        else:
            out.append({"type": "zoom_in", "region": "center", "startFrame": 28})

    if out and "startFrame" not in out[0]:
        out[0]["startFrame"] = 18
    return out


def _plan_slide_types(num_slides: int, planner_slides: List[Dict[str, Any]]) -> List[str]:
    total = max(3, int(num_slides))
    planned = ["grid_2"] * total

    fixed_slots: Dict[int, str] = {0: "cover", total - 1: "summary"}
    if total > 1:
        fixed_slots[1] = "toc"
    for idx, slide_type in fixed_slots.items():
        planned[idx] = slide_type

    content_slots = [i for i in range(total) if i not in fixed_slots]
    cycle_index = 0
    since_divider = 0
    for slot_pos, idx in enumerate(content_slots):
        remaining = len(content_slots) - slot_pos
        if since_divider >= 3 and remaining > 1:
            planned[idx] = "divider"
            since_divider = 0
            continue
        planned[idx] = _CONTENT_TYPES[cycle_index % len(_CONTENT_TYPES)]
        cycle_index += 1
        since_divider += 1

    # Inject planner preference when still valid.
    for i in range(min(len(planner_slides), total)):
        if i in fixed_slots:
            continue
        suggested = str(planner_slides[i].get("slide_type", "")).strip()
        if suggested in SLIDE_TYPES and suggested not in {"cover", "toc", "summary"}:
            prev_ok = i == 0 or planned[i - 1] != suggested
            next_ok = i == total - 1 or planned[i + 1] != suggested
            if prev_ok and next_ok:
                planned[i] = suggested

    # Ratio repair.
    max_count = max(1, ceil(total * 0.3))
    counts = Counter(planned)
    replacement_pool = ["grid_2", "grid_3", "quote_stat", "timeline", "divider"]
    for i, st in enumerate(planned):
        if i in fixed_slots:
            continue
        if counts[st] <= max_count:
            continue
        for candidate in replacement_pool:
            if candidate == st:
                continue
            if counts[candidate] >= max_count:
                continue
            prev_ok = i == 0 or planned[i - 1] != candidate
            next_ok = i == total - 1 or planned[i + 1] != candidate
            if prev_ok and next_ok:
                counts[st] -= 1
                planned[i] = candidate
                counts[candidate] += 1
                break

    # Adjacent dedupe final pass.
    for i in range(1, total):
        if i in fixed_slots:
            continue
        if planned[i] != planned[i - 1]:
            continue
        for candidate in replacement_pool:
            if candidate == planned[i]:
                continue
            if i < total - 1 and planned[i + 1] == candidate:
                continue
            if i in fixed_slots and fixed_slots[i] != candidate:
                continue
            planned[i] = candidate
            break

    # Final guard: mandatory layout invariants.
    for idx, slide_type in fixed_slots.items():
        planned[idx] = slide_type

    return planned


def _slide_meta_from_plan(
    planner_slides: List[Dict[str, Any]],
    planned_types: List[str],
) -> List[Dict[str, Any]]:
    metas: List[Dict[str, Any]] = []
    for idx, st in enumerate(planned_types):
        raw = planner_slides[idx] if idx < len(planner_slides) else {}
        key_message = str(raw.get("key_message", "")).strip() or f"第{idx + 1}页核心观点"
        points = raw.get("data_points")
        data_points = (
            [str(p).strip() for p in points if str(p).strip()] if isinstance(points, list) else []
        )
        metas.append(
            {
                "slide_index": idx + 1,
                "slide_type": st,
                "key_message": _trim_text(key_message, 32),
                "data_points": data_points[:5],
            }
        )
    return metas


def _fallback_slide(meta: Dict[str, Any]) -> Dict[str, Any]:
    title = meta["key_message"]
    points = meta.get("data_points", [])
    keyword = points[0] if points else "关键指标"
    markdown = _compact_markdown(meta["slide_type"], title, keyword)
    markdown = _ensure_mark(markdown, keyword)
    script = _normalize_script([], title=title, points=points)
    actions = _normalize_actions([], meta["slide_type"], markdown, points)
    return {
        "slide_type": meta["slide_type"],
        "markdown": markdown,
        "script": script,
        "bg_image_keyword": _trim_text(title, 40),
        "actions": actions,
    }


def _normalize_mapped_slide(mapped: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    title = meta["key_message"]
    points = meta.get("data_points", [])
    slide_type = meta["slide_type"]

    markdown = str(mapped.get("markdown", "")).strip()
    if not markdown:
        markdown = _compact_markdown(slide_type, title, points[0] if points else title)
    markdown = _ensure_mark(markdown, points[0] if points else title)

    if _visible_text_len(markdown) > 40:
        markdown = _compact_markdown(slide_type, title, points[0] if points else title)
        markdown = _ensure_mark(markdown, points[0] if points else title)

    script = _normalize_script(mapped.get("script"), title=title, points=points)
    bg_keyword = _trim_text(str(mapped.get("bg_image_keyword", "")).strip(), 80)
    if not bg_keyword:
        bg_keyword = _trim_text(f"{title} business presentation background", 80)
    actions = _normalize_actions(mapped.get("actions"), slide_type, markdown, points)

    return {
        "slide_type": slide_type,
        "markdown": markdown,
        "script": script,
        "bg_image_keyword": bg_keyword,
        "actions": actions,
    }


async def generate_v7(
    requirement: str,
    num_slides: int = 10,
    language: str = "zh-CN",
    ai_call=None,
) -> Dict[str, Any]:
    from src.openrouter_client import OpenRouterClient

    client = ai_call or OpenRouterClient()
    target_count = max(3, int(num_slides))

    logger.info("[v7] phase-1 planner")
    planner_raw = await client.chat_completions(
        model=MODEL,
        messages=[
            {"role": "system", "content": PLANNER_PROMPT},
            {
                "role": "user",
                "content": f"主题: {requirement}\n页数: {target_count}\n语言: {language}",
            },
        ],
        temperature=0.4,
        max_tokens=2500,
        response_format={"type": "json_object"},
    )
    plan = _extract_planner_payload(planner_raw, target_count)
    planner_slides = plan.get("slides", []) if isinstance(plan.get("slides"), list) else []
    planned_types = _plan_slide_types(target_count, planner_slides)
    metas = _slide_meta_from_plan(planner_slides, planned_types)

    logger.info("[v7] phase-2 mapper (%d slides)", len(metas))
    sem = asyncio.Semaphore(4)

    async def _map_slide(meta: Dict[str, Any]) -> Dict[str, Any]:
        async with sem:
            prompt = (
                f"请输出第{meta['slide_index']}页 JSON。\n"
                f"slide_type: {meta['slide_type']}\n"
                f"key_message: {meta['key_message']}\n"
                f"data_points: {json.dumps(meta['data_points'], ensure_ascii=False)}"
            )
            raw = await client.chat_completions(
                model=MODEL,
                messages=[
                    {"role": "system", "content": MAPPER_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=1600,
                response_format={"type": "json_object"},
            )
            return _extract_json(raw)

    mapped_results = await asyncio.gather(
        *[_map_slide(meta) for meta in metas],
        return_exceptions=True,
    )

    slide_models: List[SlideData] = []
    for idx, meta in enumerate(metas):
        mapped = mapped_results[idx]
        normalized = (
            _fallback_slide(meta)
            if isinstance(mapped, Exception)
            else _normalize_mapped_slide(mapped, meta)
        )

        try:
            script = [DialogueLine.model_validate(s) for s in normalized["script"]]
            actions = [SlideAction.model_validate(a) for a in normalized["actions"]]
            slide_models.append(
                SlideData(
                    page_number=idx + 1,
                    slide_type=normalized["slide_type"],
                    markdown=normalized["markdown"],
                    script=script,
                    bg_image_keyword=normalized["bg_image_keyword"],
                    actions=actions,
                )
            )
        except Exception as exc:
            logger.warning("[v7] slide %s failed schema validation, fallback. error=%s", idx + 1, exc)
            fallback = _fallback_slide(meta)
            slide_models.append(
                SlideData(
                    page_number=idx + 1,
                    slide_type=fallback["slide_type"],
                    markdown=fallback["markdown"],
                    script=[DialogueLine.model_validate(s) for s in fallback["script"]],
                    bg_image_keyword=fallback["bg_image_keyword"],
                    actions=[SlideAction.model_validate(a) for a in fallback["actions"]],
                )
            )

    ds = str(plan.get("design_system", "tech_blue")).strip() or "tech_blue"
    if ds not in {"tech_blue", "apple_dark", "modern_light"}:
        ds = "tech_blue"

    presentation = PresentationData(
        title=_trim_text(str(plan.get("title", "")).strip() or "商业演示文稿", 120),
        design_system=ds,
        slides=slide_models,
    )
    logger.info("[v7] complete: %d slides", len(presentation.slides))
    return presentation.model_dump(mode="json")
