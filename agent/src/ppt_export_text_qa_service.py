"""Text QA composition service for export flow."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Dict, List


class PPTExportTextQAService:
    """Runs textual QA and optional markitdown probe for exported PPTX."""

    async def run(
        self,
        *,
        export_result: Dict[str, Any],
        slides_data: List[Dict[str, Any]],
        render_spec: Dict[str, Any],
        audit_textual_slides: Callable[..., Dict[str, Any]],
        run_markitdown_text_qa: Callable[..., Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            final_text_qa = audit_textual_slides(
                (export_result.get("input_payload") or {}).get("slides") or slides_data,
                render_spec=render_spec,
            )
        except Exception as exc:
            final_text_qa = {"error": str(exc)[:220]}

        markitdown_enabled = str(
            os.getenv("PPT_TEXT_QA_MARKITDOWN_ENABLED", "true")
        ).strip().lower() not in {"0", "false", "no", "off"}
        if not markitdown_enabled:
            return final_text_qa if isinstance(final_text_qa, dict) else {}

        markitdown_timeout_sec_raw = str(
            os.getenv("PPT_TEXT_QA_MARKITDOWN_TIMEOUT_SEC", "25")
        ).strip()
        try:
            markitdown_timeout_sec = max(5, min(90, int(markitdown_timeout_sec_raw)))
        except Exception:
            markitdown_timeout_sec = 25

        try:
            markitdown_summary = await asyncio.to_thread(
                run_markitdown_text_qa,
                export_result["pptx_bytes"],
                timeout_sec=markitdown_timeout_sec,
            )
        except Exception as exc:
            markitdown_summary = {
                "enabled": True,
                "ok": False,
                "error": str(exc)[:220],
                "issue_codes": ["markitdown_extraction_failed"],
            }

        if not isinstance(final_text_qa, dict):
            final_text_qa = {}
        final_text_qa["markitdown"] = markitdown_summary

        text_issue_codes = (
            final_text_qa.get("issue_codes")
            if isinstance(final_text_qa.get("issue_codes"), list)
            else []
        )
        md_issue_codes = (
            markitdown_summary.get("issue_codes")
            if isinstance(markitdown_summary.get("issue_codes"), list)
            else []
        )
        if md_issue_codes:
            final_text_qa["issue_codes"] = sorted(
                {
                    str(item).strip()
                    for item in [*text_issue_codes, *md_issue_codes]
                    if str(item).strip()
                }
            )

        return final_text_qa

