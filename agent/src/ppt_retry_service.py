"""Thin retry service for PPT export orchestration."""

from __future__ import annotations

import asyncio
from typing import Iterable

from src.ppt_failure_classifier import FailureClassification
from src.ppt_retry_orchestrator import RetryDecision, RetryPolicy


class PPTRetryService:
    """Facade service for retry decision/hint/sleep behavior."""

    def __init__(self, *, policy: RetryPolicy | None = None) -> None:
        self._policy = policy or RetryPolicy()

    def decide(
        self,
        *,
        code: str,
        attempt: int,
        max_attempts: int,
        base_delay_ms: int,
    ) -> RetryDecision:
        return self._policy.decide(
            code=code,
            attempt=attempt,
            max_attempts=max_attempts,
            base_delay_ms=base_delay_ms,
        )

    def decide_from_classification(
        self,
        *,
        classification: FailureClassification,
        attempt: int,
        max_attempts: int,
    ) -> RetryDecision:
        return self.decide(
            code=classification.code,
            attempt=attempt,
            max_attempts=min(int(max_attempts), int(classification.max_attempts)),
            base_delay_ms=int(classification.base_delay_ms),
        )

    def build_hint(
        self,
        *,
        failure_code: str,
        failure_detail: str,
        attempt: int,
        retry_scope: str,
        target_ids: Iterable[str] | None = None,
    ) -> str:
        return self._policy.build_hint(
            failure_code=failure_code,
            failure_detail=failure_detail,
            attempt=attempt,
            retry_scope=retry_scope,
            target_ids=target_ids,
        )

    async def sleep_for_retry(self, decision: RetryDecision) -> None:
        if not decision.should_retry or int(decision.delay_ms) <= 0:
            return
        await asyncio.sleep(float(decision.delay_ms) / 1000.0)

