"""Media output helpers for export flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass(frozen=True)
class PPTExportMediaResult:
    png_bytes_list: List[bytes]
    slide_image_urls: List[str]
    video_mode: Optional[str]
    video_slides: Optional[List[Dict[str, Any]]]
    video_slide_count: Optional[int]


class PPTExportMediaService:
    """Build slide image URLs and normalized video slide fields."""

    async def build_media_outputs(
        self,
        *,
        project_id: str,
        export_pptx_bytes: bytes,
        initial_png_bytes_list: List[bytes],
        route_policy_force_rasterization: bool,
        render_spec: Dict[str, Any],
        slides_data: List[Dict[str, Any]],
        rasterize_pptx_bytes_to_png_bytes: Callable[[bytes], List[bytes]],
        upload_bytes_to_r2: Callable[..., Awaitable[str]],
        build_image_video_slides: Callable[[List[str], List[Dict[str, Any]]], List[Dict[str, Any]]],
        logger_warning: Callable[[str, Any], None],
    ) -> PPTExportMediaResult:
        png_bytes_list: List[bytes] = list(initial_png_bytes_list or [])
        slide_image_urls: List[str] = []
        try:
            if (not png_bytes_list) and route_policy_force_rasterization:
                png_bytes_list = rasterize_pptx_bytes_to_png_bytes(export_pptx_bytes)
            for idx, png_bytes in enumerate(png_bytes_list):
                image_url = await upload_bytes_to_r2(
                    png_bytes,
                    key=f"projects/{project_id}/slides/slide_{idx + 1:03d}.png",
                    content_type="image/png",
                )
                slide_image_urls.append(image_url)
        except Exception as exc:
            logger_warning("[ppt_service] ppt rasterize skipped: %s", exc)

        video_mode: Optional[str] = None
        video_slides: Optional[List[Dict[str, Any]]] = None
        video_slide_count: Optional[int] = None
        if slide_image_urls:
            video_mode = "ppt_image_slideshow"
            video_slides = build_image_video_slides(slide_image_urls, slides_data)
            video_slide_count = len(slide_image_urls)
        else:
            spec_slides = render_spec.get("slides") if isinstance(render_spec, dict) else None
            if isinstance(spec_slides, list) and spec_slides:
                video_mode = (
                    str(render_spec.get("mode") or "minimax_presentation")
                    if isinstance(render_spec, dict)
                    else "minimax_presentation"
                )
                video_slides = spec_slides
                video_slide_count = len(spec_slides)

        return PPTExportMediaResult(
            png_bytes_list=png_bytes_list,
            slide_image_urls=slide_image_urls,
            video_mode=video_mode,
            video_slides=video_slides,
            video_slide_count=video_slide_count,
        )

