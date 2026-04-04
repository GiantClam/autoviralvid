"""Stage timeline helpers for PPT export orchestration."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExportStage:
    stage: str
    started_at: str
    ended_at: str
    duration_ms: int
    ok: bool
    meta: Dict[str, Any] = field(default_factory=dict)


class ExportPipelineTimeline:
    """Capture lightweight stage-level timing for export mainflow."""

    def __init__(self) -> None:
        self._stages: List[ExportStage] = []

    @contextmanager
    def stage(self, name: str, meta: Dict[str, Any] | None = None) -> Iterator[Dict[str, Any]]:
        stage_name = str(name or "").strip() or "unknown"
        started_at = _utc_now()
        t0 = time.perf_counter()
        local_meta: Dict[str, Any] = dict(meta or {})
        ok = True
        try:
            yield local_meta
        except Exception:
            ok = False
            raise
        finally:
            t1 = time.perf_counter()
            self._stages.append(
                ExportStage(
                    stage=stage_name,
                    started_at=started_at,
                    ended_at=_utc_now(),
                    duration_ms=max(0, int((t1 - t0) * 1000)),
                    ok=ok,
                    meta=local_meta,
                )
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": "v1",
            "stages": [
                {
                    "stage": row.stage,
                    "started_at": row.started_at,
                    "ended_at": row.ended_at,
                    "duration_ms": row.duration_ms,
                    "ok": row.ok,
                    "meta": row.meta,
                }
                for row in self._stages
            ],
        }

    def record(self, *, stage: str, ok: bool, meta: Dict[str, Any] | None = None) -> None:
        now = _utc_now()
        self._stages.append(
            ExportStage(
                stage=str(stage or "").strip() or "unknown",
                started_at=now,
                ended_at=now,
                duration_ms=0,
                ok=bool(ok),
                meta=dict(meta or {}),
            )
        )
