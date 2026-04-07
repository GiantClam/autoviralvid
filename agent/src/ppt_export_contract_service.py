"""Contract helpers for post-export slide metadata."""

from __future__ import annotations

from typing import Any, Dict, List


class PPTExportContractService:
    """Builds normalized final slide contract metadata."""

    def build_final_slide_contract(self, slides: List[Dict[str, Any]] | Any) -> List[Dict[str, Any]]:
        if not isinstance(slides, list):
            return []
        out: List[Dict[str, Any]] = []
        for idx, slide in enumerate(slides):
            if not isinstance(slide, dict):
                continue
            out.append(
                {
                    "index": idx,
                    "slide_id": str(
                        slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}"
                    ),
                    "slide_type": str(slide.get("slide_type") or slide.get("type") or "")
                    .strip()
                    .lower(),
                    "layout_grid": str(slide.get("layout_grid") or slide.get("layout") or "")
                    .strip()
                    .lower(),
                    "template_family": str(
                        slide.get("template_family") or slide.get("template_id") or ""
                    )
                    .strip()
                    .lower(),
                }
            )
        return out

