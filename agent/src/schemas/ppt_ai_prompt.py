"""
AI Prompt-based PPT generation schemas.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AIPromptPPTRequest(BaseModel):
    """Request for AI prompt-based PPT generation."""

    prompt: str = Field(
        ..., description="AI prompt describing the PPT content", min_length=10
    )
    total_pages: int = Field(
        default=10, ge=3, le=50, description="Total number of pages"
    )
    style: str = Field(
        default="professional",
        description="Presentation style: professional, creative, academic, minimal",
    )
    color_scheme: Optional[str] = Field(
        None, description="Color scheme: blue, red, green, purple, or auto"
    )
    language: str = Field(default="zh-CN", description="Content language: zh-CN, en-US")
    include_images: bool = Field(
        default=False, description="Whether to generate AI images"
    )
    web_enrichment: bool = Field(
        default=True, description="Enable web research enrichment"
    )
    image_asset_enrichment: bool = Field(
        default=True, description="Enable image asset enrichment"
    )
    template_family: Optional[str] = Field(None, description="Template family to use")

    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "Create a university class presentation on the Strait of Hormuz crisis and its impact on international relations.",
                "total_pages": 12,
                "style": "professional",
                "color_scheme": "blue",
                "language": "zh-CN",
                "include_images": False,
                "web_enrichment": True,
                "image_asset_enrichment": True,
            }
        }


class AIPromptPPTResult(BaseModel):
    """Result of AI prompt-based PPT generation."""

    success: bool
    project_name: str
    project_path: str
    total_slides: int
    generated_content: Dict[str, Any]
    design_spec: Dict[str, Any]
    output_pptx: Optional[str] = None
    artifacts: Dict[str, str]
    generation_time_seconds: float

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "project_name": "ai_gen_20260408_120000",
                "project_path": "output/ai_generation/ai_gen_20260408_120000",
                "total_slides": 12,
                "generated_content": {
                    "title": "The Strait of Hormuz Crisis",
                    "outline": [
                        "Geostrategic background",
                        "Escalation timeline",
                        "International relations impact",
                        "Risk scenarios",
                    ],
                },
                "design_spec": {
                    "primary_color": "#4472C4",
                    "font_family": "Microsoft YaHei",
                },
                "output_pptx": "output/ai_generation/ai_gen_20260408_120000/presentation.pptx",
                "generation_time_seconds": 45.2,
            }
        }
