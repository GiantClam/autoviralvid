"""Retry policy orchestration for PPT export."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, Collection


TRANSIENT_CODES = {
    "timeout",
    "rate_limit",
    "upstream_5xx",
    "schema_invalid",
    "encoding_invalid",
    "layout_homogeneous",
}

@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    delay_ms: int
    reason: str


@dataclass(frozen=True)
class RetryPolicyConfig:
    max_backoff_ms: int = 20000
    enable_jitter: bool = True


class RetryPolicy:
    """Unified retry policy used by PPT export orchestration."""

    def __init__(
        self,
        *,
        transient_codes: Collection[str] | None = None,
        config: RetryPolicyConfig | None = None,
    ) -> None:
        self._transient_codes = {
            str(code or "").strip().lower()
            for code in (transient_codes or TRANSIENT_CODES)
            if str(code or "").strip()
        }
        self._config = config or RetryPolicyConfig()

    def should_retry(
        self,
        *,
        code: str,
        attempt: int,
        max_attempts: int | None = None,
    ) -> bool:
        normalized = str(code or "").strip().lower()
        if normalized not in self._transient_codes:
            return False
        if attempt < 1:
            return True
        if max_attempts is None:
            return True
        return attempt < max_attempts

    def compute_backoff_ms(
        self,
        *,
        base_delay_ms: int,
        attempt: int,
    ) -> int:
        attempt_idx = max(0, int(attempt) - 1)
        exponential = int(base_delay_ms) * (2**attempt_idx)
        capped = min(int(self._config.max_backoff_ms), int(exponential))
        if self._config.enable_jitter:
            jitter = int(random.uniform(0, max(1, int(base_delay_ms))))
        else:
            jitter = 0
        return max(0, int(capped + jitter))

    def decide(
        self,
        *,
        code: str,
        attempt: int,
        max_attempts: int,
        base_delay_ms: int,
    ) -> RetryDecision:
        enabled = self.should_retry(
            code=code,
            attempt=attempt,
            max_attempts=max_attempts,
        )
        if not enabled:
            return RetryDecision(
                should_retry=False,
                delay_ms=0,
                reason=f"terminal_or_max_attempts_reached(code={code}, attempt={attempt})",
            )
        return RetryDecision(
            should_retry=True,
            delay_ms=self.compute_backoff_ms(
                base_delay_ms=base_delay_ms,
                attempt=attempt,
            ),
            reason=f"transient_failure(code={code}, attempt={attempt})",
        )

    @staticmethod
    def build_hint(
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


_DEFAULT_RETRY_POLICY = RetryPolicy()


def should_retry(code: str, attempt: int, max_attempts: int | None = None) -> bool:
    return _DEFAULT_RETRY_POLICY.should_retry(
        code=code,
        attempt=attempt,
        max_attempts=max_attempts,
    )


def compute_backoff_ms(
    *,
    base_delay_ms: int,
    attempt: int,
    max_backoff_ms: int = 20000,
) -> int:
    policy = RetryPolicy(
        config=RetryPolicyConfig(
            max_backoff_ms=max_backoff_ms,
            enable_jitter=True,
        )
    )
    return policy.compute_backoff_ms(base_delay_ms=base_delay_ms, attempt=attempt)


def make_retry_decision(
    *,
    code: str,
    attempt: int,
    max_attempts: int,
    base_delay_ms: int,
) -> RetryDecision:
    return _DEFAULT_RETRY_POLICY.decide(
        code=code,
        attempt=attempt,
        max_attempts=max_attempts,
        base_delay_ms=base_delay_ms,
    )


def build_retry_hint(
    *,
    failure_code: str,
    failure_detail: str,
    attempt: int,
    retry_scope: str,
    target_ids: Iterable[str] | None = None,
) -> str:
    return RetryPolicy.build_hint(
        failure_code=failure_code,
        failure_detail=failure_detail,
        attempt=attempt,
        retry_scope=retry_scope,
        target_ids=target_ids,
    )


def compute_render_path_downgrade(
    current_render_path: str | None,
    *,
    failure_code: str | None = None,
    attempt: int | None = None,
) -> str:
    """
    Backward-compatible normalization hook.

    DrawingML-first export keeps a single render path. Legacy callers may still
    import this function; it now always normalizes to `svg`.
    """
    _ = failure_code
    _ = attempt
    _ = current_render_path
    return "svg"
