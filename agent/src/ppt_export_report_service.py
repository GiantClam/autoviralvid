"""Report composition service for PPT export observability output."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


class PPTExportReportService:
    """Builds normalized observability report payloads."""

    @staticmethod
    def _clean_codes(codes: Iterable[Any] | None) -> List[str]:
        return sorted({str(item).strip() for item in (codes or []) if str(item).strip()})

    def build_observability_report(
        self,
        *,
        route_mode: str,
        quality_profile: str,
        strict_quality_mode: bool,
        attempts: int,
        retry_count: int,
        layout_homogeneous_count: int,
        slide_count_for_incidence: int,
        generator_mode: str,
        export_channel: str,
        has_visual_qa: bool,
        has_text_qa: bool,
        has_quality_score: bool,
        visual_professional_score: Dict[str, Any] | None,
        issue_codes: List[str],
        quality_score: Dict[str, Any] | None,
        template_renderer_summary: Dict[str, Any] | None,
        text_qa: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "route_mode": route_mode,
            "quality_profile": quality_profile,
            "strict_quality_mode": bool(strict_quality_mode),
            "attempts": int(attempts),
            "retry_count": max(0, int(retry_count)),
            "render_success_rate": 1.0,
            "layout_homogeneous_incidence": float(layout_homogeneous_count)
            / float(max(1, int(slide_count_for_incidence))),
            "generator_mode": generator_mode,
            "export_channel": export_channel,
            "has_visual_qa": bool(has_visual_qa),
            "has_text_qa": bool(has_text_qa),
            "has_quality_score": bool(has_quality_score),
            "has_visual_professional_score": isinstance(visual_professional_score, dict),
            "issue_codes": self._clean_codes(issue_codes),
        }
        if isinstance(quality_score, dict):
            report["weighted_quality_score"] = float(quality_score.get("score") or 0.0)
            report["weighted_quality_threshold"] = float(
                quality_score.get("threshold") or 0.0
            )
        if isinstance(template_renderer_summary, dict) and template_renderer_summary:
            report["template_renderer_summary"] = dict(template_renderer_summary)
        if isinstance(visual_professional_score, dict):
            report["visual_professional_score"] = dict(visual_professional_score)
        if isinstance(text_qa, dict) and text_qa:
            report["text_qa"] = dict(text_qa)
            text_issue_codes = (
                text_qa.get("issue_codes")
                if isinstance(text_qa.get("issue_codes"), list)
                else []
            )
            if text_issue_codes:
                report["issue_codes"] = self._clean_codes(
                    [*report.get("issue_codes", []), *text_issue_codes]
                )
        return report

