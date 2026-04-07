"""PPT data schemas for both PPT and video generation APIs."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class SlideOutline(BaseModel):
    """Single slide outline item."""

    id: str = Field(default_factory=_new_id)
    order: int = 0
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1000)
    key_points: List[str] = Field(default_factory=list, max_length=10)
    suggested_elements: List[str] = Field(default_factory=list)
    estimated_duration: int = Field(default=120, ge=10, le=600)


class PresentationOutline(BaseModel):
    """Presentation outline."""

    id: str = Field(default_factory=_new_id)
    title: str = Field(default="", max_length=300)
    theme: str = "default"
    slides: List[SlideOutline] = Field(default_factory=list, max_length=50)
    total_duration: int = 0
    style: Literal["professional", "education", "creative"] = "professional"


class SlideElement(BaseModel):
    """Visual/content element on a slide."""

    id: str = Field(default_factory=_new_id)
    block_id: Optional[str] = Field(default=None, max_length=128)
    type: Literal["text", "image", "shape", "chart", "table", "latex", "video", "audio"]
    left: float = Field(default=0, ge=0, le=10000)
    top: float = Field(default=0, ge=0, le=10000)
    width: float = Field(default=200, ge=1, le=10000)
    height: float = Field(default=100, ge=1, le=10000)
    content: Optional[str] = Field(default=None, max_length=50000)
    src: Optional[str] = Field(default=None, max_length=2048)
    style: Optional[Dict[str, Any]] = None
    chart_type: Optional[str] = None
    chart_data: Optional[Dict[str, Any]] = None
    table_rows: Optional[List[List[str]]] = None
    table_col_widths: Optional[List[float]] = None
    latex_formula: Optional[str] = None

    @model_validator(mode="after")
    def ensure_block_id(self) -> "SlideElement":
        if not self.block_id:
            self.block_id = self.id
        return self


class SlideBackground(BaseModel):
    """Slide background."""

    type: Literal["solid", "gradient", "image"] = "solid"
    color: str = "#ffffff"
    gradient: Optional[Dict[str, Any]] = None
    image_url: Optional[str] = None


class SlideContent(BaseModel):
    """Fully generated slide content."""

    # Preserve rich render-contract fields (slide_type/layout_grid/blocks/template_family...)
    # when /api/v1/ppt/export receives pipeline-level slide payloads.
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=_new_id)
    slide_id: Optional[str] = Field(default=None, max_length=128)
    outline_id: str = ""
    order: int = 0
    title: str = Field(default="", max_length=300)
    elements: List[SlideElement] = Field(default_factory=list, max_length=50)
    background: SlideBackground = Field(default_factory=SlideBackground)
    narration: str = Field(default="", max_length=10000)
    narration_audio_url: Optional[str] = None
    speaker_notes: str = Field(default="", max_length=10000)
    duration: int = Field(default=120, ge=10, le=600)

    @model_validator(mode="after")
    def ensure_slide_id(self) -> "SlideContent":
        if not self.slide_id:
            self.slide_id = self.id
        return self


class ParsedDocument(BaseModel):
    """Result of PPT/PDF parsing."""

    source_type: Literal["pptx", "ppt", "pdf"] = "pptx"
    source_url: str = ""
    title: str = ""
    slides: List[SlideContent] = Field(default_factory=list)
    total_pages: int = 0


class VideoRenderConfig(BaseModel):
    """Video render config."""

    width: int = Field(default=1920, ge=480, le=3840)
    height: int = Field(default=1080, ge=360, le=2160)
    fps: int = Field(default=30, ge=15, le=60)
    transition: Literal["fade", "slide", "wipe"] = "fade"
    bgm_url: Optional[str] = None
    bgm_volume: float = Field(default=0.15, ge=0, le=1)
    include_narration: bool = True
    voice_style: str = "zh-CN-female"


class RenderJob(BaseModel):
    """Video render job."""

    id: str = Field(default_factory=_new_id)
    project_id: str = ""
    status: Literal["pending", "rendering", "done", "failed"] = "pending"
    progress: float = 0
    lambda_job_id: Optional[str] = None
    output_url: Optional[str] = None
    error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class OutlineRequest(BaseModel):
    """Outline generation request."""

    requirement: str = Field(..., min_length=2, max_length=5000)
    language: Literal["zh-CN", "en-US"] = "zh-CN"
    num_slides: int = Field(default=10, ge=1, le=50)
    style: Literal["professional", "education", "creative"] = "professional"
    purpose: str = Field(default="", max_length=500)


class ContentRequest(BaseModel):
    """Content generation request."""

    outline: PresentationOutline
    language: Literal["zh-CN", "en-US"] = "zh-CN"


class ExportRequest(BaseModel):
    """PPTX export request."""

    slides: List[SlideContent] = Field(..., max_length=50)
    deck_id: str = Field(default_factory=_new_id, max_length=128)
    title: str = Field(default="演示文稿", max_length=300)
    author: str = Field(default="AutoViralVid", max_length=100)
    pptx_skill: Literal["minimax_pptx_generator"] = "minimax_pptx_generator"
    minimax_style_variant: Literal["auto", "sharp", "soft", "rounded", "pill"] = "auto"
    minimax_palette_key: str = Field(default="auto", max_length=64)
    verbatim_content: bool = False
    retry_scope: Literal["deck"] = "deck"
    retry_hint: str = Field(default="", max_length=2000)
    target_slide_ids: List[str] = Field(default_factory=list, max_length=50)
    target_block_ids: List[str] = Field(default_factory=list, max_length=500)
    idempotency_key: Optional[str] = Field(default=None, max_length=128)
    template_file_url: Optional[str] = Field(default=None, max_length=2048)
    route_mode: Literal["auto", "fast", "standard", "refine"] = "auto"
    export_channel: Literal["auto", "local"] = "local"
    generator_mode: Literal["auto", "official", "legacy"] = "official"
    original_style: bool = False
    disable_local_style_rewrite: bool = False
    visual_priority: bool = True
    visual_preset: Literal["auto", "tech_cinematic", "executive_brief", "premium_light", "energetic"] = "auto"
    theme_recipe: str = Field(default="auto", max_length=64)
    tone: Literal["auto", "light", "dark"] = "auto"
    visual_density: Literal["sparse", "balanced", "dense"] = "balanced"
    execution_profile: Literal["auto", "dev_strict", "prod_safe"] = "auto"
    force_ppt_master: Optional[bool] = None
    constraint_hardness: Literal["minimal", "balanced", "strict"] = "minimal"
    svg_mode: Literal["off", "on"] = "on"
    template_family: str = Field(default="auto", max_length=128)
    skill_profile: str = Field(default="auto", max_length=64)
    hardness_profile: Literal["auto", "minimal", "balanced", "strict"] = "auto"
    schema_profile: str = Field(default="auto", max_length=128)
    contract_profile: str = Field(default="auto", max_length=64)
    quality_profile: str = Field(default="auto", max_length=64)
    enforce_visual_contract: bool = True

    @field_validator("target_slide_ids", "target_block_ids")
    @classmethod
    def dedup_ids(cls, value: List[str]) -> List[str]:
        dedup: List[str] = []
        seen = set()
        for item in value:
            key = str(item or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            dedup.append(key)
        return dedup

    @field_validator("template_file_url")
    @classmethod
    def validate_template_file_url(cls, value: Optional[str]) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        if not (text.startswith("http://") or text.startswith("https://")):
            raise ValueError("template_file_url must start with http:// or https://")
        return text

    @field_validator("template_family")
    @classmethod
    def validate_template_family(cls, value: str) -> str:
        text = str(value or "").strip().lower()
        return text or "auto"


class ParseRequest(BaseModel):
    """Document parse request."""

    file_url: str = Field(..., min_length=1, max_length=2048)
    file_type: Literal["pptx", "ppt", "pdf"] = "pptx"

    @field_validator("file_url")
    @classmethod
    def validate_file_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("file_url must start with http:// or https://")
        return v


class VideoRenderRequest(BaseModel):
    """Video render request."""

    # Accept raw dict slides to avoid mixed Union coercion:
    # semantic slides may include `markdown/script/actions`, while
    # absolute-layout slides include `elements/background/...`.
    # If we use `SlideContent | Dict[...]`, pydantic may partially coerce
    # some semantic slides into SlideContent and drop `markdown`, causing
    # "undefined" frames during Marp rendering.
    slides: List[Dict[str, Any]] = Field(..., min_length=1, max_length=50)
    config: VideoRenderConfig = Field(default_factory=VideoRenderConfig)
    idempotency_key: Optional[str] = Field(default=None, max_length=64)

    @field_validator("slides")
    @classmethod
    def validate_render_slides(cls, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for idx, slide in enumerate(value):
            if not isinstance(slide, dict):
                raise ValueError(f"slides[{idx}] must be an object")
            has_markdown = isinstance(slide.get("markdown"), str) and bool(
                str(slide.get("markdown")).strip()
            )
            has_elements = isinstance(slide.get("elements"), list)
            has_image = bool(
                str(slide.get("imageUrl") or slide.get("image_url") or "").strip()
            )
            if not (has_markdown or has_elements or has_image):
                raise ValueError(
                    f"slides[{idx}] must contain markdown (semantic), elements (layout), or imageUrl (ppt image)"
                )
        return value


class ApiResponse(BaseModel):
    """Standard API response envelope."""

    success: bool = True
    data: Optional[Any] = None
    error: Optional[Any] = None
