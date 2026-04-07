"""Thin quality evaluation service for PPT export flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, TYPE_CHECKING

from src.ppt_quality_checkers import QualityGateOrchestrator

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

    def __init__(
        self,
        *,
        orchestrator: QualityGateOrchestrator | None = None,
    ) -> None:
        self._orchestrator = orchestrator or QualityGateOrchestrator()

    def evaluate_structural_quality(
        self,
        *,
        slides: List[dict[str, Any]],
        render_spec: dict[str, Any],
        profile: str,
        quality_threshold_offset: float,
        relaxed_codes: Iterable[str] | None = None,
    ) -> PPTQualityEvaluation:
        result = self._orchestrator.evaluate(
            slides=slides,
            render_spec=render_spec,
            profile=profile,
            relaxed_codes=relaxed_codes,
        )
        score_result = result.score_result
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
            content_gate=result.content_gate,
            layout_gate=result.layout_gate,
            content_issues=result.content_issues,
            layout_issues=result.layout_issues,
            gate_issues=result.gate_issues,
            score_result=score_result,
            effective_threshold=effective_threshold,
            score_passed=score_passed,
        )

