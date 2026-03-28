"""
Marp 数据模型 — Markdown 驱动 + 视听解耦

LLM 输出: 每页 Marp Markdown + 讲解剧本
PPTX: marp-cli 转换
视频: Remotion @marp-team/marp-core 渲染
"""

from __future__ import annotations
import uuid
from typing import List, Literal
from pydantic import BaseModel, Field


def _id() -> str:
    return uuid.uuid4().hex[:10]


# ════════════════════════════════════════════════════════════════════
# 对话行 (单人 host + 动作)
# ════════════════════════════════════════════════════════════════════

ActionType = Literal["none", "spotlight", "draw_circle", "underline"]


class DialogueLine(BaseModel):
    role: str = "host"
    text: str = ""
    target_id: str = ""  # <span id="target-1"> 对应的 ID
    action: ActionType = "none"
    audio_url: str = ""
    audio_duration: float = 0


# ════════════════════════════════════════════════════════════════════
# 单页幻灯片
# ════════════════════════════════════════════════════════════════════


class SlideData(BaseModel):
    id: str = Field(default_factory=_id)
    order: int = 0
    markdown: str = ""  # 单页 Marp Markdown (不含 frontmatter)
    script: List[DialogueLine] = Field(default_factory=list)
    duration: float = 0  # 由音频时长决定


# ════════════════════════════════════════════════════════════════════
# 完整演示文稿
# ════════════════════════════════════════════════════════════════════

MarpTheme = Literal["default", "gaia", "uncover"]


class PresentationMarp(BaseModel):
    title: str = ""
    theme: MarpTheme = "default"
    slides: List[SlideData] = Field(default_factory=list)

    def to_full_markdown(self) -> str:
        """拼装完整 Marp Markdown (含 frontmatter)"""
        header = (
            f"---\nmarp: true\ntheme: {self.theme}\npaginate: true\nsize: 16:9\n---\n\n"
        )
        pages = [s.markdown.strip() for s in self.slides]
        return header + "\n\n---\n\n".join(pages)


# ════════════════════════════════════════════════════════════════════
# API
# ════════════════════════════════════════════════════════════════════


class GenerateRequest(BaseModel):
    requirement: str = Field(..., min_length=2, max_length=5000)
    num_slides: int = Field(default=10, ge=1, le=50)
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    theme: MarpTheme = "default"


class ExportRequest(BaseModel):
    presentation: PresentationMarp


class TTSRequestMarp(BaseModel):
    slides: List[SlideData]


class ApiResponse(BaseModel):
    success: bool = True
    data: object = None
    error: str = ""
