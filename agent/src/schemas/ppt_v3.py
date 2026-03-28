"""
PPT 数据模型 v3 — 语义化版式 + 多角色剧本 + 动作引擎
"""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


def _id() -> str:
    return uuid.uuid4().hex[:10]


# ════════════════════════════════════════════════════════════════════
# 版式类型 (预设7种高视觉质量版式)
# ════════════════════════════════════════════════════════════════════

LayoutType = Literal[
    "cover",  # 封面
    "bullet_points",  # 核心要点
    "split_image",  # 图文对半分
    "quote",  # 金句/名言
    "comparison",  # 双列对比
    "big_number",  # 大数字高亮
    "qa_transition",  # 问答转场黑屏
    "whiteboard",  # 白板推导
]


# ════════════════════════════════════════════════════════════════════
# 角色与动作 (借鉴 OpenMAIC)
# ════════════════════════════════════════════════════════════════════

RoleType = Literal["host", "student", "expert"]

ActionType = Literal["none", "spotlight", "draw_circle", "underline", "zoom_in"]


class DialogueLine(BaseModel):
    """一句对话台词"""

    role: RoleType = "host"
    text: str = ""
    target_element_id: Optional[str] = None  # 动作指向的语义区域
    action: ActionType = "none"
    audio_url: Optional[str] = None  # TTS 音频 URL
    audio_duration: float = 0  # 秒


# ════════════════════════════════════════════════════════════════════
# 视觉内容 (每种版式对应不同字段)
# ════════════════════════════════════════════════════════════════════


class ComparisonData(BaseModel):
    left_title: str = ""
    left_items: List[str] = []
    right_title: str = ""
    right_items: List[str] = []


class BigNumberData(BaseModel):
    number: str = ""
    unit: str = ""
    description: str = ""


class VisualContent(BaseModel):
    title: str = ""
    subtitle: Optional[str] = None
    body_items: List[str] = []  # 强制要点化, 每条不超过20字
    image_url: Optional[str] = None
    image_position: Literal["left", "right", "center"] = "right"
    comparison: Optional[ComparisonData] = None
    big_number: Optional[BigNumberData] = None
    emphasis_words: List[str] = []  # 需高亮的核心词汇
    bg_style: Literal["light", "dark", "gradient"] = "light"


# ════════════════════════════════════════════════════════════════════
# 幻灯片 (v3 核心: layout_type + content + script)
# ════════════════════════════════════════════════════════════════════


class SlideContentV3(BaseModel):
    id: str = Field(default_factory=_id)
    order: int = 0
    layout_type: LayoutType = "bullet_points"
    content: VisualContent = Field(default_factory=VisualContent)
    script: List[DialogueLine] = Field(default_factory=list)  # 多角色剧本
    duration: float = 0  # 由音频时长决定


# ════════════════════════════════════════════════════════════════════
# 大纲
# ════════════════════════════════════════════════════════════════════


class SlideOutlineV3(BaseModel):
    id: str = Field(default_factory=_id)
    order: int = 0
    title: str = ""
    description: str = ""
    key_points: List[str] = []
    suggested_layout: LayoutType = "bullet_points"
    estimated_duration: int = 120


class PresentationOutlineV3(BaseModel):
    id: str = Field(default_factory=_id)
    title: str = ""
    slides: List[SlideOutlineV3] = []
    total_duration: int = 0
    style: Literal["professional", "education", "creative"] = "professional"


# ════════════════════════════════════════════════════════════════════
# API
# ════════════════════════════════════════════════════════════════════


class ContentRequestV3(BaseModel):
    outline: PresentationOutlineV3
    language: Literal["zh-CN", "en-US"] = "zh-CN"


class ExportRequestV3(BaseModel):
    slides: List[SlideContentV3] = []
    title: str = "未命名"
    author: str = "AutoViralVid"
    template_id: str = "professional"


class ApiResponse(BaseModel):
    success: bool = True
    data: Any = None
    error: Optional[str] = None
