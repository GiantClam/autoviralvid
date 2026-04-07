"""
PPT Reference Reconstruction Schemas
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ReferenceReconstructionRequest(BaseModel):
    """Request for PPT reference reconstruction"""

    reference_ppt_url: str = Field(
        ..., description="URL or path to reference PPTX file"
    )
    target_audience: str = Field(default="大学生", description="Target audience")
    style_objective: str = Field(default="学术清晰", description="Style objective")
    project_name: Optional[str] = Field(None, description="Optional project name")
    with_export: bool = Field(default=False, description="Whether to export final PPTX")

    class Config:
        json_schema_extra = {
            "example": {
                "reference_ppt_url": "https://example.com/reference.pptx",
                "target_audience": "大学生",
                "style_objective": "学术清晰",
                "with_export": True,
            }
        }


class ReferenceReconstructionResult(BaseModel):
    """Result of PPT reference reconstruction"""

    success: bool
    project_name: str
    project_path: str
    reference_ppt: str
    total_slides: int
    extracted_colors: List[str]
    extracted_fonts: List[str]
    primary_color: str
    primary_font: str
    artifacts: Dict[str, str]
    presentation_plan: Optional[Dict[str, Any]] = None
    export_result: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "project_name": "recon_presentation_20260408",
                "project_path": "output/reference_reconstruction/recon_presentation_20260408",
                "reference_ppt": "reference.pptx",
                "total_slides": 12,
                "extracted_colors": ["#c1121f", "#669bbc", "#003049"],
                "extracted_fonts": ["Microsoft YaHei", "Arial"],
                "primary_color": "#c1121f",
                "primary_font": "Microsoft YaHei",
                "artifacts": {
                    "parsed_json": "output/.../parsed_reference.json",
                    "design_spec_json": "output/.../design_spec.json",
                },
            }
        }
