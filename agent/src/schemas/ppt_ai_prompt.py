"""
AI Prompt-based PPT Generation Schemas
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class AIPromptPPTRequest(BaseModel):
    """Request for AI prompt-based PPT generation"""

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
    template_family: Optional[str] = Field(None, description="Template family to use")

    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "创建一份关于人工智能发展历程的演示文稿，包括AI的起源、重要里程碑、当前应用和未来展望",
                "total_pages": 12,
                "style": "professional",
                "color_scheme": "blue",
                "language": "zh-CN",
                "include_images": False,
            }
        }


class AIPromptPPTResult(BaseModel):
    """Result of AI prompt-based PPT generation"""

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
                    "title": "人工智能发展历程",
                    "outline": ["AI起源", "重要里程碑", "当前应用", "未来展望"],
                },
                "design_spec": {
                    "primary_color": "#4472C4",
                    "font_family": "Microsoft YaHei",
                },
                "output_pptx": "output/ai_generation/ai_gen_20260408_120000/presentation.pptx",
                "generation_time_seconds": 45.2,
            }
        }
