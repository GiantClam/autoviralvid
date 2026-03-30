from src.ppt_failure_classifier import classify_failure


def test_timeout_is_retryable():
    c = classify_failure("subprocess.TimeoutExpired: timed out after 180 seconds")
    assert c.code == "timeout"
    assert c.retryable is True


def test_auth_invalid_is_terminal():
    c = classify_failure("HTTP 401 unauthorized: invalid api key")
    assert c.code == "auth_invalid"
    assert c.retryable is False


def test_quality_score_low_is_retryable():
    c = classify_failure("quality_score_low: weighted_score=66.0 < threshold=72.0")
    assert c.code == "quality_score_low"
    assert c.retryable is True
