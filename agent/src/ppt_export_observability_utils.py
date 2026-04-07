"""Utilities for export observability diagnostics and strict gate messages."""

from __future__ import annotations

from typing import Any, Dict, List


def merge_strict_blockers_into_alerts(
    alerts: List[Dict[str, Any]],
    strict_blockers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = [dict(item) for item in (alerts or []) if isinstance(item, dict)]
    existing_codes = {
        str(item.get("code") or "").strip().lower()
        for item in merged
        if str(item.get("code") or "").strip()
    }
    for blocker in strict_blockers or []:
        if not isinstance(blocker, dict):
            continue
        code = str(blocker.get("code") or "").strip().lower()
        if code and code in existing_codes:
            continue
        merged.append(dict(blocker))
        if code:
            existing_codes.add(code)
    return merged


def build_persisted_diagnostics(
    *,
    diagnostics: List[Dict[str, Any]],
    template_renderer_summary: Dict[str, Any] | None,
    text_qa: Dict[str, Any] | None,
    strict_blockers: List[Dict[str, Any]] | None,
) -> List[Dict[str, Any]]:
    persisted: List[Dict[str, Any]] = [dict(item) for item in (diagnostics or []) if isinstance(item, dict)][-20:]
    if isinstance(template_renderer_summary, dict) and template_renderer_summary:
        persisted = [
            *persisted,
            {"status": "template_renderer_summary", "summary": dict(template_renderer_summary)},
        ][-20:]
    if isinstance(text_qa, dict) and text_qa:
        persisted = [
            *persisted,
            {"status": "text_qa_summary", "summary": dict(text_qa)},
        ][-20:]
    if isinstance(strict_blockers, list) and strict_blockers:
        persisted = [
            *persisted,
            {"status": "strict_quality_gate_failed", "blockers": [dict(item) for item in strict_blockers if isinstance(item, dict)]},
        ][-20:]
    return persisted


def build_strict_failure_detail(
    strict_blockers: List[Dict[str, Any]] | None,
    *,
    max_items: int = 6,
    max_len: int = 1200,
) -> str:
    pairs: List[str] = []
    for item in (strict_blockers or [])[: max(1, int(max_items))]:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        message = str(item.get("message") or "").strip()
        pairs.append(f"{code}:{message}")
    return "; ".join(pairs)[: max(1, int(max_len))]

