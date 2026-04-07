"""
PPT Master Integration Service
Provides a bridge to run ppt-master workflow in the current project
"""

import os
import sys
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio


class PPTMasterService:
    """
    Service to integrate ppt-master workflow
    Provides AI prompt-based PPT generation using ppt-master's complete pipeline
    """

    def __init__(self):
        # Locate ppt-master directory
        self.ppt_master_root = (
            Path(__file__).parent.parent.parent
            / "vendor"
            / "minimax-skills"
            / "skills"
            / "ppt-master"
        )
        if not self.ppt_master_root.exists():
            raise RuntimeError(f"ppt-master not found at {self.ppt_master_root}")

        self.scripts_dir = self.ppt_master_root / "scripts"
        self.templates_dir = self.ppt_master_root / "templates"
        self.references_dir = self.ppt_master_root / "references"

        # Output directory
        self.output_base = Path("output/ppt_master_projects")
        self.output_base.mkdir(parents=True, exist_ok=True)

    async def generate_from_prompt(
        self,
        prompt: str,
        total_pages: int = 10,
        style: str = "professional",
        color_scheme: Optional[str] = None,
        language: str = "zh-CN",
        template_name: Optional[str] = None,
        include_images: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate PPT from AI prompt using ppt-master workflow

        Args:
            prompt: AI prompt describing the PPT content
            total_pages: Total number of pages
            style: Presentation style
            color_scheme: Color scheme
            language: Content language
            template_name: Optional template name
            include_images: Whether to generate AI images

        Returns:
            Generation result with project path and artifacts
        """

        start_time = datetime.now()

        # Create project
        project_name = f"ai_gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        project_path = await self._create_project(project_name)

        try:
            # Step 1: Create source content from prompt
            source_md = await self._create_source_from_prompt(
                project_path, prompt, total_pages, language
            )

            # Step 2: Select template (if specified)
            if template_name:
                await self._copy_template(project_path, template_name)

            # Step 3: Generate design spec (Strategist phase)
            design_spec = await self._generate_design_spec(
                project_path,
                source_md,
                total_pages,
                style,
                color_scheme,
                language,
                template_name,
            )

            # Step 4: Generate images (if requested)
            if include_images:
                await self._generate_images(project_path, design_spec)

            # Step 5: Generate SVG pages (Executor phase)
            svg_files = await self._generate_svg_pages(project_path, design_spec, style)

            # Step 6: Post-process SVG
            await self._postprocess_svg(project_path)

            # Step 7: Export to PPTX
            output_pptx = await self._export_pptx(project_path)

            end_time = datetime.now()
            generation_time = (end_time - start_time).total_seconds()

            result = {
                "success": True,
                "project_name": project_name,
                "project_path": str(project_path),
                "total_slides": total_pages,
                "generated_content": {
                    "source_md": str(source_md),
                    "design_spec": str(project_path / "design_spec.md"),
                },
                "design_spec": design_spec,
                "svg_files": [str(f) for f in svg_files],
                "output_pptx": str(output_pptx) if output_pptx else None,
                "artifacts": {
                    "project_path": str(project_path),
                    "svg_output": str(project_path / "svg_output"),
                    "svg_final": str(project_path / "svg_final"),
                },
                "generation_time_seconds": generation_time,
            }

            # Save result
            result_file = project_path / "generation_result.json"
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "project_name": project_name,
                "project_path": str(project_path),
            }

    async def _create_project(self, project_name: str) -> Path:
        """Create project structure using ppt-master's project_manager.py"""

        project_path = self.output_base / project_name

        # Use ppt-master's project_manager.py
        cmd = [
            sys.executable,
            str(self.scripts_dir / "project_manager.py"),
            "init",
            str(project_path),
            "--format",
            "ppt169",
        ]

        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.scripts_dir),
        )

        stdout, stderr = await result.communicate()

        if result.returncode != 0:
            raise RuntimeError(f"Project creation failed: {stderr.decode()}")

        return project_path

    async def _create_source_from_prompt(
        self, project_path: Path, prompt: str, total_pages: int, language: str
    ) -> Path:
        """Create source markdown from AI prompt"""

        # Use LLM to expand prompt into structured content
        from src.llm_client import get_llm_client

        llm = get_llm_client()

        system_prompt = f"""You are a professional presentation content creator.
Given a user prompt, create a detailed outline for a {total_pages}-page presentation.

Output format (Markdown):
# [Presentation Title]

## Page 1: [Title]
[Content description]

## Page 2: [Title]
[Content description]

... (continue for all {total_pages} pages)

Language: {language}
Style: Professional and clear
"""

        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )

        content = response.get("content", "")

        # Save to sources
        sources_dir = project_path / "sources"
        sources_dir.mkdir(exist_ok=True)

        source_md = sources_dir / "content.md"
        with open(source_md, "w", encoding="utf-8") as f:
            f.write(content)

        return source_md

    async def _copy_template(self, project_path: Path, template_name: str):
        """Copy template files to project"""

        template_src = self.templates_dir / "layouts" / template_name
        if not template_src.exists():
            raise ValueError(f"Template not found: {template_name}")

        template_dst = project_path / "templates"
        template_dst.mkdir(exist_ok=True)

        # Copy SVG files
        for svg_file in template_src.glob("*.svg"):
            shutil.copy2(svg_file, template_dst / svg_file.name)

        # Copy design_spec.md
        design_spec_src = template_src / "design_spec.md"
        if design_spec_src.exists():
            shutil.copy2(design_spec_src, template_dst / "design_spec.md")

        # Copy images
        for img_file in template_src.glob("*.png"):
            images_dir = project_path / "images"
            images_dir.mkdir(exist_ok=True)
            shutil.copy2(img_file, images_dir / img_file.name)

        for img_file in template_src.glob("*.jpg"):
            images_dir = project_path / "images"
            images_dir.mkdir(exist_ok=True)
            shutil.copy2(img_file, images_dir / img_file.name)

    async def _generate_design_spec(
        self,
        project_path: Path,
        source_md: Path,
        total_pages: int,
        style: str,
        color_scheme: Optional[str],
        language: str,
        template_name: Optional[str],
    ) -> Dict[str, Any]:
        """Generate design specification (Strategist phase)"""

        from src.llm_client import get_llm_client

        llm = get_llm_client()

        # Read source content
        with open(source_md, "r", encoding="utf-8") as f:
            source_content = f.read()

        # Read strategist reference
        strategist_ref = self.references_dir / "strategist.md"
        with open(strategist_ref, "r", encoding="utf-8") as f:
            strategist_guide = f.read()

        # Read template design spec if exists
        template_spec = ""
        if template_name:
            template_spec_file = project_path / "templates" / "design_spec.md"
            if template_spec_file.exists():
                with open(template_spec_file, "r", encoding="utf-8") as f:
                    template_spec = f.read()

        system_prompt = f"""You are a professional presentation strategist following ppt-master workflow.

Reference guide:
{strategist_guide[:3000]}

Template specification:
{template_spec[:2000] if template_spec else "No template - free design"}

Task: Generate a complete design specification for this presentation.
Output format: Follow the design_spec.md structure from the reference guide.
"""

        user_prompt = f"""Source content:
{source_content}

Requirements:
- Total pages: {total_pages}
- Style: {style}
- Color scheme: {color_scheme or "auto"}
- Language: {language}
- Template: {template_name or "free design"}

Generate the complete design specification in Markdown format.
"""

        response = await llm.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
        )

        design_spec_content = response.get("content", "")

        # Save design spec
        design_spec_file = project_path / "design_spec.md"
        with open(design_spec_file, "w", encoding="utf-8") as f:
            f.write(design_spec_content)

        # Parse design spec to dict
        design_spec = {
            "file": str(design_spec_file),
            "content": design_spec_content,
            "total_pages": total_pages,
            "style": style,
            "color_scheme": color_scheme,
            "language": language,
        }

        return design_spec

    async def _generate_images(self, project_path: Path, design_spec: Dict[str, Any]):
        """Generate AI images (Image_Generator phase)"""

        # Use ppt-master's image_gen.py
        images_dir = project_path / "images"
        images_dir.mkdir(exist_ok=True)

        # For now, skip image generation (can be implemented later)
        pass

    async def _generate_svg_pages(
        self, project_path: Path, design_spec: Dict[str, Any], style: str
    ) -> List[Path]:
        """Generate SVG pages (Executor phase)"""

        from src.llm_client import get_llm_client

        llm = get_llm_client()

        # Read executor reference based on style
        executor_base = self.references_dir / "executor-base.md"
        with open(executor_base, "r", encoding="utf-8") as f:
            executor_base_guide = f.read()

        executor_style_map = {
            "professional": "executor-general.md",
            "consulting": "executor-consultant.md",
            "academic": "executor-general.md",
            "minimal": "executor-general.md",
        }

        executor_style_file = self.references_dir / executor_style_map.get(
            style, "executor-general.md"
        )
        with open(executor_style_file, "r", encoding="utf-8") as f:
            executor_style_guide = f.read()

        # Read design spec
        design_spec_file = Path(design_spec["file"])
        with open(design_spec_file, "r", encoding="utf-8") as f:
            design_spec_content = f.read()

        svg_output_dir = project_path / "svg_output"
        svg_output_dir.mkdir(exist_ok=True)

        total_pages = design_spec.get("total_pages", 10)
        svg_files = []

        system_prompt = f"""You are a professional SVG page designer following ppt-master executor workflow.

Base guidelines:
{executor_base_guide[:2000]}

Style-specific guidelines:
{executor_style_guide[:2000]}

Design specification:
{design_spec_content[:3000]}

Task: Generate SVG pages one by one following the design spec.
Output: Complete SVG code for each page.
"""

        # Generate pages sequentially
        for page_num in range(1, total_pages + 1):
            user_prompt = f"""Generate SVG for page {page_num} of {total_pages}.

Requirements:
- Follow the design spec strictly
- Use proper SVG structure
- Include all content for this page
- Canvas: 1280x720 (16:9)

Output only the complete SVG code, no explanations.
"""

            response = await llm.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )

            svg_content = response.get("content", "")

            # Extract SVG code (remove markdown code blocks if present)
            if "```" in svg_content:
                svg_content = svg_content.split("```")[1]
                if svg_content.startswith("xml") or svg_content.startswith("svg"):
                    svg_content = "\n".join(svg_content.split("\n")[1:])

            # Save SVG
            svg_file = svg_output_dir / f"page_{page_num:03d}.svg"
            with open(svg_file, "w", encoding="utf-8") as f:
                f.write(svg_content)

            svg_files.append(svg_file)

        return svg_files

    async def _postprocess_svg(self, project_path: Path):
        """Post-process SVG files using ppt-master's finalize_svg.py"""

        cmd = [
            sys.executable,
            str(self.scripts_dir / "finalize_svg.py"),
            str(project_path),
        ]

        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.scripts_dir),
        )

        stdout, stderr = await result.communicate()

        if result.returncode != 0:
            # Non-critical error, log but continue
            print(f"SVG post-processing warning: {stderr.decode()}")

    async def _export_pptx(self, project_path: Path) -> Optional[Path]:
        """Export to PPTX using ppt-master's svg_to_pptx.py"""

        cmd = [
            sys.executable,
            str(self.scripts_dir / "svg_to_pptx.py"),
            str(project_path),
            "-s",
            "final",
            "--only",
            "native",
        ]

        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.scripts_dir),
        )

        stdout, stderr = await result.communicate()

        if result.returncode != 0:
            print(f"PPTX export warning: {stderr.decode()}")
            return None

        # Find generated PPTX
        pptx_files = list(project_path.glob("*.pptx"))
        if pptx_files:
            return pptx_files[0]

        return None

    def list_available_templates(self) -> List[Dict[str, str]]:
        """List available templates"""

        layouts_dir = self.templates_dir / "layouts"
        templates = []

        for template_dir in layouts_dir.iterdir():
            if template_dir.is_dir() and template_dir.name != "__pycache__":
                design_spec = template_dir / "design_spec.md"
                description = ""
                if design_spec.exists():
                    with open(design_spec, "r", encoding="utf-8") as f:
                        first_lines = f.read(200)
                        description = first_lines.split("\n")[0] if first_lines else ""

                templates.append(
                    {
                        "name": template_dir.name,
                        "path": str(template_dir),
                        "description": description,
                    }
                )

        return templates


# Convenience function
async def generate_ppt_from_prompt(
    prompt: str, total_pages: int = 10, style: str = "professional", **kwargs
) -> Dict[str, Any]:
    """
    Generate PPT from AI prompt using ppt-master

    Args:
        prompt: AI prompt describing the PPT content
        total_pages: Total number of pages
        style: Presentation style
        **kwargs: Additional options

    Returns:
        Generation result
    """
    service = PPTMasterService()
    return await service.generate_from_prompt(
        prompt=prompt, total_pages=total_pages, style=style, **kwargs
    )
