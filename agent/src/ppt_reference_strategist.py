"""
Strategist Module - Generate design specification from reference PPT
Based on ppt-master strategist role
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


class Strategist:
    """
    Strategist role: Generate design specification and content outline
    Based on ppt-master workflow
    """

    def __init__(self, parsed_ppt: Dict[str, Any], project_path: str):
        self.parsed_ppt = parsed_ppt
        self.project_path = Path(project_path)
        self.design_spec = {}

    def generate_design_spec(
        self,
        target_audience: str = "大学生",
        style_objective: str = "学术清晰",
        icon_approach: str = "minimal",
        image_approach: str = "preserve",
    ) -> Dict[str, Any]:
        """
        Generate design specification based on reference PPT

        Args:
            target_audience: Target audience description
            style_objective: Style objective (e.g., "学术清晰", "商务专业")
            icon_approach: Icon usage approach
            image_approach: Image handling approach

        Returns:
            Design specification dict
        """

        canvas = self.parsed_ppt.get("canvas", {})
        colors = self.parsed_ppt.get("colors", {})
        typography = self.parsed_ppt.get("typography", {})
        content_outline = self.parsed_ppt.get("content_outline", [])

        # Build design spec following ppt-master structure
        design_spec = {
            "metadata": {
                "project_name": self.project_path.name,
                "created_at": datetime.now().isoformat(),
                "source_reference": self.parsed_ppt.get("metadata", {}).get(
                    "source_file", ""
                ),
                "total_pages": len(content_outline),
            },
            "canvas": {
                "format": canvas.get("format", "ppt169"),
                "width": canvas.get("width_px", 1920),
                "height": canvas.get("height_px", 1080),
                "aspect_ratio": canvas.get("aspect_ratio", 16 / 9),
            },
            "target_audience": target_audience,
            "style_objective": style_objective,
            "color_scheme": {
                "primary": colors.get("primary_colors", ["#4472C4"])[0]
                if colors.get("primary_colors")
                else "#4472C4",
                "secondary": colors.get("primary_colors", ["#ED7D31"])[1]
                if len(colors.get("primary_colors", [])) > 1
                else "#ED7D31",
                "accent": colors.get("primary_colors", ["#A5A5A5"])[2]
                if len(colors.get("primary_colors", [])) > 2
                else "#A5A5A5",
                "background": "#FFFFFF",
                "text_primary": "#000000",
                "text_secondary": "#666666",
                "palette": colors.get("primary_colors", [])[:6],
            },
            "typography": {
                "primary_font": typography.get("primary_font", "Arial"),
                "title_size": max(typography.get("common_sizes", [24])[:1])
                if typography.get("common_sizes")
                else 24,
                "body_size": typography.get("common_sizes", [14])[1]
                if len(typography.get("common_sizes", [])) > 1
                else 14,
                "caption_size": min(typography.get("common_sizes", [12])[-2:])
                if typography.get("common_sizes")
                else 12,
                "all_fonts": typography.get("all_fonts", ["Arial"]),
            },
            "icon_approach": icon_approach,
            "image_approach": image_approach,
            "content_outline": self._build_content_outline(content_outline),
            "design_guidelines": {
                "spacing": "consistent",
                "alignment": "grid-based",
                "visual_hierarchy": "clear",
                "color_usage": "restrained",
                "consistency": "high",
            },
        }

        self.design_spec = design_spec
        return design_spec

    def _build_content_outline(
        self, content_outline: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build structured content outline for each page"""
        structured_outline = []

        for slide in content_outline:
            page_spec = {
                "page_number": slide.get("page_number", 1),
                "title": slide.get("title", ""),
                "layout_type": slide.get("layout_type", "mixed"),
                "content_blocks": [],
                "design_notes": "",
            }

            # Add body text as content blocks
            for idx, text in enumerate(slide.get("body_text", []), 1):
                page_spec["content_blocks"].append(
                    {"type": "text", "content": text, "order": idx}
                )

            # Add image placeholders
            image_elements = [
                e for e in slide.get("elements", []) if e.get("type") == "image"
            ]
            for idx, img in enumerate(
                image_elements, len(page_spec["content_blocks"]) + 1
            ):
                page_spec["content_blocks"].append(
                    {
                        "type": "image",
                        "placeholder": f"image_{slide.get('page_number')}_{idx}",
                        "order": idx,
                        "position": img.get("position", {}),
                    }
                )

            # Detect slide type
            if slide.get("page_number") == 1:
                page_spec["slide_type"] = "cover"
            elif not slide.get("body_text") and len(image_elements) == 0:
                page_spec["slide_type"] = "divider"
            else:
                page_spec["slide_type"] = "content"

            structured_outline.append(page_spec)

        return structured_outline

    def save_design_spec(self, output_path: Optional[str] = None) -> str:
        """Save design specification to markdown file"""
        if not output_path:
            output_path = self.project_path / "design_spec.json"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.design_spec, f, indent=2, ensure_ascii=False)

        print(f"[OK] Design specification saved to: {output_path}")

        # Also save as markdown for human readability
        md_path = output_path.with_suffix(".md")
        self._save_as_markdown(md_path)

        return str(output_path)

    def _save_as_markdown(self, md_path: Path):
        """Save design spec as markdown"""
        spec = self.design_spec

        md_content = f"""# Design Specification

## Project Metadata
- **Project Name**: {spec["metadata"]["project_name"]}
- **Created**: {spec["metadata"]["created_at"]}
- **Source Reference**: {spec["metadata"]["source_reference"]}
- **Total Pages**: {spec["metadata"]["total_pages"]}

## Canvas Format
- **Format**: {spec["canvas"]["format"]}
- **Dimensions**: {spec["canvas"]["width"]}x{spec["canvas"]["height"]}px
- **Aspect Ratio**: {spec["canvas"]["aspect_ratio"]:.2f}

## Target Audience
{spec["target_audience"]}

## Style Objective
{spec["style_objective"]}

## Color Scheme
- **Primary**: {spec["color_scheme"]["primary"]}
- **Secondary**: {spec["color_scheme"]["secondary"]}
- **Accent**: {spec["color_scheme"]["accent"]}
- **Background**: {spec["color_scheme"]["background"]}
- **Text Primary**: {spec["color_scheme"]["text_primary"]}
- **Text Secondary**: {spec["color_scheme"]["text_secondary"]}

**Full Palette**: {", ".join(spec["color_scheme"]["palette"])}

## Typography
- **Primary Font**: {spec["typography"]["primary_font"]}
- **Title Size**: {spec["typography"]["title_size"]}pt
- **Body Size**: {spec["typography"]["body_size"]}pt
- **Caption Size**: {spec["typography"]["caption_size"]}pt

## Content Outline

"""

        for page in spec["content_outline"]:
            md_content += f"""### Page {page["page_number"]}: {page["title"] or "(No Title)"}
- **Type**: {page["slide_type"]}
- **Layout**: {page["layout_type"]}
- **Content Blocks**: {len(page["content_blocks"])}

"""

            for block in page["content_blocks"]:
                if block["type"] == "text":
                    preview = (
                        block["content"][:80] + "..."
                        if len(block["content"]) > 80
                        else block["content"]
                    )
                    md_content += f"  - Text: {preview}\n"
                elif block["type"] == "image":
                    md_content += f"  - Image: {block['placeholder']}\n"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"[OK] Design specification (markdown) saved to: {md_path}")


def generate_design_spec_from_reference(
    parsed_ppt: Dict[str, Any],
    project_path: str,
    target_audience: str = "大学生",
    style_objective: str = "学术清晰",
) -> Dict[str, Any]:
    """
    Generate design specification from parsed reference PPT

    Args:
        parsed_ppt: Parsed PPT structure from ppt_parser
        project_path: Project directory path
        target_audience: Target audience
        style_objective: Style objective

    Returns:
        Design specification dict
    """
    strategist = Strategist(parsed_ppt, project_path)
    design_spec = strategist.generate_design_spec(
        target_audience=target_audience, style_objective=style_objective
    )
    strategist.save_design_spec()

    return design_spec


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python strategist.py <parsed_ppt_json> <project_path>")
        sys.exit(1)

    parsed_json = sys.argv[1]
    project_path = sys.argv[2]

    with open(parsed_json, "r", encoding="utf-8") as f:
        parsed_ppt = json.load(f)

    design_spec = generate_design_spec_from_reference(parsed_ppt, project_path)
    print(f"✓ Generated design spec with {len(design_spec['content_outline'])} pages")
