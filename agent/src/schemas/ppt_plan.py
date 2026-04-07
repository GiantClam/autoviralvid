"""Wireframe-level presentation plan schemas."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from src.schemas.ppt_outline import OutlinePlan
from src.schemas.ppt_research import ResearchContext


_PLACEHOLDER_PATTERNS = (
    r"\?\?\?",
    r"\bxxxx\b",
    r"\btodo\b",
    r"\btbd\b",
    r"lorem ipsum",
    r"\bplaceholder\b",
    r"指标[a-eA-E]",
    r"item\s*\d+",
)


BlockType = Literal[
    "title",
    "subtitle",
    "body",
    "comparison",
    "kpi",
    "chart",
    "image",
    "icon_text",
    "list",
    "quote",
    "table",
    "workflow",
    "diagram",
]

PositionType = Literal[
    "top",
    "left",
    "right",
    "center",
    "bottom",
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
]

SlideType = Literal["cover", "toc", "content", "divider", "summary"]


class ContentBlock(BaseModel):
    """Atomic content block in a slide plan."""

    block_type: BlockType
    position: PositionType
    content: str | Dict[str, Any] = Field(...)
    data: Optional[Dict] = None
    emphasis: List[str] = Field(default_factory=list, max_length=10)

    @field_validator("content")
    @classmethod
    def validate_content_no_placeholder(cls, value: str | Dict[str, Any]) -> str | Dict[str, Any]:
        if isinstance(value, dict):
            text = " ".join(str(item or "").strip() for item in value.values() if str(item or "").strip()).strip()
        else:
            text = str(value or "").strip()
        if not text:
            raise ValueError("content must not be empty")
        if len(text) > 4000:
            raise ValueError("content exceeds max_length=4000")
        for pattern in _PLACEHOLDER_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                raise ValueError(f"content contains placeholder pattern: {pattern}")
        return value if isinstance(value, dict) else text

    @model_validator(mode="after")
    def validate_block_data(self) -> "ContentBlock":
        if self.block_type == "kpi":
            payload = self.data or {}
            required = {"number", "unit", "trend"}
            missing = [k for k in required if k not in payload]
            if missing:
                raise ValueError(f"kpi data missing keys: {', '.join(missing)}")
        if self.block_type == "chart":
            payload = self.data or {}
            required = {"labels", "datasets"}
            missing = [k for k in required if k not in payload]
            if missing:
                raise ValueError(f"chart data missing keys: {', '.join(missing)}")
        return self


class SlideContentStrategy(BaseModel):
    """SCQA-inspired strategy metadata for a slide."""

    assertion: str = Field(..., min_length=2, max_length=220)
    evidence: List[str] = Field(default_factory=list, max_length=6)
    data_anchor: str = Field(default="", max_length=160)
    page_role: Literal["argument", "evidence", "transition", "summary"] = "argument"
    density_hint: Literal["high", "medium", "low", "breathing"] = "medium"
    render_path: Literal["svg"] = "svg"


class SlidePlan(BaseModel):
    """Wireframe + finalized content for one slide."""

    page_number: int = Field(..., ge=1, le=200)
    slide_type: SlideType
    layout_grid: str = Field(..., min_length=3, max_length=50)
    blocks: List[ContentBlock] = Field(default_factory=list, min_length=2, max_length=30)
    bg_style: Literal["light", "dark", "accent", "image"] = "light"
    image_keywords: List[str] = Field(default_factory=list, max_length=8)
    archetype: str = Field(default="", max_length=80)
    template_candidates: List[str] = Field(default_factory=list, max_length=6)
    notes_for_designer: str = Field(default="", max_length=500)
    content_strategy: Optional[SlideContentStrategy] = None

    @model_validator(mode="after")
    def validate_block_composition(self) -> "SlidePlan":
        has_title = any(block.block_type == "title" for block in self.blocks)
        has_non_title = any(block.block_type != "title" for block in self.blocks)
        if not has_title or not has_non_title:
            raise ValueError("slide plan must include title and at least one non-title block")
        return self


class PresentationPlan(BaseModel):
    """Full wireframe-level presentation plan."""

    title: str = Field(..., min_length=2, max_length=300)
    theme: str = Field(..., min_length=2, max_length=100)
    style: str = Field(..., min_length=2, max_length=50)
    slides: List[SlidePlan] = Field(default_factory=list, min_length=3, max_length=50)
    global_notes: str = Field(default="", max_length=1000)


class PresentationPlanRequest(BaseModel):
    """Input payload to generate presentation plan from outline."""

    outline: OutlinePlan
    research: Optional[ResearchContext] = None
