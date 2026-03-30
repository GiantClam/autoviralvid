#!/usr/bin/env python
"""Build an operational report from PPT observability records.

Usage:
  python scripts/tests/ppt-observability-report.py --hours 24 --output test_reports/ppt/observability.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _load_local_records(input_path: str, glob_pattern: str) -> List[Dict[str, Any]]:
    base = Path(input_path).resolve()
    if base.is_file():
        try:
            raw = json.loads(base.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [item for item in raw if isinstance(item, dict)]
            if isinstance(raw, dict):
                if isinstance(raw.get("records"), list):
                    return [item for item in raw["records"] if isinstance(item, dict)]
                if isinstance(raw.get("results"), list):
                    return [item for item in raw["results"] if isinstance(item, dict)]
                return [raw]
        except Exception:
            return []
    if not base.exists():
        return []
    records: List[Dict[str, Any]] = []
    for file in base.rglob(glob_pattern):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, list):
            records.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            if isinstance(data.get("records"), list):
                records.extend(item for item in data["records"] if isinstance(item, dict))
            else:
                records.append(data)
    return records


def _load_supabase_records(hours: int, limit: int) -> List[Dict[str, Any]]:
    supabase_url = str(os.getenv("SUPABASE_URL") or "").strip()
    service_key = str(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or "").strip()
    if not supabase_url or not service_key:
        return []
    try:
        from supabase import create_client

        sb = create_client(supabase_url, service_key)
        since = (_utc_now() - timedelta(hours=max(1, int(hours)))).isoformat()
        response = (
            sb.table("autoviralvid_ppt_observability_reports")
            .select("*")
            .gte("created_at", since)
            .order("created_at", desc=True)
            .limit(max(1, int(limit)))
            .execute()
        )
        data = getattr(response, "data", None)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    except Exception:
        return []


def _build_report(records: List[Dict[str, Any]], *, max_failure_rate: float) -> Dict[str, Any]:
    def _status_of(item: Dict[str, Any]) -> str:
        raw = str(item.get("status") or "").strip().lower()
        if raw:
            return raw
        if bool(item.get("ok")) or bool(item.get("passed")):
            return "success"
        if str(item.get("failure_code") or "").strip():
            return "failed"
        return "unknown"

    total = len(records)
    status_counter = Counter(_status_of(item) for item in records)
    route_counter = Counter(str(item.get("route_mode") or "unknown") for item in records)
    failure_counter = Counter(
        str(item.get("failure_code") or "none")
        for item in records
        if _status_of(item) != "success"
    )
    alert_counter = Counter()
    for item in records:
        alerts = _safe_list(item.get("alerts"))
        for alert in alerts:
            if isinstance(alert, dict):
                severity = str(alert.get("severity") or "unknown").lower()
                code = str(alert.get("code") or "unknown")
                alert_counter[f"{severity}:{code}"] += 1

    success_count = status_counter.get("success", 0)
    failed_count = total - success_count
    failure_rate = (failed_count / total) if total else 0.0
    report = {
        "ok": failure_rate <= max(0.0, float(max_failure_rate)),
        "summary": {
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "failure_rate": failure_rate,
        },
        "status_distribution": dict(status_counter),
        "route_distribution": dict(route_counter),
        "top_failure_codes": failure_counter.most_common(10),
        "top_alerts": alert_counter.most_common(20),
        "samples": records[:20],
    }
    if failure_rate > max(0.0, float(max_failure_rate)):
        report["gate"] = {
            "type": "failure_rate",
            "message": f"failure_rate={failure_rate:.4f} exceeds max_failure_rate={float(max_failure_rate):.4f}",
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--input", default="")
    parser.add_argument("--glob", default="*.json")
    parser.add_argument("--max-failure-rate", type=float, default=0.2)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    records = _load_supabase_records(args.hours, args.limit)
    source = "supabase"
    if not records:
        input_path = str(args.input or "test_reports/ppt").strip()
        records = _load_local_records(input_path, str(args.glob or "*.json"))
        source = f"local:{Path(input_path).resolve()}"

    report = _build_report(records, max_failure_rate=float(args.max_failure_rate))
    report["source"] = source
    report["generated_at"] = _utc_now().isoformat()

    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
