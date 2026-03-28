"""Sticky-note outline schemas for PPT planning workflow."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, model_validator

from src.schemas.ppt_research import ResearchContext


LayoutType = Literal[
    "cover",
    "summary",
    "hero_1",
    "split_2",
    "asymmetric_2",
    "grid_3",
    "grid_4",
    "bento_5",
    "bento_6",
    "timeline",
]


class StickyNote(BaseModel):
    """One sticky note per slide."""

    page_number: int = Field(..., ge=1, le=200)
    core_message: str = Field(..., min_length=2, max_length=30)
    layout_hint: LayoutType
    content_density: Literal["low", "medium", "high"] = "medium"
    data_elements: List[str] = Field(default_factory=list, max_length=12)
    visual_anchor: str = Field(default="text", max_length=80)
    key_points: List[str] = Field(default_factory=list, min_length=3, max_length=7)
    speaker_notes: str = Field(default="", max_length=200)


class OutlinePlan(BaseModel):
    """Full sticky-note outline plan."""

    title: str = Field(..., min_length=2, max_length=300)
    total_pages: int = Field(..., ge=3, le=50)
    theme_suggestion: str = Field(default="slate_minimal", max_length=100)
    style_suggestion: str = Field(default="soft", max_length=50)
    notes: List[StickyNote] = Field(default_factory=list, min_length=3, max_length=50)
    logic_flow: str = Field(..., min_length=8, max_length=1000)

    @model_validator(mode="after")
    def validate_outline(self) -> "OutlinePlan":
        if self.total_pages != len(self.notes):
            raise ValueError("total_pages must equal number of notes")
        if self.notes[0].layout_hint != "cover":
            raise ValueError("first note layout_hint must be cover")
        if self.notes[-1].layout_hint != "summary":
            raise ValueError("last note layout_hint must be summary")
        for idx in range(1, len(self.notes)):
            if self.notes[idx].layout_hint == self.notes[idx - 1].layout_hint:
                raise ValueError("adjacent notes cannot use the same layout_hint")
        return self


class OutlinePlanRequest(BaseModel):
    """Input payload to generate sticky-note outline."""

    research: ResearchContext
    total_pages: int = Field(default=10, ge=3, le=50)

