"""Thin quality evaluation service for PPT export flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, TYPE_CHECKING

import src.ppt_quality_gate as quality_gate

if TYPE_CHECKING:
    from src.ppt_quality_gate import QualityIssue, QualityResult, QualityScoreResult


@dataclass(frozen=True)
class PPTQualityEvaluation:
    content_gate: "QualityResult"
    layout_gate: "QualityResult"
    content_issues: List["QualityIssue"]
    layout_issues: List["QualityIssue"]
    gate_issues: List["QualityIssue"]
    score_result: "QualityScoreResult"
    effective_threshold: float
    score_passed: bool


class PPTQualityService:
    """Facade around deck/layout validation + score computation."""

    def evaluate_structural_quality(
        self,
        *,
        slides: List[dict[str, Any]],
        render_spec: dict[str, Any],
        profile: str,
        quality_threshold_offset: float,
        relaxed_codes: Iterable[str] | None = None,
    ) -> PPTQualityEvaluation:
        content_gate = quality_gate.validate_deck(slides, profile=profile)
        layout_gate = quality_gate.validate_layout_diversity(render_spec, profile=profile)
        content_issues = list(content_gate.issues)
        layout_issues = list(layout_gate.issues)
        relaxed = {
            str(code or "").strip()
            for code in (relaxed_codes or [])
            if str(code or "").strip()
        }
        if relaxed:
            content_issues = [
                issue
                for issue in content_issues
                if str(getattr(issue, "code", "")).strip() not in relaxed
            ]
            layout_issues = [
                issue
                for issue in layout_issues
                if str(getattr(issue, "code", "")).strip() not in relaxed
            ]
        gate_issues = [*content_issues, *layout_issues]
        score_result = quality_gate.score_deck_quality(
            slides=slides,
            render_spec=render_spec,
            profile=profile,
            content_issues=content_issues,
            layout_issues=layout_issues,
        )
        effective_threshold = max(
            1.0,
            min(
                100.0,
                float(score_result.threshold) + float(quality_threshold_offset),
            ),
        )
        score_passed = bool(score_result.passed) and float(
            score_result.score
        ) >= float(effective_threshold)
        return PPTQualityEvaluation(
            content_gate=content_gate,
            layout_gate=layout_gate,
            content_issues=content_issues,
            layout_issues=layout_issues,
            gate_issues=gate_issues,
            score_result=score_result,
            effective_threshold=effective_threshold,
            score_passed=score_passed,
        )
