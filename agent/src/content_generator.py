"""
内容生成器 v4 — LLM 选择页面类型+填充内容，模板引擎生成专业布局

架构 (借鉴 OpenMAIC):
  LLM: 负责 "内容" — 标题/要点/数据/页面类型选择
  模板引擎: 负责 "布局" — 位置/大小/颜色/字体/装饰元素
  讲解生成: 独立步骤 — 更丰富的叙事脚本
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional

from src.schemas.ppt import (
    PresentationOutline,
    SlideBackground,
    SlideContent,
    SlideElement,
    SlideOutline,
)

logger = logging.getLogger("content_generator")

CONTENT_MODEL = os.getenv("CONTENT_LLM_MODEL", "openai/gpt-4o-mini")


# ════════════════════════════════════════════════════════════════════
# 系统提示 — LLM 只负责内容，不算像素
# ════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一位商业演示内容策划专家。

你的任务是为每页幻灯片选择最合适的页面类型，并填充具体内容。

## 页面类型 (6种)

1. **cover** — 封面页
   - 适用: 第一页、标题页
   - 需要: 主标题、副标题、背景风格描述

2. **content** — 内容页 (最常用)
   - 适用: 展示要点、数据、概念
   - 需要: 标题、要点列表 (3-7条，每条15-40字)、可选图表数据

3. **comparison** — 对比页
   - 适用: A vs B、方案对比、优劣分析
   - 需要: 标题、左栏标题+要点、右栏标题+要点

4. **table** — 表格页
   - 适用: 产品对比、参数列表、数据展示
   - 需要: 标题、表头、表格数据行

5. **section** — 章节分隔页
   - 适用: 大段落之间的过渡
   - 需要: 章节号、大标题、副标题

6. **contact** — 联系页
   - 适用: 最后一页
   - 需要: 感谢语、联系方式字典

## 内容要求
- 要点必须具体、有数据支撑，不要泛泛而谈
- 每条要点 15-40 字，包含具体数字或案例
- 图表数据必须是真实有意义的数据
- 讲解脚本 200-350字，口语化、专业、有过渡句"""


# ════════════════════════════════════════════════════════════════════
# Prompt 构建
# ════════════════════════════════════════════════════════════════════


def _build_content_prompt(
    slide_outline: SlideOutline,
    language: str,
    page_context: Optional[Dict[str, Any]] = None,
) -> str:
    ctx = ""
    if page_context:
        prev = page_context.get("previous_speeches", [])
        if prev:
            ctx = f"\n上一页讲解结尾: {prev[-1][:150]}...\n请用过渡句衔接。"

    # 自动推断页面类型建议
    order = slide_outline.order
    title = slide_outline.title
    suggested_type = "content"
    if order == 0 or "封面" in title:
        suggested_type = "cover"
    elif "联系" in title or "封底" in title:
        suggested_type = "contact"
    elif "对比" in title or "vs" in title.lower():
        suggested_type = "comparison"
    elif len(slide_outline.key_points) > 5:
        suggested_type = "table"
    elif order > 0 and len(slide_outline.key_points) <= 2:
        suggested_type = "section"

    return f"""请为这页幻灯片选择页面类型并填充内容:

标题: {slide_outline.title}
描述: {slide_outline.description}
关键要点: {json.dumps(slide_outline.key_points, ensure_ascii=False)}
建议类型: {suggested_type}
{ctx}

严格按以下JSON格式返回 (不要位置/大小/颜色等样式信息):

如果是 content 类型:
{{
    "page_type": "content",
    "title": "页面标题",
    "items": [
        "第一条要点 (15-40字，含具体数据或案例)",
        "第二条要点...",
        "第三条要点..."
    ],
    "highlight": "最重要的一个数据或结论 (用于视觉强调)",
    "chart_data": null,
    "narration": "200-350字的口语化讲解脚本..."
}}

如果是 comparison 类型:
{{
    "page_type": "comparison",
    "title": "对比标题",
    "left_title": "方案A",
    "left_items": ["要点1", "要点2", "要点3"],
    "right_title": "方案B",
    "right_items": ["要点1", "要点2", "要点3"],
    "narration": "讲解脚本..."
}}

如果是 table 类型:
{{
    "page_type": "table",
    "title": "表格标题",
    "headers": ["项目", "指标A", "指标B"],
    "rows": [["产品1", "100", "200"], ["产品2", "150", "180"]],
    "narration": "讲解脚本..."
}}

如果是 cover 类型:
{{
    "page_type": "cover",
    "title": "主标题",
    "subtitle": "副标题",
    "bg_style": "dark",
    "narration": "简短开场白..."
}}

如果是 section 类型:
{{
    "page_type": "section",
    "section_num": 2,
    "title": "章节大标题",
    "subtitle": "章节副标题",
    "narration": "过渡性讲解..."
}}

如果是 contact 类型:
{{
    "page_type": "contact",
    "thanks": "感谢语",
    "contacts": {{"公司": "灵创智能", "电话": "400-XXX-XXXX", "官网": "www.xxx.com"}},
    "narration": "结尾致辞..."
}}"""


# ════════════════════════════════════════════════════════════════════
# JSON 提取
# ════════════════════════════════════════════════════════════════════


def _extract_json(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("LLM返回了空响应")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for match in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL):
        extracted = match.group(1).strip()
        if extracted.startswith(("{", "[")):
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass
    json_start_arr = text.find("[")
    json_start_obj = text.find("{")
    if json_start_arr != -1 or json_start_obj != -1:
        start_idx = min(x for x in [json_start_arr, json_start_obj] if x != -1)
        depth = 0
        in_string = False
        escape_next = False
        end_idx = -1
        for i in range(start_idx, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if not in_string:
                if ch in "[{":
                    depth += 1
                elif ch in "]}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
        if end_idx != -1:
            try:
                return json.loads(text[start_idx : end_idx + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError(f"无法从LLM响应中提取JSON: {text[:500]}")


def _sanitize(text: str) -> str:
    import html

    return html.escape(text)


def _sanitize_text(text: str) -> str:
    """Backward-compatible alias used by existing tests and older callers."""
    return _sanitize(text or "")


def _fix_element_defaults(element: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backward-compatible default normalizer for legacy tests.
    New layout code uses strongly-typed `SlideElement`, but this helper is kept
    for compatibility with older pipelines and regression tests.
    """
    el = dict(element or {})
    el.setdefault("type", "text")
    el.setdefault("left", 100)
    el.setdefault("top", 100)
    el.setdefault("width", 200)
    el.setdefault("height", 100)
    style = dict(el.get("style") or {})

    t = str(el.get("type", "text"))
    if t == "text":
        el.setdefault("content", "")
        style.setdefault("fontFamily", "Microsoft YaHei")
        style.setdefault("color", "#333333")
        style.setdefault("fontSize", 18)
    elif t == "image":
        style.setdefault("objectFit", "cover")
        el.setdefault("src", "")
    elif t == "shape":
        w = int(el.get("width", 200))
        h = int(el.get("height", 100))
        el.setdefault("viewBox", f"0 0 {w} {h}")
        el.setdefault("path", f"M0 0 H{w} V{h} H0 Z")
        el.setdefault("fill", "#5b9bd5")
    elif t == "chart":
        el.setdefault("chart_type", "bar")
        el.setdefault(
            "chart_data",
            {
                "labels": [],
                "datasets": [],
            },
        )
    elif t == "table":
        el.setdefault("table_rows", [])
        style.setdefault("fontSize", 14)

    if style:
        el["style"] = style
    return el


# ════════════════════════════════════════════════════════════════════
# 模板引擎 — 根据页面类型+内容自动生成专业布局
# ════════════════════════════════════════════════════════════════════

# 配色方案
PALETTES = {
    "professional": {
        "primary": "#1e3a5f",
        "secondary": "#2563eb",
        "accent": "#38bdf8",
        "bg": "#ffffff",
        "text": "#1e293b",
        "text2": "#64748b",
    },
    "dark": {
        "primary": "#0f172a",
        "secondary": "#1e3a5f",
        "accent": "#38bdf8",
        "bg": "#0f172a",
        "text": "#e2e8f0",
        "text2": "#94a3b8",
    },
    "education": {
        "primary": "#166534",
        "secondary": "#16a34a",
        "accent": "#4ade80",
        "bg": "#f0fdf4",
        "text": "#14532d",
        "text2": "#6b7280",
    },
}


def _build_layout(data: Dict, order: int) -> tuple[List[SlideElement], SlideBackground]:
    """根据 LLM 返回的结构化内容，自动生成专业布局"""
    page_type = data.get("page_type", "content")
    p = PALETTES["professional"]  # 默认商务蓝

    bg_style = data.get("bg_style", "")
    if bg_style == "dark" or page_type in ("cover", "contact", "section"):
        p = PALETTES["dark"]

    title = _sanitize(data.get("title", ""))

    if page_type == "cover":
        return _layout_cover(title, data.get("subtitle", ""), p)
    elif page_type == "content":
        return _layout_content(
            title,
            data.get("items", []),
            data.get("highlight", ""),
            data.get("chart_data"),
            p,
        )
    elif page_type == "comparison":
        return _layout_comparison(
            title,
            data.get("left_title", ""),
            data.get("left_items", []),
            data.get("right_title", ""),
            data.get("right_items", []),
            p,
        )
    elif page_type == "table":
        return _layout_table(title, data.get("headers", []), data.get("rows", []), p)
    elif page_type == "section":
        return _layout_section(
            data.get("section_num", order), title, data.get("subtitle", ""), p
        )
    elif page_type == "contact":
        return _layout_contact(
            data.get("thanks", "感谢聆听"), data.get("contacts", {}), p
        )
    else:
        return _layout_content(
            title, data.get("items", []), data.get("highlight", ""), None, p
        )


def _layout_cover(title: str, subtitle: str, p: Dict) -> tuple:
    bg = SlideBackground(
        type="gradient",
        gradient={
            "type": "linear",
            "colors": [
                {"pos": 0, "color": p["primary"]},
                {"pos": 100, "color": "#0f172a"},
            ],
            "rotate": 135,
        },
    )
    els = [
        # 装饰圆
        SlideElement(
            type="shape",
            left=1500,
            top=0,
            width=600,
            height=600,
            style={
                "backgroundColor": p["accent"],
                "opacity": 0.08,
                "borderRadius": 300,
            },
        ),
        SlideElement(
            type="shape",
            left=0,
            top=700,
            width=400,
            height=400,
            style={
                "backgroundColor": p["secondary"],
                "opacity": 0.06,
                "borderRadius": 200,
            },
        ),
        # 主标题
        SlideElement(
            type="text",
            left=120,
            top=300,
            width=1680,
            height=100,
            content=f"<b>{title}</b>",
            style={
                "fontSize": 64,
                "fontFamily": "Microsoft YaHei",
                "color": "#ffffff",
                "bold": True,
                "align": "left",
            },
        ),
        # 装饰线
        SlideElement(
            type="shape",
            left=120,
            top=430,
            width=120,
            height=4,
            style={"backgroundColor": p["accent"], "borderRadius": 2},
        ),
        # 副标题
        SlideElement(
            type="text",
            left=120,
            top=460,
            width=1680,
            height=50,
            content=subtitle,
            style={
                "fontSize": 26,
                "fontFamily": "Microsoft YaHei",
                "color": p["accent"],
                "align": "left",
            },
        ),
    ]
    return els, bg


def _layout_content(
    title: str, items: List[str], highlight: str, chart_data: Optional[Dict], p: Dict
) -> tuple:
    bg = SlideBackground(type="solid", color=p["bg"])
    els = [
        # 顶部标题栏
        SlideElement(
            type="shape",
            left=0,
            top=0,
            width=1920,
            height=90,
            style={"backgroundColor": p["primary"]},
        ),
        SlideElement(
            type="text",
            left=80,
            top=18,
            width=1500,
            height=60,
            content=f"<b>{title}</b>",
            style={
                "fontSize": 34,
                "fontFamily": "Microsoft YaHei",
                "color": "#ffffff",
                "bold": True,
            },
        ),
        # 左侧强调色竖条
        SlideElement(
            type="shape",
            left=80,
            top=120,
            width=5,
            height=min(len(items) * 60, 650),
            style={"backgroundColor": p["accent"], "borderRadius": 3},
        ),
    ]

    # 要点列表
    for i, item in enumerate(items[:8]):
        y = 125 + i * 62
        if y > 880:
            break
        els.append(
            SlideElement(
                type="text",
                left=110,
                top=y,
                width=1050,
                height=50,
                content=f"\u2022 {_sanitize(item)}",
                style={
                    "fontSize": 22,
                    "fontFamily": "Microsoft YaHei",
                    "color": p["text"],
                    "lineSpacing": 1.3,
                },
            )
        )

    # 高亮数据框 (右侧)
    if highlight:
        els.append(
            SlideElement(
                type="shape",
                left=1200,
                top=140,
                width=640,
                height=160,
                style={
                    "backgroundColor": p["accent"],
                    "borderRadius": 12,
                    "opacity": 0.15,
                },
            )
        )
        els.append(
            SlideElement(
                type="text",
                left=1220,
                top=160,
                width=600,
                height=120,
                content=f"<b>{_sanitize(highlight)}</b>",
                style={
                    "fontSize": 36,
                    "fontFamily": "Microsoft YaHei",
                    "color": p["primary"],
                    "bold": True,
                    "align": "center",
                },
            )
        )

    # 图表 (右下)
    if chart_data and chart_data.get("labels"):
        els.append(
            SlideElement(
                type="chart",
                left=1150,
                top=340,
                width=700,
                height=450,
                chart_type=chart_data.get("type", "bar"),
                chart_data={
                    "labels": chart_data["labels"],
                    "datasets": chart_data.get("datasets", []),
                },
            )
        )

    return els, bg


def _layout_comparison(
    title: str, lt: str, li: List[str], rt: str, ri: List[str], p: Dict
) -> tuple:
    bg = SlideBackground(type="solid", color=p["bg"])
    els = [
        SlideElement(
            type="shape",
            left=0,
            top=0,
            width=1920,
            height=90,
            style={"backgroundColor": p["primary"]},
        ),
        SlideElement(
            type="text",
            left=80,
            top=18,
            width=1500,
            height=60,
            content=f"<b>{title}</b>",
            style={
                "fontSize": 34,
                "fontFamily": "Microsoft YaHei",
                "color": "#ffffff",
                "bold": True,
            },
        ),
        # 左栏标题
        SlideElement(
            type="shape",
            left=80,
            top=120,
            width=860,
            height=55,
            style={"backgroundColor": p["secondary"], "borderRadius": 8},
        ),
        SlideElement(
            type="text",
            left=100,
            top=128,
            width=820,
            height=40,
            content=f"<b>{_sanitize(lt)}</b>",
            style={
                "fontSize": 22,
                "fontFamily": "Microsoft YaHei",
                "color": "#ffffff",
                "bold": True,
            },
        ),
        # 右栏标题
        SlideElement(
            type="shape",
            left=980,
            top=120,
            width=860,
            height=55,
            style={"backgroundColor": p["accent"], "borderRadius": 8},
        ),
        SlideElement(
            type="text",
            left=1000,
            top=128,
            width=820,
            height=40,
            content=f"<b>{_sanitize(rt)}</b>",
            style={
                "fontSize": 22,
                "fontFamily": "Microsoft YaHei",
                "color": "#ffffff",
                "bold": True,
            },
        ),
    ]
    for i, item in enumerate(li[:7]):
        els.append(
            SlideElement(
                type="text",
                left=100,
                top=200 + i * 52,
                width=800,
                height=42,
                content=f"\u2713 {_sanitize(item)}",
                style={
                    "fontSize": 20,
                    "fontFamily": "Microsoft YaHei",
                    "color": p["text"],
                },
            )
        )
    for i, item in enumerate(ri[:7]):
        els.append(
            SlideElement(
                type="text",
                left=1000,
                top=200 + i * 52,
                width=800,
                height=42,
                content=f"\u2713 {_sanitize(item)}",
                style={
                    "fontSize": 20,
                    "fontFamily": "Microsoft YaHei",
                    "color": p["text"],
                },
            )
        )
    return els, bg


def _layout_table(
    title: str, headers: List[str], rows: List[List[str]], p: Dict
) -> tuple:
    bg = SlideBackground(type="solid", color=p["bg"])
    els = [
        SlideElement(
            type="shape",
            left=0,
            top=0,
            width=1920,
            height=90,
            style={"backgroundColor": p["primary"]},
        ),
        SlideElement(
            type="text",
            left=80,
            top=18,
            width=1500,
            height=60,
            content=f"<b>{title}</b>",
            style={
                "fontSize": 34,
                "fontFamily": "Microsoft YaHei",
                "color": "#ffffff",
                "bold": True,
            },
        ),
    ]
    if headers and rows:
        col_count = len(headers)
        col_w = 1760 / max(col_count, 1)
        els.append(
            SlideElement(
                type="table",
                left=80,
                top=130,
                width=1760,
                height=min(50 + len(rows) * 45, 850),
                table_rows=[headers] + rows,
                table_col_widths=[col_w] * col_count,
                style={"fontSize": 16, "fontFamily": "Microsoft YaHei"},
            )
        )
    return els, bg


def _layout_section(num: int, title: str, subtitle: str, p: Dict) -> tuple:
    bg = SlideBackground(
        type="gradient",
        gradient={
            "type": "linear",
            "colors": [
                {"pos": 0, "color": p["primary"]},
                {"pos": 100, "color": "#0f172a"},
            ],
            "rotate": 135,
        },
    )
    els = [
        SlideElement(
            type="shape",
            left=120,
            top=430,
            width=160,
            height=4,
            style={"backgroundColor": p["accent"], "borderRadius": 2},
        ),
        SlideElement(
            type="text",
            left=120,
            top=340,
            width=200,
            height=60,
            content=f"<b>PART {num}</b>",
            style={
                "fontSize": 22,
                "fontFamily": "Microsoft YaHei",
                "color": p["accent"],
                "bold": True,
            },
        ),
        SlideElement(
            type="text",
            left=120,
            top=460,
            width=1680,
            height=80,
            content=f"<b>{title}</b>",
            style={
                "fontSize": 52,
                "fontFamily": "Microsoft YaHei",
                "color": "#ffffff",
                "bold": True,
            },
        ),
        SlideElement(
            type="text",
            left=120,
            top=560,
            width=1680,
            height=40,
            content=subtitle,
            style={
                "fontSize": 20,
                "fontFamily": "Microsoft YaHei",
                "color": p["text2"],
            },
        ),
    ]
    return els, bg


def _layout_contact(thanks: str, contacts: Dict, p: Dict) -> tuple:
    bg = SlideBackground(
        type="gradient",
        gradient={
            "type": "linear",
            "colors": [
                {"pos": 0, "color": p["primary"]},
                {"pos": 100, "color": "#0f172a"},
            ],
            "rotate": 135,
        },
    )
    els = [
        SlideElement(
            type="shape",
            left=1500,
            top=600,
            width=400,
            height=400,
            style={
                "backgroundColor": p["accent"],
                "opacity": 0.06,
                "borderRadius": 200,
            },
        ),
        SlideElement(
            type="text",
            left=120,
            top=280,
            width=1680,
            height=90,
            content=f"<b>{_sanitize(thanks)}</b>",
            style={
                "fontSize": 56,
                "fontFamily": "Microsoft YaHei",
                "color": "#ffffff",
                "bold": True,
                "align": "center",
            },
        ),
        SlideElement(
            type="text",
            left=120,
            top=390,
            width=1680,
            height=40,
            content="期待与您合作",
            style={
                "fontSize": 24,
                "fontFamily": "Microsoft YaHei",
                "color": p["accent"],
                "align": "center",
            },
        ),
    ]
    y = 500
    for k, v in contacts.items():
        els.append(
            SlideElement(
                type="text",
                left=500,
                top=y,
                width=920,
                height=35,
                content=f"{_sanitize(k)}: {_sanitize(str(v))}",
                style={
                    "fontSize": 18,
                    "fontFamily": "Microsoft YaHei",
                    "color": "#e2e8f0",
                    "align": "center",
                },
            )
        )
        y += 42
    return els, bg


# ════════════════════════════════════════════════════════════════════
# 生成逻辑
# ════════════════════════════════════════════════════════════════════

ProgressCallback = Callable[[Dict[str, Any]], None]


async def _generate_single_slide(
    slide_outline: SlideOutline,
    language: str,
    client,
    page_context: Optional[Dict[str, Any]] = None,
) -> SlideContent:
    """单页生成: LLM 填内容 → 模板引擎生成布局"""
    prompt = _build_content_prompt(slide_outline, language, page_context)

    raw = await client.chat_completions(
        model=CONTENT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=2048,
    )

    data = _extract_json(raw)

    # 模板引擎: 结构化内容 → 像素级布局
    elements, background = _build_layout(data, slide_outline.order)

    narration = _sanitize(data.get("narration", ""))
    if not narration or len(narration) < 20:
        narration = (
            f"接下来我们来看{slide_outline.title}。"
            + "。".join(slide_outline.key_points)
            + "。"
        )

    return SlideContent(
        outline_id=slide_outline.id,
        order=slide_outline.order,
        title=data.get("title", slide_outline.title),
        elements=elements,
        background=background,
        narration=narration,
        speaker_notes=narration[:100],
        duration=max(10, min(600, slide_outline.estimated_duration)),
    )


async def generate_content(
    outline: PresentationOutline,
    language: str = "zh-CN",
    ai_call: Optional[callable] = None,
    max_concurrency: int = 5,
    on_progress: Optional[ProgressCallback] = None,
    **kwargs,
) -> List[SlideContent]:
    """并行生成所有幻灯片内容"""
    from src.openrouter_client import OpenRouterClient

    client = ai_call or OpenRouterClient()
    semaphore = asyncio.Semaphore(max_concurrency)
    completed = 0
    total = len(outline.slides)
    all_narrations: List[str] = [""] * total

    on_progress and on_progress(
        {
            "stage": "content",
            "status": "generating",
            "message": f"Generating {total} slides...",
            "completed": 0,
            "total": total,
        }
    )

    async def _limited(idx: int, s: SlideOutline) -> tuple[int, SlideContent]:
        nonlocal completed
        async with semaphore:
            ctx = {"previous_speeches": [all_narrations[idx - 1]]} if idx > 0 else None
            result = await _generate_single_slide(s, language, client, ctx)
            all_narrations[idx] = result.narration
            completed += 1
            on_progress and on_progress(
                {
                    "stage": "content",
                    "status": "progress",
                    "message": f"{completed}/{total}",
                    "completed": completed,
                    "total": total,
                }
            )
            return idx, result

    tasks = [_limited(i, s) for i, s in enumerate(outline.slides)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    slides: List[SlideContent] = [None] * total  # type: ignore
    failures: List[str] = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"[content_generator] Slide failed: {result}")
            failures.append(str(result))
            continue
        idx, content = result
        slides[idx] = content

    missing_indexes = [idx for idx, slide in enumerate(slides) if slide is None]
    if failures or missing_indexes:
        detail_parts = []
        if failures:
            detail_parts.append("; ".join(failures[:3]))
        if missing_indexes:
            detail_parts.append(f"missing_indexes={missing_indexes[:10]}")
        detail = " | ".join(detail_parts)[:800]
        raise RuntimeError(
            f"Content generation degraded: {len(failures)} failed, {len(missing_indexes)} missing. "
            f"Fallback is disabled. detail={detail}"
        )

    on_progress and on_progress(
        {
            "stage": "content",
            "status": "completed",
            "message": "Done",
            "completed": total,
            "total": total,
        }
    )
    return [slide for slide in slides if slide is not None]
