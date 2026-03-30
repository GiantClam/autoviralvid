"""Retry policy orchestration for PPT export."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable


TRANSIENT_CODES = {
    "timeout",
    "rate_limit",
    "upstream_5xx",
    "schema_invalid",
    "encoding_invalid",
    "layout_homogeneous",
}

RENDER_PATH_DOWNGRADE_CODES = {
    "schema_invalid",
    "encoding_invalid",
    "timeout",
    "upstream_5xx",
    "unknown",
}

_RENDER_PATH_SEQUENCE = ("pptxgenjs", "svg", "png_fallback")


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    delay_ms: int
    reason: str


def should_retry(code: str, attempt: int, max_attempts: int | None = None) -> bool:
    normalized = str(code or "").strip().lower()
    if normalized not in TRANSIENT_CODES:
        return False
    if attempt < 1:
        return True
    if max_attempts is None:
        return True
    return attempt < max_attempts


def compute_backoff_ms(
    *,
    base_delay_ms: int,
    attempt: int,
    max_backoff_ms: int = 20000,
) -> int:
    attempt_idx = max(0, int(attempt) - 1)
    exponential = base_delay_ms * (2**attempt_idx)
    capped = min(max_backoff_ms, exponential)
    jitter = int(random.uniform(0, max(1, base_delay_ms)))
    return max(0, int(capped + jitter))


def make_retry_decision(
    *,
    code: str,
    attempt: int,
    max_attempts: int,
    base_delay_ms: int,
) -> RetryDecision:
    enabled = should_retry(code, attempt, max_attempts=max_attempts)
    if not enabled:
        return RetryDecision(
            should_retry=False,
            delay_ms=0,
            reason=f"terminal_or_max_attempts_reached(code={code}, attempt={attempt})",
        )
    return RetryDecision(
        should_retry=True,
        delay_ms=compute_backoff_ms(
            base_delay_ms=base_delay_ms,
            attempt=attempt,
        ),
        reason=f"transient_failure(code={code}, attempt={attempt})",
    )


def build_retry_hint(
    *,
    failure_code: str,
    failure_detail: str,
    attempt: int,
    retry_scope: str,
    target_ids: Iterable[str] | None = None,
) -> str:
    ids = [str(item).strip() for item in (target_ids or []) if str(item).strip()]
    ids_text = ", ".join(ids[:20]) if ids else "n/a"
    return (
        f"[attempt={attempt}] failure_code={failure_code}; "
        f"scope={retry_scope}; targets={ids_text}; "
        f"detail={str(failure_detail or '').strip()[:500]}"
    )


def _normalize_render_path(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _RENDER_PATH_SEQUENCE:
        return normalized
    return "pptxgenjs"


def compute_render_path_downgrade(
    *,
    current_render_path: str | None,
    failure_code: str,
) -> str | None:
    code = str(failure_code or "").strip().lower()
    if code not in RENDER_PATH_DOWNGRADE_CODES:
        return None
    current = _normalize_render_path(current_render_path)
    try:
        index = _RENDER_PATH_SEQUENCE.index(current)
    except ValueError:
        index = 0
    if index >= len(_RENDER_PATH_SEQUENCE) - 1:
        return None
    return _RENDER_PATH_SEQUENCE[index + 1]
