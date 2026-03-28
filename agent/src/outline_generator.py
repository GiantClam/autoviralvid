"""大纲生成器 — Feature A: 根据用户需求生成PPT大纲

增强: 借鉴 OpenMAIC 的多策略JSON提取 + 进度回调 + 媒体策略
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional

from src.schemas.ppt import PresentationOutline, SlideOutline

logger = logging.getLogger("outline_generator")

OUTLINE_MODEL = os.getenv("OUTLINE_LLM_MODEL", "openai/gpt-4o-mini")

SYSTEM_PROMPT_ZH = """你是一位专业的课程设计师和PPT大纲规划师。
根据用户的需求，设计一份结构清晰、逻辑连贯的PPT大纲。

要求：
1. 每页幻灯片包含：标题、描述、关键要点、建议的视觉元素类型、预计时长
2. 大纲要有清晰的叙事结构（引入→核心内容→案例→总结）
3. 每页预计时长 60-180 秒
4. 关键要点每页 2-5 个
5. 建议的元素类型从以下选择：text, image, chart, table, latex, shape"""

SYSTEM_PROMPT_EN = """You are a professional course designer and PPT outline planner.
Design a well-structured PPT outline based on user requirements.

Requirements:
1. Each slide: title, description, key points, suggested visual elements, estimated duration
2. Clear narrative structure (intro → core content → examples → summary)
3. Each slide: 60-180 seconds
4. 2-5 key points per slide
5. Element types: text, image, chart, table, latex, shape"""


def _build_outline_prompt(
    requirement: str,
    language: str,
    num_slides: int,
    style: str,
    purpose: str,
    image_generation_enabled: bool = False,
    video_generation_enabled: bool = False,
) -> str:
    style_desc = {
        "professional": "商务专业风格，严谨简洁",
        "education": "教育培训风格，图文并茂，通俗易懂",
        "creative": "创意设计风格，视觉冲击力强",
    }
    style_zh = style_desc.get(style, style_desc["professional"])

    # 媒体生成策略 (借鉴 OpenMAIC mediaGenerationPolicy)
    media_policy = ""
    if not image_generation_enabled and not video_generation_enabled:
        media_policy = (
            "**重要: 不要在大纲中包含任何媒体生成标记。图片和视频生成均未启用。**"
        )
    elif not image_generation_enabled:
        media_policy = "**重要: 不要包含图片生成标记(type=image)。仅允许视频生成。**"
    elif not video_generation_enabled:
        media_policy = "**重要: 不要包含视频生成标记(type=video)。仅允许图片生成。**"

    if language == "zh-CN":
        return f"""请为以下需求设计PPT大纲：

需求：{requirement}
用途：{purpose or "通用演示"}
风格：{style_zh}
幻灯片数量：{num_slides}页
{media_policy}

请严格按以下JSON格式返回（不要包含任何其他文字）：
{{
    "title": "演示文稿标题",
    "theme": "default",
    "style": "{style}",
    "slides": [
        {{
            "order": 1,
            "title": "幻灯片标题",
            "description": "这页要讲解的内容概述",
            "key_points": ["要点1", "要点2", "要点3"],
            "suggested_elements": ["text", "image"],
            "estimated_duration": 120
        }}
    ]
}}"""
    else:
        return f"""Design a PPT outline for the following requirement:

Requirement: {requirement}
Purpose: {purpose or "General presentation"}
Style: {style}
Number of slides: {num_slides}
{media_policy}

Return strictly in this JSON format (no other text):
{{
    "title": "Presentation Title",
    "theme": "default",
    "style": "{style}",
    "slides": [
        {{
            "order": 1,
            "title": "Slide Title",
            "description": "Overview of this slide",
            "key_points": ["Point 1", "Point 2"],
            "suggested_elements": ["text", "image"],
            "estimated_duration": 120
        }}
    ]
}}"""


def _extract_json(text: str) -> dict:
    """
    从LLM响应中提取JSON — 多策略回退 (借鉴 OpenMAIC json-repair.ts)

    策略:
    1. 直接解析
    2. 提取 markdown code block
    3. 括号匹配 (感知字符串内括号)
    4. 正则匹配 { ... }
    5. 修复截断JSON
    """
    text = text.strip()
    if not text:
        raise ValueError("LLM返回了空响应")

    # Strategy 1: 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: 提取 markdown code block (可能有多个)
    for match in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL):
        extracted = match.group(1).strip()
        if extracted.startswith(("{", "[")):
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass

    # Strategy 3: 括号匹配 (感知字符串)
    json_start_arr = text.find("[")
    json_start_obj = text.find("{")

    if json_start_arr != -1 or json_start_obj != -1:
        start_idx = (
            min(json_start_arr, json_start_obj)
            if json_start_arr != -1 and json_start_obj != -1
            else max(json_start_arr, json_start_obj)
        )

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
            json_str = text[start_idx : end_idx + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # Strategy 4: 修复常见问题
                try:
                    fixed = json_str
                    # 修复LaTeX转义
                    fixed = re.sub(
                        r'"([^"]*?)"',
                        lambda m: '"'
                        + re.sub(r"\\([a-zA-Z])", r"\\\\\1", m.group(1))
                        + '"',
                        fixed,
                    )
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass
        else:
            # Strategy 4b: 修复截断的JSON (bracket matching 失败时)
            try:
                fixed = text[start_idx:]
                trimmed = fixed.strip()
                if trimmed.startswith("[") and not trimmed.endswith("]"):
                    last_obj = fixed.rfind("}")
                    if last_obj > start_idx:
                        fixed = fixed[: last_obj + 1] + "]"
                elif trimmed.startswith("{") and not trimmed.endswith("}"):
                    open_b = fixed.count("{")
                    close_b = fixed.count("}")
                    if open_b > close_b:
                        fixed += "}" * (open_b - close_b)
                # LaTeX修复
                fixed = re.sub(
                    r'"([^"]*?)"',
                    lambda m: '"'
                    + re.sub(r"\\([a-zA-Z])", r"\\\\\1", m.group(1))
                    + '"',
                    fixed,
                )
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

    # Strategy 5: 正则匹配
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从LLM响应中提取JSON: {text[:500]}")


ProgressCallback = Callable[[Dict[str, Any]], None]


async def generate_outline(
    requirement: str,
    language: str = "zh-CN",
    num_slides: int = 10,
    style: str = "professional",
    purpose: str = "",
    ai_call: Optional[callable] = None,
    on_progress: Optional[ProgressCallback] = None,
    image_generation_enabled: bool = False,
    video_generation_enabled: bool = False,
) -> PresentationOutline:
    """
    根据用户需求生成PPT大纲。

    增强 (借鉴 OpenMAIC):
    - 多策略JSON提取
    - 进度回调
    - 媒体生成策略
    - 用户画像支持
    """
    from src.openrouter_client import OpenRouterClient

    client = ai_call or OpenRouterClient()
    system = SYSTEM_PROMPT_ZH if language == "zh-CN" else SYSTEM_PROMPT_EN
    prompt = _build_outline_prompt(
        requirement,
        language,
        num_slides,
        style,
        purpose,
        image_generation_enabled,
        video_generation_enabled,
    )

    on_progress and on_progress(
        {
            "stage": "outline",
            "status": "generating",
            "message": "正在分析需求，生成场景大纲..."
            if language == "zh-CN"
            else "Analyzing requirements...",
        }
    )

    logger.info(f"[outline_generator] Generating outline: {requirement[:100]}...")

    raw = await client.chat_completions(
        model=OUTLINE_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
    )

    data = _extract_json(raw)

    slides = []
    for i, s in enumerate(data.get("slides", [])):
        # 元素默认值修复 (借鉴 OpenMAIC fixElementDefaults)
        suggested = s.get("suggested_elements", ["text"])
        if not suggested:
            suggested = ["text"]

        slides.append(
            SlideOutline(
                order=s.get("order", i + 1),
                title=s.get("title", f"Slide {i + 1}"),
                description=s.get("description", ""),
                key_points=s.get("key_points", []),
                suggested_elements=suggested,
                estimated_duration=max(30, min(600, s.get("estimated_duration", 120))),
            )
        )

    if not slides:
        raise ValueError("LLM未生成任何幻灯片大纲")

    outline = PresentationOutline(
        title=data.get("title", "未命名演示文稿"),
        theme=data.get("theme", "default"),
        slides=slides,
        total_duration=sum(s.estimated_duration for s in slides),
        style=data.get("style", style),
    )

    on_progress and on_progress(
        {
            "stage": "outline",
            "status": "completed",
            "message": f"已生成 {len(slides)} 个场景大纲",
            "slides_count": len(slides),
        }
    )

    logger.info(
        f"[outline_generator] Generated {len(slides)} slides, total {outline.total_duration}s"
    )
    return outline
