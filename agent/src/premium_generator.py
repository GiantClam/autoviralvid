"""
Premium PPT 生成器 v6 — 强制丰富内容 + 7种模板 + 多样化script
"""

from __future__ import annotations
import asyncio, json, logging, os, random, re
from typing import Any, Dict, List

logger = logging.getLogger("premium_gen")
MODEL = os.getenv("CONTENT_LLM_MODEL", "openai/gpt-4o-mini")


# ════════════════════════════════════════════════════════════════════
# 多样化 script 模板
# ════════════════════════════════════════════════════════════════════

SCRIPT_TEMPLATES = [
    "关于{title}，{items_str}。",
    "{title}这块，{items_str}。",
    "来看{title}，{items_str}。",
    "说到{title}，{items_str}。",
    "{title}是重点，{items_str}。",
]

COMPARISON_SCRIPTS = [
    "做一个对比，{left_str}是传统方案的问题，而我们的方案在{right_str}方面差距很明显。",
    "看这组数据：传统方案{left_str}，我们做到了{right_str}。差距一目了然。",
]


def _gen_script(title, items, comp=None):
    if isinstance(comp, dict) and comp:
        left = "、".join(comp.get("left_items", [])[:2])
        right = "、".join(comp.get("right_items", [])[:2])
        return random.choice(COMPARISON_SCRIPTS).format(
            left_str=left or "效率低", right_str=right or "效率高"
        )
    if items:
        return random.choice(SCRIPT_TEMPLATES).format(
            title=title, items_str="。".join(items[:3]) + "。"
        )
    return f"接下来看{title}。"


# ════════════════════════════════════════════════════════════════════
# Prompt — 强制生成具体数据
# ════════════════════════════════════════════════════════════════════

SYSTEM = """你是制造业资深顾问。请为企业生成PPT。

## 布局
每页必须用不同布局，从以下选择: bullet_points, comparison, big_number, quote
cover 放第1页，closing 放最后1页，中间交替使用 comparison/bullet_points/quote/big_number

## 内容
- bullet_points: 3-5条要点，每条含具体数字
- comparison: left_title/left_items/right_title/right_items
- big_number: 1个超大数字+说明
- quote: 1句金句

## 禁止
赋能、闭环、抓手"""


def _build(requirement, n):
    return f"""请为企业设计{n}页PPT:

{requirement}

每页返回: layout_type, content.title, content.body_items(3-5条含数字), content.comparison, content.emphasis_words(1-2个数字)
第1页layout_type=cover，最后1页layout_type=closing，中间交替 comparison/bullet_points/quote/big_number

返回: {{"slides":[{{"layout_type":"cover","content":{{"title":"...","body_items":["..."],"emphasis_words":[],"comparison":null}}}}]}}"""


def _extract(text):
    text = text.strip()
    # 清理 Unicode 替换字符
    text = text.replace("\ufffd", "")
    # 直接解析
    try:
        return json.loads(text)
    except:
        pass
    # Code block 提取
    for m in re.finditer(r"```(?:json)?\s*\n(.*?)\n?\s*```", text, re.DOTALL):
        try:
            return json.loads(m.group(1).strip())
        except:
            pass
    # 找 JSON 对象
    si, ei = text.find("{"), text.rfind("}")
    if si != -1 and ei > si:
        json_str = text[si : ei + 1]
        try:
            return json.loads(json_str)
        except:
            # 修复截断
            open_b = json_str.count("{")
            close_b = json_str.count("}")
            if open_b > close_b:
                json_str += "}" * (open_b - close_b)
            open_arr = json_str.count("[")
            close_arr = json_str.count("]")
            if open_arr > close_arr:
                last_obj = json_str.rfind("}")
                if last_obj > 0:
                    json_str = json_str[: last_obj + 1] + "]" * (open_arr - close_arr)
            try:
                return json.loads(json_str)
            except:
                pass
    # 清理 markdown
    cleaned = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except:
        pass
    raise ValueError(f"Cannot parse: {text[:500]}")


def _s(t):
    import html

    return html.escape(str(t))


async def generate(requirement, num_slides=10, language="zh-CN", ai_call=None):
    from src.openrouter_client import OpenRouterClient

    client = ai_call or OpenRouterClient()

    raw = await client.chat_completions(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": _build(requirement, num_slides)},
        ],
        temperature=0.8,
        max_tokens=8192,
    )

    data = _extract(raw)
    raw_slides = data.get("slides", [])

    valid = {
        "cover",
        "bullet_points",
        "split_image",
        "quote",
        "comparison",
        "big_number",
        "qa_transition",
        "whiteboard",
    }
    lm = {
        "hero": "cover",
        "stats": "big_number",
        "versus": "comparison",
        "points": "bullet_points",
        "closing": "cover",
        "section_divider": "quote",
        "summary": "quote",
        "grid_2": "bullet_points",
        "grid_3": "bullet_points",
        "lead": "cover",
    }

    slides = []
    for i, s in enumerate(raw_slides):
        lt = lm.get(
            s.get("layout_type", "bullet_points"), s.get("layout_type", "bullet_points")
        )
        if lt not in valid:
            lt = "bullet_points"

        c = s.get("content", s.get("data", {}))
        comp = c.get("comparison")
        if isinstance(comp, dict):
            comp = {
                "left_title": comp.get("left_title", "传统"),
                "left_items": comp.get("left_items", []),
                "right_title": comp.get("right_title", "灵创"),
                "right_items": comp.get("right_items", []),
            }
        elif lt == "comparison":
            items = c.get("body_items", c.get("items", []))
            mid = max(1, len(items) // 2)
            comp = {
                "left_title": "传统方案",
                "left_items": [_s(t) for t in items[:mid]],
                "right_title": "灵创方案",
                "right_items": [_s(t) for t in items[mid:]],
            }

        items = c.get("body_items", c.get("items", []))
        emphasis = c.get("emphasis_words", c.get("emphasis", []))
        title = s.get("title", c.get("title", f"第{i + 1}页"))

        # 强制生成script
        script_text = _gen_script(title, items, comp)

        slides.append(
            {
                "order": i,
                "layout_type": lt,
                "content": {
                    "title": _s(title),
                    "subtitle": _s(s.get("subtitle", "")),
                    "body_items": [_s(t) for t in items[:5]],
                    "emphasis_words": emphasis[:3],
                    "bg_style": "dark",
                    "comparison": comp,
                },
                "script": [{"role": "host", "text": script_text, "action": "none"}],
            }
        )

    return slides
