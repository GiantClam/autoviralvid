from __future__ import annotations

from src.ppt_quality_checkers import QualityGateOrchestrator
from src.ppt_quality_gate import QualityIssue, QualityResult, QualityScoreResult


def test_quality_gate_orchestrator_filters_relaxed_issue_codes(monkeypatch):
    import src.ppt_quality_gate as quality_gate

    def _fake_validate_deck(*_args, **_kwargs):
        return QualityResult(
            ok=False,
            issues=[
                QualityIssue(
                    slide_id="s1",
                    code="placeholder_text",
                    message="placeholder",
                    retry_scope="deck",
                ),
                QualityIssue(
                    slide_id="s2",
                    code="template_family_homogeneous",
                    message="homogeneous",
                    retry_scope="deck",
                ),
            ],
        )

    def _fake_validate_layout(*_args, **_kwargs):
        return QualityResult(
            ok=False,
            issues=[
                QualityIssue(
                    slide_id="s2",
                    code="layout_adjacent_duplicate",
                    message="duplicate",
                    retry_scope="deck",
                )
            ],
        )

    def _fake_score(*_args, **_kwargs):
        return QualityScoreResult(
            score=80.0,
            passed=True,
            threshold=75.0,
            warn_threshold=82.0,
            dimensions={},
            issue_counts={},
            diagnostics={},
        )

    monkeypatch.setattr(quality_gate, "validate_deck", _fake_validate_deck)
    monkeypatch.setattr(quality_gate, "validate_layout_diversity", _fake_validate_layout)
    monkeypatch.setattr(quality_gate, "score_deck_quality", _fake_score)

    result = QualityGateOrchestrator().evaluate(
        slides=[{"slide_id": "s1"}],
        render_spec={"slides": [{"slide_id": "s1"}]},
        profile="default",
        relaxed_codes=["template_family_homogeneous"],
    )

    codes = [issue.code for issue in result.gate_issues]
    assert "template_family_homogeneous" not in codes
    assert "placeholder_text" in codes
    assert "layout_adjacent_duplicate" in codes
    assert result.score_result.score == 80.0

