"""Failure persistence helpers for PPT export retry flow."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List


class PPTExportFailureService:
    """Build and persist retry/observability failure payloads consistently."""

    def __init__(
        self,
        *,
        persist_retry_diagnostic: Callable[[Dict[str, Any]], None],
        persist_observability_report: Callable[[Dict[str, Any]], None],
        utc_now: Callable[[], str],
    ) -> None:
        self._persist_retry_diagnostic = persist_retry_diagnostic
        self._persist_observability_report = persist_observability_report
        self._utc_now = utc_now

    @staticmethod
    def _clean_ids(raw_ids: Iterable[Any] | None) -> List[str]:
        return [str(item).strip() for item in (raw_ids or []) if str(item).strip()]

    def build_retry_target_ids(
        self,
        *,
        retry_scope: str,
        target_slide_ids: Iterable[Any] | None,
        target_block_ids: Iterable[Any] | None,
    ) -> List[str]:
        scope = str(retry_scope or "").strip().lower()
        if scope == "block":
            return self._clean_ids(target_block_ids)
        return self._clean_ids(target_slide_ids)

    def persist_retry_event(
        self,
        *,
        deck_id: str,
        failure_code: str | None,
        failure_detail: str | None,
        retry_scope: str,
        target_slide_ids: Iterable[Any] | None,
        target_block_ids: Iterable[Any] | None,
        attempt: int,
        idempotency_key: str | None,
        export_channel: str | None,
        quality_profile: str | None,
        route_mode: str | None,
        render_spec_version: str | None,
        status: str,
        quality_score: float | None = None,
        quality_score_threshold: float | None = None,
        extra_fields: Dict[str, Any] | None = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "deck_id": deck_id,
            "failure_code": failure_code,
            "failure_detail": failure_detail,
            "retry_scope": retry_scope,
            "retry_target_ids": self.build_retry_target_ids(
                retry_scope=retry_scope,
                target_slide_ids=target_slide_ids,
                target_block_ids=target_block_ids,
            ),
            "attempt": attempt,
            "idempotency_key": idempotency_key,
            "export_channel": export_channel,
            "quality_profile": quality_profile,
            "route_mode": route_mode,
            "render_spec_version": render_spec_version,
            "status": status,
            "created_at": self._utc_now(),
        }
        if quality_score is not None:
            payload["quality_score"] = float(quality_score)
        if quality_score_threshold is not None:
            payload["quality_score_threshold"] = quality_score_threshold
        if isinstance(extra_fields, dict) and extra_fields:
            payload.update(extra_fields)
        self._persist_retry_diagnostic(payload)

    def persist_observability_event(
        self,
        *,
        deck_id: str,
        status: str,
        failure_code: str | None,
        failure_detail: str | None,
        route_mode: str | None,
        quality_profile: str | None,
        attempts: int,
        export_channel: str | None,
        generator_mode: str | None,
        diagnostics: List[Dict[str, Any]] | None = None,
        quality_score: float | None = None,
        quality_score_threshold: float | None = None,
        extra_fields: Dict[str, Any] | None = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "deck_id": deck_id,
            "status": status,
            "failure_code": failure_code,
            "failure_detail": failure_detail,
            "route_mode": route_mode,
            "quality_profile": quality_profile,
            "attempts": attempts,
            "export_channel": export_channel,
            "generator_mode": generator_mode,
            "diagnostics": diagnostics[-20:] if isinstance(diagnostics, list) else [],
            "created_at": self._utc_now(),
        }
        if quality_score is not None:
            payload["quality_score"] = float(quality_score)
        if quality_score_threshold is not None:
            payload["quality_score_threshold"] = quality_score_threshold
        if isinstance(extra_fields, dict) and extra_fields:
            payload.update(extra_fields)
        self._persist_observability_report(payload)

    def persist_failed_observability(
        self,
        *,
        deck_id: str,
        failure_code: str,
        failure_detail: str,
        route_mode: str | None,
        quality_profile: str | None,
        attempts: int,
        export_channel: str | None,
        generator_mode: str | None,
        diagnostics: List[Dict[str, Any]],
        quality_score: float | None = None,
        quality_score_threshold: float | None = None,
        extra_fields: Dict[str, Any] | None = None,
    ) -> None:
        self.persist_observability_event(
            deck_id=deck_id,
            status="failed",
            failure_code=failure_code,
            failure_detail=failure_detail,
            route_mode=route_mode,
            quality_profile=quality_profile,
            attempts=attempts,
            export_channel=export_channel,
            generator_mode=generator_mode,
            diagnostics=diagnostics,
            quality_score=quality_score,
            quality_score_threshold=quality_score_threshold,
            extra_fields=extra_fields,
        )
