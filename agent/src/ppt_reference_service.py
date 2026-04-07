"""
PPT Reference Reconstruction Service
Integrates ppt-master style reference reconstruction into the main pipeline
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from src.ppt_reference_parser import PPTParser
from src.ppt_reference_strategist import Strategist
from src.schemas.ppt import SlideContent
from src.schemas.ppt_plan import PresentationPlan


class PPTReferenceReconstructionService:
    """
    Service for reconstructing PPT from reference file
    Uses ppt-master approach: parse → design_spec → render
    """

    def __init__(self):
        self.output_base = Path("output/reference_reconstruction")
        self.output_base.mkdir(parents=True, exist_ok=True)

    async def reconstruct_from_reference(
        self,
        reference_ppt_path: str,
        target_audience: str = "大学生",
        style_objective: str = "学术清晰",
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reconstruct PPT from reference file

        Args:
            reference_ppt_path: Path to reference PPTX
            target_audience: Target audience
            style_objective: Style objective
            project_name: Optional project name

        Returns:
            Reconstruction result with parsed data and design spec
        """

        # Create project directory
        if not project_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            project_name = f"recon_{Path(reference_ppt_path).stem}_{timestamp}"

        project_path = self.output_base / project_name
        project_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (project_path / "sources").mkdir(exist_ok=True)
        (project_path / "artifacts").mkdir(exist_ok=True)

        # Copy reference PPT
        ref_copy = project_path / "sources" / Path(reference_ppt_path).name
        shutil.copy2(reference_ppt_path, ref_copy)

        # Step 1: Parse reference PPT
        parser = PPTParser(reference_ppt_path)
        parsed_data = parser.parse()

        # Save parsed data
        parsed_json = project_path / "artifacts" / "parsed_reference.json"
        with open(parsed_json, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, indent=2, ensure_ascii=False)

        # Step 2: Generate design spec
        strategist = Strategist(parsed_data, str(project_path))
        design_spec = strategist.generate_design_spec(
            target_audience=target_audience, style_objective=style_objective
        )

        # Save design spec
        design_spec_json = project_path / "artifacts" / "design_spec.json"
        with open(design_spec_json, "w", encoding="utf-8") as f:
            json.dump(design_spec, f, indent=2, ensure_ascii=False)

        strategist.save_design_spec(str(design_spec_json))

        # Step 3: Convert to presentation plan format (for compatibility)
        presentation_plan = self._convert_to_presentation_plan(design_spec)

        result = {
            "success": True,
            "project_name": project_name,
            "project_path": str(project_path),
            "reference_ppt": reference_ppt_path,
            "parsed_data": parsed_data,
            "design_spec": design_spec,
            "presentation_plan": presentation_plan,
            "artifacts": {
                "parsed_json": str(parsed_json),
                "design_spec_json": str(design_spec_json),
                "design_spec_md": str(project_path / "design_spec.md"),
            },
        }

        # Save result
        result_file = project_path / "reconstruction_result.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        return result

    def _convert_to_presentation_plan(
        self, design_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert design spec to presentation plan format for compatibility"""

        slides = []
        for page in design_spec.get("content_outline", []):
            slide = {
                "page_number": page.get("page_number", 1),
                "slide_type": page.get("slide_type", "content"),
                "title": page.get("title", ""),
                "layout_grid": self._map_layout_type(page.get("layout_type", "mixed")),
                "content_blocks": page.get("content_blocks", []),
                "design_notes": page.get("design_notes", ""),
                "template_family": design_spec.get("typography", {}).get(
                    "primary_font", ""
                ),
                "style_variant": "soft",
                "palette_key": design_spec.get("color_scheme", {}).get(
                    "primary", "#4472C4"
                ),
            }
            slides.append(slide)

        return {
            "title": design_spec.get("metadata", {}).get("project_name", ""),
            "total_pages": len(slides),
            "slides": slides,
            "theme": {
                "primary_color": design_spec.get("color_scheme", {}).get(
                    "primary", "#4472C4"
                ),
                "secondary_color": design_spec.get("color_scheme", {}).get(
                    "secondary", "#ED7D31"
                ),
                "accent_color": design_spec.get("color_scheme", {}).get(
                    "accent", "#A5A5A5"
                ),
                "background_color": design_spec.get("color_scheme", {}).get(
                    "background", "#FFFFFF"
                ),
                "font_family": design_spec.get("typography", {}).get(
                    "primary_font", "Arial"
                ),
            },
            "metadata": {
                "source": "reference_reconstruction",
                "target_audience": design_spec.get("target_audience", ""),
                "style_objective": design_spec.get("style_objective", ""),
            },
        }

    def _map_layout_type(self, layout_type: str) -> str:
        """Map parsed layout type to layout_grid"""
        mapping = {
            "title_only": "hero_1",
            "text_heavy": "text_2col",
            "text_image": "image_right_1",
            "image_heavy": "image_full",
            "mixed": "flex_2x2",
        }
        return mapping.get(layout_type, "flex_2x2")


async def reconstruct_ppt_from_reference(
    reference_ppt_path: str,
    target_audience: str = "大学生",
    style_objective: str = "学术清晰",
) -> Dict[str, Any]:
    """
    Convenience function for PPT reference reconstruction

    Args:
        reference_ppt_path: Path to reference PPTX
        target_audience: Target audience
        style_objective: Style objective

    Returns:
        Reconstruction result
    """
    service = PPTReferenceReconstructionService()
    return await service.reconstruct_from_reference(
        reference_ppt_path, target_audience, style_objective
    )
