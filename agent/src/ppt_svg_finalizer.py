"""Unified SVG post-processing entry for PPT pipeline."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List
from xml.etree import ElementTree as ET


_DEFAULT_STEPS = (
    "embed_icons",
    "crop_images",
    "fix_aspect",
    "embed_images",
    "flatten_text",
    "fix_rounded",
)


@dataclass
class SVGFinalizationResult:
    success: bool
    steps_run: List[str] = field(default_factory=list)
    skipped_steps: List[str] = field(default_factory=list)
    step_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    processed_files: int = 0


class PPTSvgFinalizer:
    """Run ppt-master style SVG post-processing in one place."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        strict: bool = False,
        helper_root: Path | None = None,
    ) -> None:
        self.enabled = (
            enabled
            if enabled is not None
            else str(os.getenv("PPT_SVG_FINALIZER_ENABLED", "true")).strip().lower()
            not in {"0", "false", "no", "off"}
        )
        self.strict = bool(strict)
        self.helper_root = helper_root or self._default_helper_root()
        self.icons_dir = self.helper_root.parent / "templates" / "icons"

    @staticmethod
    def _default_helper_root() -> Path:
        repo_root = Path(__file__).resolve().parents[2]
        return (
            repo_root
            / "vendor"
            / "minimax-skills"
            / "skills"
            / "ppt-master"
            / "scripts"
        )

    def _load_helpers(self) -> Dict[str, Callable[..., Any]]:
        if not self.helper_root.exists():
            return {}
        helper_root_str = str(self.helper_root)
        if helper_root_str not in sys.path:
            sys.path.insert(0, helper_root_str)
        try:
            from svg_finalize.crop_images import process_svg_images
            from svg_finalize.embed_icons import process_svg_file
            from svg_finalize.embed_images import embed_images_in_svg
            from svg_finalize.fix_image_aspect import fix_image_aspect_in_svg
            from svg_finalize.flatten_tspan import flatten_text_with_tspans
            from svg_finalize.svg_rect_to_path import process_svg
        except Exception:
            return {}
        return {
            "crop_images": process_svg_images,
            "embed_icons": process_svg_file,
            "embed_images": embed_images_in_svg,
            "fix_aspect": fix_image_aspect_in_svg,
            "flatten_text": flatten_text_with_tspans,
            "fix_rounded": process_svg,
        }

    def finalize_project(
        self,
        project_dir: Path | str,
        *,
        source_dir: str = "svg_output",
        target_dir: str = "svg_final",
        steps: Iterable[str] | None = None,
    ) -> SVGFinalizationResult:
        root = Path(project_dir)
        src = root / source_dir
        dst = root / target_dir
        if not src.exists():
            return SVGFinalizationResult(
                success=False,
                errors=[f"source_dir_missing:{src}"],
            )
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        files = sorted(dst.glob("*.svg"))
        return self.finalize_svg_files(files, steps=steps)

    def finalize_svg_files(
        self,
        svg_files: Iterable[Path | str],
        *,
        steps: Iterable[str] | None = None,
    ) -> SVGFinalizationResult:
        files = [Path(item) for item in svg_files]
        result = SVGFinalizationResult(success=True, processed_files=len(files))
        if not files:
            return result
        selected_steps = [
            str(step or "").strip().lower()
            for step in (steps or _DEFAULT_STEPS)
            if str(step or "").strip()
        ]
        if not self.enabled:
            result.skipped_steps.extend(selected_steps)
            return result
        helpers = self._load_helpers()
        if not helpers:
            result.skipped_steps.extend(selected_steps)
            result.errors.append("finalizer_helpers_unavailable")
            result.success = not self.strict
            return result

        for step in selected_steps:
            stats = {"changed": 0, "errors": 0}
            try:
                if step == "embed_icons":
                    fn = helpers["embed_icons"]
                    for svg_file in files:
                        try:
                            changed = int(
                                fn(
                                    svg_file,
                                    self.icons_dir,
                                    dry_run=False,
                                    verbose=False,
                                )
                                or 0
                            )
                            stats["changed"] += max(0, changed)
                        except Exception:
                            stats["errors"] += 1
                elif step == "crop_images":
                    fn = helpers["crop_images"]
                    for svg_file in files:
                        try:
                            changed, errors = fn(
                                str(svg_file), dry_run=False, verbose=False
                            )
                            stats["changed"] += int(changed or 0)
                            stats["errors"] += int(errors or 0)
                        except Exception:
                            stats["errors"] += 1
                elif step == "fix_aspect":
                    fn = helpers["fix_aspect"]
                    for svg_file in files:
                        try:
                            changed = int(
                                fn(str(svg_file), dry_run=False, verbose=False) or 0
                            )
                            stats["changed"] += max(0, changed)
                        except Exception:
                            stats["errors"] += 1
                elif step == "embed_images":
                    fn = helpers["embed_images"]
                    for svg_file in files:
                        try:
                            changed, errors = fn(str(svg_file), dry_run=False)
                            stats["changed"] += int(changed or 0)
                            stats["errors"] += int(errors or 0)
                        except Exception:
                            stats["errors"] += 1
                elif step == "flatten_text":
                    fn = helpers["flatten_text"]
                    for svg_file in files:
                        try:
                            tree = ET.parse(str(svg_file))
                            changed = bool(fn(tree))
                            if changed:
                                tree.write(
                                    str(svg_file),
                                    encoding="unicode",
                                    xml_declaration=False,
                                )
                                stats["changed"] += 1
                        except Exception:
                            stats["errors"] += 1
                elif step == "fix_rounded":
                    fn = helpers["fix_rounded"]
                    for svg_file in files:
                        try:
                            content = svg_file.read_text(encoding="utf-8")
                            processed, changed = fn(content, verbose=False)
                            if int(changed or 0) > 0:
                                svg_file.write_text(processed, encoding="utf-8")
                                stats["changed"] += int(changed or 0)
                        except Exception:
                            stats["errors"] += 1
                else:
                    result.skipped_steps.append(step)
                    continue
            except Exception:
                stats["errors"] += 1

            result.steps_run.append(step)
            result.step_stats[step] = stats
            if stats["errors"] > 0:
                result.errors.append(f"{step}_errors={stats['errors']}")
                if self.strict:
                    result.success = False
        return result

