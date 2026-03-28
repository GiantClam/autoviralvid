from src.ppt_retry_orchestrator import build_retry_hint, make_retry_decision, should_retry


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

