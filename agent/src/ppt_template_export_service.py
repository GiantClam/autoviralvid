"""Template-edit export flow for PPT pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List

import src.pptx_engine as pptx_engine


@dataclass(frozen=True)
class PPTTemplateExportFlowResult:
    url: str
    template_result: Dict[str, Any]
    template_skill_runtime: Dict[str, Any]
    template_markitdown_summary: Dict[str, Any]
    text_qa: Dict[str, Any]
    diagnostics: List[Dict[str, Any]]


class PPTTemplateExportService:
    """Executes template-edit branch and returns normalized export artifacts."""

    async def run_template_edit_flow(
        self,
        *,
        template_file_url: str,
        title: str,
        author: str,
        raw_slides_data: List[Dict[str, Any]],
        effective_template_family: str,
        effective_style_variant: str,
        effective_palette_key: str,
        enforce_skill_runtime: bool,
        download_remote_file_bytes: Callable[..., Awaitable[bytes]],
        upload_bytes_to_r2: Callable[..., Awaitable[str]],
        new_id: Callable[[], str],
        run_markitdown_text_qa: Callable[..., Dict[str, Any]],
        audit_textual_slides: Callable[..., Dict[str, Any]],
        assert_skill_runtime_success: Callable[..., None],
    ) -> PPTTemplateExportFlowResult:
        template_bytes = await download_remote_file_bytes(template_file_url, suffix=".pptx")
        template_skill_runtime: Dict[str, Any] = {}
        try:
            from src.installed_skill_executor import execute_installed_skill_request

            template_skill_runtime = execute_installed_skill_request(
                {
                    "version": 1,
                    "requested_skills": [
                        "ppt-editing-skill",
                        "ppt-orchestra-skill",
                        "design-style-skill",
                        "color-font-skill",
                    ],
                    "slide": (
                        dict(raw_slides_data[0])
                        if raw_slides_data and isinstance(raw_slides_data[0], dict)
                        else {"slide_type": "cover", "title": title}
                    ),
                    "deck": {
                        "title": title,
                        "topic": title,
                        "total_slides": len(raw_slides_data),
                        "template_family": effective_template_family,
                        "style_variant": effective_style_variant,
                        "palette_key": effective_palette_key,
                    },
                }
            )
            if enforce_skill_runtime:
                assert_skill_runtime_success(
                    stage="template_edit",
                    skill_output=template_skill_runtime
                    if isinstance(template_skill_runtime, dict)
                    else {},
                    requested_skills=[
                        "ppt-editing-skill",
                        "ppt-orchestra-skill",
                        "design-style-skill",
                        "color-font-skill",
                    ],
                )
        except Exception as exc:
            if enforce_skill_runtime:
                raise RuntimeError(
                    f"template_skill_runtime_failed:{str(exc)[:180]}"
                ) from exc
            template_skill_runtime = {
                "error": f"template_skill_runtime_failed:{str(exc)[:180]}",
            }

        template_markitdown_summary: Dict[str, Any] = {}
        try:
            template_markitdown_summary = await asyncio.to_thread(
                run_markitdown_text_qa,
                template_bytes,
                timeout_sec=20,
            )
        except Exception as exc:
            template_markitdown_summary = {
                "enabled": True,
                "ok": False,
                "error": f"markitdown_template_probe_failed: {str(exc)[:180]}",
                "issue_codes": ["markitdown_extraction_failed"],
            }

        template_result = pptx_engine.fill_template_pptx(
            template_bytes=template_bytes,
            slides=[dict(item) for item in raw_slides_data],
            deck_title=title,
            author=author,
        )

        project_id = new_id()
        key = f"projects/{project_id}/pptx/presentation.pptx"
        url = await upload_bytes_to_r2(
            template_result["pptx_bytes"],
            key,
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        diagnostics: List[Dict[str, Any]] = [
            {
                "attempt": 1,
                "status": "template_edit_applied",
                "template_file_url": template_file_url,
                "replacement_count": int(template_result.get("replacement_count") or 0),
                "template_slide_count": int(
                    template_result.get("template_slide_count") or 0
                ),
                "slides_used": int(template_result.get("slides_used") or 0),
                "template_edit_engine": str(template_result.get("engine") or "unknown"),
                "template_markitdown_used": bool(
                    template_result.get("markitdown_used")
                ),
            }
        ]
        if template_skill_runtime:
            diagnostics.append(
                {
                    "attempt": 1,
                    "status": "template_skill_runtime",
                    "runtime": template_skill_runtime,
                }
            )
        if template_markitdown_summary:
            diagnostics.append(
                {
                    "attempt": 1,
                    "status": "template_markitdown_probe",
                    "markitdown": template_markitdown_summary,
                }
            )

        text_render_spec = {
            "slides": [
                {
                    "slide_id": str(
                        slide.get("slide_id")
                        or slide.get("id")
                        or f"slide-{idx + 1}"
                    ),
                    "page_number": idx + 1,
                }
                for idx, slide in enumerate(raw_slides_data)
                if isinstance(slide, dict)
            ]
        }
        text_qa: Dict[str, Any] = {}
        try:
            text_qa = audit_textual_slides(
                [dict(item) for item in raw_slides_data],
                render_spec=text_render_spec,
            )
        except Exception as exc:
            text_qa = {"error": str(exc)[:220]}

        return PPTTemplateExportFlowResult(
            url=url,
            template_result=dict(template_result or {}),
            template_skill_runtime=template_skill_runtime,
            template_markitdown_summary=template_markitdown_summary,
            text_qa=text_qa,
            diagnostics=diagnostics,
        )
