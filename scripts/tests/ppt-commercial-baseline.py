#!/usr/bin/env python
"""Commercial baseline checker for PPT render artifacts.

Usage:
  python scripts/tests/ppt-commercial-baseline.py --fixtures-dir test_outputs --glob "*.render.json"
  python scripts/tests/ppt-commercial-baseline.py --fixtures-dir test_outputs --iterations 5 --workers 8 --output test_reports/ppt/commercial-baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.ppt_quality_gate import score_deck_quality, validate_deck, validate_layout_diversity


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _slides_from_render(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(payload.get("slides"), list):
        return [item for item in payload["slides"] if isinstance(item, dict)]
    official = payload.get("official_input")
    if isinstance(official, dict) and isinstance(official.get("slides"), list):
        return [item for item in official["slides"] if isinstance(item, dict)]
    return []


def _check_file(path: Path, quality_profile: str) -> Dict[str, Any]:
    started = time.perf_counter()
    payload = _load_json(path)
    slides = _slides_from_render(payload)
    content = validate_deck(slides, profile=quality_profile)
    layout = validate_layout_diversity(payload, profile=quality_profile)
    score = score_deck_quality(
        slides=slides,
        render_spec=payload,
        profile=quality_profile,
        content_issues=content.issues,
        layout_issues=layout.issues,
    )
    return {
        "file": str(path),
        "slides": len(slides),
        "issues": [f"{issue.slide_id}:{issue.code}" for issue in [*content.issues, *layout.issues]],
        "score": score.score,
        "threshold": score.threshold,
        "passed": score.passed and score.score >= score.threshold and content.ok and layout.ok,
        "dimensions": score.dimensions,
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-dir", required=True)
    parser.add_argument("--glob", default="*.render.json")
    parser.add_argument("--quality-profile", default="default")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--required-fixtures", default="")
    parser.add_argument("--max-failure-rate", type=float, default=0.0)
    parser.add_argument("--max-p95-ms", type=float, default=0.0)
    parser.add_argument("--baseline-report", default="")
    parser.add_argument("--max-score-regression", type=float, default=2.0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    fixtures_dir = Path(args.fixtures_dir).resolve()
    files = sorted(fixtures_dir.rglob(args.glob))
    if not files:
        print(json.dumps({"ok": False, "error": "no fixtures found", "fixtures_dir": str(fixtures_dir)}))
        return 2

    required_fixture_tokens = [
        token.strip().lower()
        for token in str(args.required_fixtures or "").split(",")
        if token.strip()
    ]
    if required_fixture_tokens:
        available_paths = [str(path).lower() for path in files]
        missing_tokens = [
            token
            for token in required_fixture_tokens
            if not any(token in item for item in available_paths)
        ]
        if missing_tokens:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "required fixtures missing",
                        "missing_tokens": missing_tokens,
                    },
                    ensure_ascii=False,
                )
            )
            return 2

    iterations = max(1, int(args.iterations))
    tasks = [(path, iteration + 1) for iteration in range(iterations) for path in files]
    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
        raw_results = list(
            pool.map(
                lambda item: {
                    **_check_file(item[0], str(args.quality_profile)),
                    "iteration": item[1],
                },
                tasks,
            )
        )

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in raw_results:
        grouped.setdefault(str(item.get("file")), []).append(item)

    per_fixture: List[Dict[str, Any]] = []
    for file_path, group in grouped.items():
        runs = len(group)
        passed_runs = sum(1 for item in group if bool(item.get("passed")))
        failed_runs = runs - passed_runs
        scores = [float(item.get("score") or 0.0) for item in group]
        elapsed = sorted(float(item.get("elapsed_ms") or 0.0) for item in group)
        p95_index = max(0, min(len(elapsed) - 1, int(round((len(elapsed) - 1) * 0.95)))) if elapsed else 0
        issue_union = sorted({issue for item in group for issue in item.get("issues", [])})
        per_fixture.append(
            {
                "file": file_path,
                "runs": runs,
                "passed_runs": passed_runs,
                "failed_runs": failed_runs,
                "pass_rate": (passed_runs / runs) if runs else 0.0,
                "avg_score": (sum(scores) / len(scores)) if scores else 0.0,
                "min_score": min(scores) if scores else 0.0,
                "max_score": max(scores) if scores else 0.0,
                "p95_elapsed_ms": elapsed[p95_index] if elapsed else 0.0,
                "issues": issue_union[:30],
            }
        )

    results = sorted(per_fixture, key=lambda item: (item["failed_runs"], item["avg_score"]))
    failed = [item for item in results if int(item.get("failed_runs") or 0) > 0]
    total_runs = len(raw_results)
    failed_runs = sum(int(item.get("failed_runs") or 0) for item in results)
    failure_rate = (failed_runs / total_runs) if total_runs else 0.0
    all_scores = [float(item.get("score") or 0.0) for item in raw_results]
    all_elapsed = sorted(float(item.get("elapsed_ms") or 0.0) for item in raw_results)
    p95_all_idx = max(0, min(len(all_elapsed) - 1, int(round((len(all_elapsed) - 1) * 0.95)))) if all_elapsed else 0

    gates: List[str] = []
    if float(args.max_failure_rate) >= 0 and failure_rate > float(args.max_failure_rate):
        gates.append(
            f"failure_rate {failure_rate:.4f} > max_failure_rate {float(args.max_failure_rate):.4f}"
        )
    p95_elapsed_ms = all_elapsed[p95_all_idx] if all_elapsed else 0.0
    if float(args.max_p95_ms) > 0 and p95_elapsed_ms > float(args.max_p95_ms):
        gates.append(
            f"p95_elapsed_ms {p95_elapsed_ms:.2f} > max_p95_ms {float(args.max_p95_ms):.2f}"
        )

    baseline_compare: Dict[str, Any] = {}
    baseline_path = str(args.baseline_report or "").strip()
    if baseline_path:
        baseline_file = Path(baseline_path).resolve()
        if baseline_file.exists():
            baseline_data = _load_json(baseline_file)
            baseline_summary = baseline_data.get("summary") if isinstance(baseline_data, dict) else {}
            prev_mean_score = float((baseline_summary or {}).get("mean_score") or 0.0)
            curr_mean_score = (sum(all_scores) / len(all_scores)) if all_scores else 0.0
            score_delta = curr_mean_score - prev_mean_score
            baseline_compare = {
                "baseline_report": str(baseline_file),
                "baseline_mean_score": prev_mean_score,
                "current_mean_score": curr_mean_score,
                "delta": score_delta,
            }
            if score_delta < (-1.0 * float(args.max_score_regression)):
                gates.append(
                    f"mean_score regression {score_delta:.3f} < -{float(args.max_score_regression):.3f}"
                )
        else:
            baseline_compare = {
                "baseline_report": str(baseline_file),
                "warning": "baseline report file not found",
            }

    report = {
        "ok": len(gates) == 0 and len(failed) == 0,
        "fixtures": len(results),
        "iterations": iterations,
        "workers": max(1, int(args.workers)),
        "failed_fixtures": len(failed),
        "failed_runs": failed_runs,
        "total_runs": total_runs,
        "gates": gates,
        "summary": {
            "failure_rate": failure_rate,
            "mean_score": (sum(all_scores) / len(all_scores)) if all_scores else 0.0,
            "min_score": min(all_scores) if all_scores else 0.0,
            "max_score": max(all_scores) if all_scores else 0.0,
            "mean_elapsed_ms": (sum(all_elapsed) / len(all_elapsed)) if all_elapsed else 0.0,
            "p95_elapsed_ms": p95_elapsed_ms,
        },
        "baseline_compare": baseline_compare,
        "results": results,
    }
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
