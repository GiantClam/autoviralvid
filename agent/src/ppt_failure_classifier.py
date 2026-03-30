"""Failure classification for PPT export and scoped retries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


RETRYABLE_CODES = {
    "timeout",
    "rate_limit",
    "upstream_5xx",
    "schema_invalid",
    "encoding_invalid",
    "layout_homogeneous",
    "quality_score_low",
}


@dataclass(frozen=True)
class FailureClassification:
    code: str
    retryable: bool
    max_attempts: int
    base_delay_ms: int
    message_for_retry_prompt: str


_CLASSIFICATIONS = {
    "timeout": FailureClassification(
        code="timeout",
        retryable=True,
        max_attempts=3,
        base_delay_ms=1200,
        message_for_retry_prompt="Export timed out. Keep structure unchanged and regenerate only failed scope.",
    ),
    "rate_limit": FailureClassification(
        code="rate_limit",
        retryable=True,
        max_attempts=4,
        base_delay_ms=1800,
        message_for_retry_prompt="Rate limited upstream. Retry with identical template and content.",
    ),
    "upstream_5xx": FailureClassification(
        code="upstream_5xx",
        retryable=True,
        max_attempts=3,
        base_delay_ms=1500,
        message_for_retry_prompt="Upstream transient server error. Retry only failed scope.",
    ),
    "schema_invalid": FailureClassification(
        code="schema_invalid",
        retryable=True,
        max_attempts=2,
        base_delay_ms=800,
        message_for_retry_prompt="Schema mismatch detected. Keep original style and repair only invalid fields.",
    ),
    "encoding_invalid": FailureClassification(
        code="encoding_invalid",
        retryable=True,
        max_attempts=2,
        base_delay_ms=900,
        message_for_retry_prompt="Encoding issue detected. Preserve content semantics and retry failed scope.",
    ),
    "layout_homogeneous": FailureClassification(
        code="layout_homogeneous",
        retryable=True,
        max_attempts=2,
        base_delay_ms=700,
        message_for_retry_prompt="Layout diversity is too low. Regenerate deck with varied slide types and avoid adjacent duplicates.",
    ),
    "quality_score_low": FailureClassification(
        code="quality_score_low",
        retryable=True,
        max_attempts=2,
        base_delay_ms=700,
        message_for_retry_prompt="Weighted quality score is too low. Improve visual consistency and structural clarity in failed scope.",
    ),
    "auth_invalid": FailureClassification(
        code="auth_invalid",
        retryable=False,
        max_attempts=1,
        base_delay_ms=0,
        message_for_retry_prompt="Authentication/authorization is invalid. Manual action required.",
    ),
    "unknown": FailureClassification(
        code="unknown",
        retryable=False,
        max_attempts=1,
        base_delay_ms=0,
        message_for_retry_prompt="Unknown terminal error. Retry disabled by policy.",
    ),
}


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(p in lowered for p in patterns)


def classify_failure(error: object) -> FailureClassification:
    message = str(error or "").strip()
    lowered = message.lower()

    if _contains_any(
        lowered,
        (
            "timeoutexpired",
            "timed out",
            "timeout",
            "deadline exceeded",
        ),
    ):
        return _CLASSIFICATIONS["timeout"]

    if _contains_any(
        lowered,
        (
            "429",
            "rate limit",
            "too many requests",
            "retry-after",
        ),
    ):
        return _CLASSIFICATIONS["rate_limit"]

    if _contains_any(
        lowered,
        (
            " 500",
            " 502",
            " 503",
            " 504",
            "http 5",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "upstream",
        ),
    ):
        return _CLASSIFICATIONS["upstream_5xx"]

    if _contains_any(
        lowered,
        (
            "validationerror",
            "schema",
            "jsondecodeerror",
            "invalid slide",
            "slides[",
            "must contain",
            "pydantic",
        ),
    ):
        return _CLASSIFICATIONS["schema_invalid"]

    if _contains_any(
        lowered,
        (
            "unicode",
            "utf-8",
            "utf8",
            "encoding",
            "garbled",
            "mojibake",
            "replacement character",
        ),
    ):
        return _CLASSIFICATIONS["encoding_invalid"]

    if _contains_any(
        lowered,
        (
            "layout_homogeneous",
            "layout_adjacent_repeat",
            "template_family_homogeneous",
            "template_family_switch_frequent",
            "layout diversity",
            "homogeneous",
            "adjacent layout repetition",
        ),
    ):
        return _CLASSIFICATIONS["layout_homogeneous"]

    if _contains_any(
        lowered,
        (
            "quality_score_low",
            "weighted_score",
            "weighted quality score",
        ),
    ):
        return _CLASSIFICATIONS["quality_score_low"]

    if _contains_any(
        lowered,
        (
            "401",
            "403",
            "unauthorized",
            "forbidden",
            "auth",
            "api key",
            "permission denied",
        ),
    ):
        return _CLASSIFICATIONS["auth_invalid"]

    return _CLASSIFICATIONS["unknown"]
