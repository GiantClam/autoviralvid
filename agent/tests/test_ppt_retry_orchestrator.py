from src.ppt_retry_orchestrator import (
    build_retry_hint,
    compute_render_path_downgrade,
    make_retry_decision,
    should_retry,
)


def test_non_retryable_fails_fast():
    assert should_retry(code="auth_invalid", attempt=1, max_attempts=3) is False


def test_retry_decision_for_timeout():
    decision = make_retry_decision(
        code="timeout",
        attempt=1,
        max_attempts=3,
        base_delay_ms=1000,
    )
    assert decision.should_retry is True
    assert decision.delay_ms >= 1000


def test_build_retry_hint_contains_scope():
    hint = build_retry_hint(
        failure_code="timeout",
        failure_detail="timed out",
        attempt=2,
        retry_scope="slide",
        target_ids=["s2"],
    )
    assert "scope=slide" in hint
    assert "s2" in hint


def test_compute_render_path_downgrade_promotes_to_svg():
    next_path = compute_render_path_downgrade(
        current_render_path="pptxgenjs",
        failure_code="schema_invalid",
    )
    assert next_path == "svg"


def test_compute_render_path_downgrade_promotes_to_png_fallback():
    next_path = compute_render_path_downgrade(
        current_render_path="svg",
        failure_code="schema_invalid",
    )
    assert next_path == "png_fallback"


def test_compute_render_path_downgrade_ignores_non_render_failures():
    next_path = compute_render_path_downgrade(
        current_render_path="pptxgenjs",
        failure_code="layout_homogeneous",
    )
    assert next_path is None
