"""
PPT 数据模型 v5 — 语义化布局 (废弃绝对坐标)

核心思想: LLM 只输出 layoutType + content + emphasisWords
布局由模板引擎/Remotion组件负责
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ════════════════════════════════════════════════════════════════════
# 版式类型 — 预设 6 种高视觉质量版式
# ════════════════════════════════════════════════════════════════════

LayoutType = Literal[
    "cover",  # 封面: 大标题 + 副标题 + 背景
    "bullet_points",  # 要点列表: 标题 + 3-7条要点
    "split_left_img",  # 左图右文
    "split_right_img",  # 右图左文
    "quote",  # 名言/金句/重点强调
    "comparison",  # 双列对比
    "big_number",  # 大数字高亮: 标题 + 巨大数字 + 说明
]


# ════════════════════════════════════════════════════════════════════
# 视觉内容 — 每种版式对应不同的数据结构
# ════════════════════════════════════════════════════════════════════


class ComparisonData(BaseModel):
    """对比版式数据"""

    left_title: str = ""
    left_items: List[str] = Field(default_factory=list)
    right_title: str = ""
    right_items: List[str] = Field(default_factory=list)


class BigNumberData(BaseModel):
    """大数字版式数据"""

    number: str = ""
    unit: str = ""
    description: str = ""


class VisualContent(BaseModel):
    """视觉内容 — 根据 layoutType 填充对应字段"""

    title: str = ""
    subtitle: Optional[str] = None
    # bullet_points / quote 版式
    body_text: List[str] = Field(default_factory=list)  # 支持 Markdown **bold** 标记
    # 图片版式
    image_url: Optional[str] = None
    image_keyword: Optional[str] = None  # 图片搜索关键词
    # 对比版式
    comparison: Optional[ComparisonData] = None
    # 大数字版式
    big_number: Optional[BigNumberData] = None
    # 背景风格
    bg_style: Literal["light", "dark", "gradient", "image"] = "light"


# ════════════════════════════════════════════════════════════════════
# 幻灯片 — 语义化 (无像素坐标)
# ════════════════════════════════════════════════════════════════════


class SlideContentV5(BaseModel):
    """幻灯片内容 v5 — 语义化版式"""

    id: str = Field(default_factory=_new_id)
    order: int = 0
    layout_type: LayoutType = "bullet_points"
    content: VisualContent = Field(default_factory=VisualContent)
    narration: str = Field(default="", max_length=5000)
    narration_audio_url: Optional[str] = None
    emphasis_words: List[str] = Field(
        default_factory=list, max_length=5
    )  # 视觉高亮词汇
    duration: int = Field(default=0, ge=0, le=600)  # 0 = 由音频时长决定
    speaker_notes: str = ""


# ════════════════════════════════════════════════════════════════════
# 大纲 (复用已有结构)
# ════════════════════════════════════════════════════════════════════


class SlideOutline(BaseModel):
    """幻灯片大纲"""

    id: str = Field(default_factory=_new_id)
    order: int = 0
    title: str = ""
    description: str = ""
    key_points: List[str] = Field(default_factory=list)
    suggested_layout: LayoutType = "bullet_points"
    estimated_duration: int = Field(default=120, ge=10, le=600)


class PresentationOutline(BaseModel):
    """演示文稿大纲"""

    id: str = Field(default_factory=_new_id)
    title: str = ""
    theme: str = "default"
    slides: List[SlideOutline] = Field(default_factory=list, max_length=50)
    total_duration: int = 0
    style: Literal["professional", "education", "creative"] = "professional"


# ════════════════════════════════════════════════════════════════════
# API 请求/响应
# ════════════════════════════════════════════════════════════════════


class OutlineRequest(BaseModel):
    requirement: str = Field(..., min_length=2, max_length=5000)
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    num_slides: int = Field(default=10, ge=1, le=50)
    style: Literal["professional", "education", "creative"] = "professional"
    purpose: str = Field(default="", max_length=500)


class ContentRequestV5(BaseModel):
    outline: PresentationOutline
    language: Literal["zh-CN", "en-US"] = "zh-CN"


class ExportRequestV5(BaseModel):
    slides: List[SlideContentV5] = Field(..., max_length=50)
    title: str = Field(default="未命名", max_length=300)
    author: str = Field(default="AutoViralVid", max_length=100)
    template_id: str = "professional"  # 母版模板ID


class ApiResponse(BaseModel):
    success: bool = True
    data: Any = None
    error: Optional[str] = None
