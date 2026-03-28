"""PPT v7 schemas: strong constraints for MiniMax + Remotion pipeline."""

from __future__ import annotations

import os
import re
from collections import Counter
from math import ceil
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


SlideType = Literal[
    "cover",
    "toc",
    "grid_2",
    "grid_3",
    "quote_stat",
    "timeline",
    "divider",
    "summary",
]

RoleType = Literal["host", "student"]

ActionType = Literal["highlight", "circle", "appear_items", "zoom_in"]

DesignSystem = Literal["tech_blue", "apple_dark", "modern_light"]


_BANNED_PREFIXES = (
    "这一页",
    "在这一页",
    "这张幻灯片",
    "接下来我们看",
    "数据都是实打实的",
    "让我们来看看",
    "如图所示",
)


def _visible_text_len(markdown: str) -> int:
    text = re.sub(r"<[^>]+>", "", markdown or "")
    text = re.sub(r"[`*_>#-]", " ", text)
    text = re.sub(r"\s+", "", text)
    return len(text)


def _screen_text_limit() -> int:
    raw = str(os.getenv("PPT_V7_SCREEN_TEXT_MAX_CHARS", "80")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 80
    return max(20, min(400, value))


class DialogueLine(BaseModel):
    role: RoleType = "host"
    text: str = Field(..., min_length=2, max_length=180)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("dialogue text is empty")
        for phrase in _BANNED_PREFIXES:
            if text.startswith(phrase):
                raise ValueError(f"禁用开头词: {phrase}")
        return text


class SlideAction(BaseModel):
    type: ActionType
    startFrame: int = Field(default=0, ge=0)
    keyword: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    r: Optional[float] = None
    items: List[str] = Field(default_factory=list)
    region: Optional[str] = None

    @model_validator(mode="after")
    def check_action_payload(self) -> "SlideAction":
        if self.type == "highlight" and not (self.keyword or "").strip():
            raise ValueError("highlight action requires keyword")
        if self.type == "circle":
            if self.x is None or self.y is None or self.r is None:
                raise ValueError("circle action requires x/y/r")
        if self.type == "appear_items" and not self.items:
            raise ValueError("appear_items action requires items")
        if self.type == "zoom_in" and not (self.region or "").strip():
            raise ValueError("zoom_in action requires region")
        return self


class SlideData(BaseModel):
    slide_id: str = Field(default="", min_length=1, max_length=128)
    page_number: int = Field(..., ge=1)
    slide_type: SlideType
    markdown: str = Field(..., min_length=2, max_length=3000)
    script: List[DialogueLine] = Field(default_factory=list, min_length=1)
    bg_image_keyword: str = Field(default="")
    actions: List[SlideAction] = Field(default_factory=list)
    narration_audio_url: str = Field(default="")
    duration: float = Field(default=0, ge=0)

    @field_validator("markdown")
    @classmethod
    def validate_markdown(cls, value: str) -> str:
        markdown = (value or "").strip()
        if "<mark>" not in markdown:
            raise ValueError("markdown must include <mark> highlight")
        limit = _screen_text_limit()
        if _visible_text_len(markdown) > limit:
            raise ValueError(f"screen text must be <= {limit} characters")
        return markdown

    @field_validator("bg_image_keyword")
    @classmethod
    def normalize_keyword(cls, value: str) -> str:
        return (value or "").strip()

    @model_validator(mode="after")
    def ensure_slide_id(self) -> "SlideData":
        if not self.slide_id.strip():
            self.slide_id = f"slide-{self.page_number}"
        return self


class PresentationData(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    design_system: DesignSystem = "tech_blue"
    slides: List[SlideData] = Field(default_factory=list, min_length=3)

    @model_validator(mode="after")
    def validate_layout_rules(self) -> "PresentationData":
        total = len(self.slides)
        slide_types = [s.slide_type for s in self.slides]
        slide_ids = [s.slide_id for s in self.slides]

        if slide_types[0] != "cover":
            raise ValueError("first slide must be cover")
        if "toc" not in slide_types:
            raise ValueError("presentation must include toc")
        if slide_types[-1] != "summary":
            raise ValueError("last slide must be summary")

        for idx in range(total - 1):
            if slide_types[idx] == slide_types[idx + 1]:
                raise ValueError("adjacent slides cannot share the same slide_type")

        max_count = max(1, ceil(total * 0.3))
        counts = Counter(slide_types)
        for st, count in counts.items():
            if count > max_count:
                raise ValueError(f"slide_type '{st}' exceeds ratio limit ({count}>{max_count})")

        if total >= 8:
            divider_count = counts.get("divider", 0)
            if divider_count < 1:
                raise ValueError("presentation with >=8 slides must include divider")

        if len(set(slide_ids)) != len(slide_ids):
            raise ValueError("slide_id must be unique")

        return self
