"""Layered quality checkers and orchestration for PPT deck validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, TYPE_CHECKING

import src.ppt_quality_gate as quality_gate

if TYPE_CHECKING:
    from src.ppt_quality_gate import QualityIssue, QualityResult, QualityScoreResult


class TechnicalConstraintChecker:
    """Structural/layout-level technical constraint checks."""

    def check(self, *, render_spec: dict[str, Any], profile: str) -> "QualityResult":
        return quality_gate.validate_layout_diversity(render_spec, profile=profile)


class ContentQualityChecker:
    """Content-level checks (placeholder, encoding, semantic integrity)."""

    def check(self, *, slides: List[dict[str, Any]], profile: str) -> "QualityResult":
        return quality_gate.validate_deck(slides, profile=profile)


class VisualConsistencyChecker:
    """Weighted quality score check for visual consistency/readability."""

    def score(
        self,
        *,
        slides: List[dict[str, Any]],
        render_spec: dict[str, Any],
        profile: str,
        content_issues: List["QualityIssue"],
        layout_issues: List["QualityIssue"],
    ) -> "QualityScoreResult":
        return quality_gate.score_deck_quality(
            slides=slides,
            render_spec=render_spec,
            profile=profile,
            content_issues=content_issues,
            layout_issues=layout_issues,
        )


@dataclass(frozen=True)
class QualityGateOrchestrationResult:
    content_gate: "QualityResult"
    layout_gate: "QualityResult"
    content_issues: List["QualityIssue"]
    layout_issues: List["QualityIssue"]
    gate_issues: List["QualityIssue"]
    score_result: "QualityScoreResult"


class QualityGateOrchestrator:
    """Orchestrates technical/content/visual checkers in one place."""

    def __init__(
        self,
        *,
        technical_checker: TechnicalConstraintChecker | None = None,
        content_checker: ContentQualityChecker | None = None,
        visual_checker: VisualConsistencyChecker | None = None,
    ) -> None:
        self._technical_checker = technical_checker or TechnicalConstraintChecker()
        self._content_checker = content_checker or ContentQualityChecker()
        self._visual_checker = visual_checker or VisualConsistencyChecker()

    def evaluate(
        self,
        *,
        slides: List[dict[str, Any]],
        render_spec: dict[str, Any],
        profile: str,
        relaxed_codes: Iterable[str] | None = None,
    ) -> QualityGateOrchestrationResult:
        content_gate = self._content_checker.check(slides=slides, profile=profile)
        layout_gate = self._technical_checker.check(
            render_spec=render_spec, profile=profile
        )
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
        score_result = self._visual_checker.score(
            slides=slides,
            render_spec=render_spec,
            profile=profile,
            content_issues=content_issues,
            layout_issues=layout_issues,
        )
        return QualityGateOrchestrationResult(
            content_gate=content_gate,
            layout_gate=layout_gate,
            content_issues=content_issues,
            layout_issues=layout_issues,
            gate_issues=gate_issues,
            score_result=score_result,
        )

