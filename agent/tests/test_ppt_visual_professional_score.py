from src.ppt_quality_gate import QualityScoreResult, score_deck_quality, score_visual_professional_metrics


def test_visual_professional_score_generates_expected_fields():
    slides = [
        {
            "slide_id": "s1",
            "slide_type": "content",
            "layout_grid": "split_2",
            "title": "Growth",
            "elements": [{"type": "text", "content": "Revenue +20% with stable margin."}],
        },
        {
            "slide_id": "s2",
            "slide_type": "content",
            "layout_grid": "grid_3",
            "title": "Roadmap",
            "elements": [{"type": "text", "content": "Q1 plan, Q2 launch, Q3 optimize."}],
        },
    ]
    quality = score_deck_quality(slides=slides, render_spec={"slides": slides})
    out = score_visual_professional_metrics(slides=slides, quality_score=quality)

    assert 0.0 <= out.color_consistency_score <= 10.0
    assert 0.0 <= out.layout_order_score <= 10.0
    assert 0.0 <= out.hierarchy_clarity_score <= 10.0
    assert 0.0 <= out.visual_avg_score <= 10.0
    assert isinstance(out.accuracy_gate_passed, bool)
    assert isinstance(out.abnormal_tags, list)


def test_visual_professional_score_marks_accuracy_gate_failed_for_hard_codes():
    quality = QualityScoreResult(
        score=78.0,
        passed=True,
        threshold=72.0,
        warn_threshold=80.0,
        dimensions={"visual": 80.0, "layout": 75.0, "consistency": 74.0},
        issue_counts={"encoding_invalid": 1},
        diagnostics={"visual_style_drift_ratio": 0.1, "visual_low_contrast_ratio": 0.0, "visual_issue_pressure": 0.1},
    )

    out = score_visual_professional_metrics(
        quality_score=quality,
        text_issue_codes=["fact_mismatch_detected"],
    )

    assert out.accuracy_gate_passed is False
    assert "accuracy_risk" in out.abnormal_tags
