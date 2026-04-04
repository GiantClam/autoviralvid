#!/usr/bin/env python3
"""Nightly orchestrator for reference regression assetization."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, NamedTuple


class NightlyScenario(NamedTuple):
    name: str
    creation_mode: str
    focus_cluster: str
    quality_bar: str
    visual_critic_repair: str


_SCENARIO_PRESETS: Dict[str, NightlyScenario] = {
    "dev": NightlyScenario(
        name="dev",
        creation_mode="fidelity",
        focus_cluster="geometry",
        quality_bar="high",
        visual_critic_repair="on",
    ),
    "holdout": NightlyScenario(
        name="holdout",
        creation_mode="fidelity",
        focus_cluster="layout",
        quality_bar="high",
        visual_critic_repair="off",
    ),
    "challenge": NightlyScenario(
        name="challenge",
        creation_mode="zero_create",
        focus_cluster="geometry",
        quality_bar="high",
        visual_critic_repair="on",
    ),
}


def _normalize_date_tag(raw: str) -> str:
    text = "".join(ch for ch in str(raw or "").strip() if ch.isalnum() or ch in {"-", "_"})
    text = text.strip("-_")
    if text:
        return text
    return datetime.now().strftime("%Y%m%d")


def _parse_scenarios(raw: str) -> List[NightlyScenario]:
    names = [str(item).strip().lower() for item in str(raw or "").split(",") if str(item).strip()]
    if not names:
        names = ["dev", "holdout", "challenge"]
    out: List[NightlyScenario] = []
    for name in names:
        scenario = _SCENARIO_PRESETS.get(name)
        if scenario is None:
            raise ValueError(f"unknown scenario: {name}")
        out.append(scenario)
    return out


def _build_phase_tag(*, date_tag: str, scenario: str, round_index: int) -> str:
    return f"{date_tag}-{scenario}-r{int(round_index)}"


def _load_summary(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _score_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    scores = [float(row.get("score", 0) or 0) for row in rows]
    if not scores:
        return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0, "delta": 0.0}
    return {
        "count": len(scores),
        "mean": float(mean(scores)),
        "min": float(min(scores)),
        "max": float(max(scores)),
        "delta": float(max(scores) - min(scores)),
    }


def _is_flaky(rows: List[Dict[str, Any]], threshold: float) -> bool:
    stats = _score_stats(rows)
    return bool(stats["count"] >= 2 and float(stats["delta"]) > float(threshold))


def _build_once_command(
    *,
    python_bin: str,
    reference_ppt: Path,
    pages: str,
    phase: str,
    output_dir: Path,
    fix_record_path: Path,
    fix_plan_path: Path,
    scenario: NightlyScenario,
    run_mode: str,
) -> List[str]:
    generated_ppt = output_dir / f"generated.{phase}.pptx"
    render_json = output_dir / f"generated.{phase}.render.json"
    issues_json = output_dir / f"issues.{phase}.json"
    summary_json = output_dir / f"round_summary.{phase}.json"
    reconstruct_via_pipeline = "off" if str(run_mode or "auto").strip().lower() == "local" else "on"
    return [
        python_bin,
        "scripts/run_reference_regression_once.py",
        "--reference-ppt",
        str(reference_ppt),
        "--pages",
        str(pages),
        "--phase",
        str(phase),
        "--quality-bar",
        str(scenario.quality_bar),
        "--compare-mode",
        "auto",
        "--creation-mode",
        str(scenario.creation_mode),
        "--mode",
        str(run_mode or "auto"),
        "--local-strategy",
        "reconstruct",
        "--fallback-local-strategy",
        "none",
        "--reconstruct-template-shell",
        "auto",
        "--reconstruct-source-aligned",
        "auto",
        "--reconstruct-via-pipeline",
        reconstruct_via_pipeline,
        "--focus-cluster",
        str(scenario.focus_cluster),
        "--single-cluster",
        "on",
        "--visual-critic-repair",
        str(scenario.visual_critic_repair),
        "--generated-ppt",
        str(generated_ppt),
        "--render-json",
        str(render_json),
        "--issues-json",
        str(issues_json),
        "--summary-json",
        str(summary_json),
        "--fix-record",
        str(fix_record_path),
        "--fix-plan",
        str(fix_plan_path),
    ]


def _build_cluster_command(*, python_bin: str, nightly_dir: Path) -> List[str]:
    return [
        python_bin,
        "scripts/build_archetype_slot_clusters.py",
        "--nightly-dir",
        str(nightly_dir),
        "--output",
        str(nightly_dir / "archetype_slot_clusters.json"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Nightly reference regression orchestrator")
    parser.add_argument(
        "--reference-ppt",
        default=r"C:\Users\liula\Downloads\ppt2\ppt2\1.pptx",
        help="Reference PPT path",
    )
    parser.add_argument("--pages", default="1-20", help="Pages range for extraction")
    parser.add_argument("--scenarios", default="dev,holdout,challenge", help="Comma-separated scenario names")
    parser.add_argument("--rounds", type=int, default=1, help="Rounds per scenario")
    parser.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "local", "api"],
        help="run_reference_regression_once mode",
    )
    parser.add_argument("--date-tag", default="", help="Date tag for nightly folder and phases")
    parser.add_argument(
        "--output-root",
        default="output/regression/nightly",
        help="Root output directory for nightly assets",
    )
    parser.add_argument(
        "--flaky-threshold",
        type=float,
        default=0.25,
        help="Score delta threshold to mark a scenario as flaky when rounds>=2",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print commands without executing")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    python_bin = sys.executable
    reference_ppt = Path(args.reference_ppt)
    if not reference_ppt.exists():
        raise FileNotFoundError(f"reference ppt not found: {reference_ppt}")

    scenarios = _parse_scenarios(args.scenarios)
    rounds = max(1, int(args.rounds))
    date_tag = _normalize_date_tag(args.date_tag)
    nightly_dir = Path(args.output_root) / date_tag
    nightly_dir.mkdir(parents=True, exist_ok=True)
    fix_record_path = nightly_dir / "fix_record.nightly.json"
    fix_plan_path = nightly_dir / "fix_plan.nightly.json"
    run_rows: List[Dict[str, Any]] = []

    for scenario in scenarios:
        for round_index in range(1, rounds + 1):
            phase = _build_phase_tag(
                date_tag=date_tag,
                scenario=scenario.name,
                round_index=round_index,
            )
            cmd = _build_once_command(
                python_bin=python_bin,
                reference_ppt=reference_ppt,
                pages=args.pages,
                phase=phase,
                output_dir=nightly_dir,
                fix_record_path=fix_record_path,
                fix_plan_path=fix_plan_path,
                scenario=scenario,
                run_mode=str(args.mode),
            )
            print(f"[NIGHTLY] phase={phase} scenario={scenario.name}")
            print(f"[RUN] {' '.join(cmd)}")
            if args.dry_run:
                run_rows.append(
                    {
                        "phase": phase,
                        "scenario": scenario.name,
                        "status": "DRY_RUN",
                        "score": 0.0,
                        "summary_json": str((nightly_dir / f"round_summary.{phase}.json").resolve()),
                    }
                )
                continue

            result = subprocess.run(cmd, cwd=str(repo_root))
            summary_path = nightly_dir / f"round_summary.{phase}.json"
            summary = _load_summary(summary_path)
            run_rows.append(
                {
                    "phase": phase,
                    "scenario": scenario.name,
                    "status": str(summary.get("status") or f"EXIT_{result.returncode}"),
                    "score": float(summary.get("score", 0) or 0.0),
                    "issue_count": int(summary.get("issue_count", 0) or 0),
                    "summary_json": str(summary_path.resolve()),
                }
            )

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in run_rows:
        grouped.setdefault(str(row.get("scenario") or "unknown"), []).append(row)
    scenario_summary: Dict[str, Any] = {}
    for name, rows in grouped.items():
        scenario_summary[name] = {
            "stats": _score_stats(rows),
            "flaky": _is_flaky(rows, threshold=float(args.flaky_threshold)),
            "latest_status": str(rows[-1].get("status") or ""),
        }

    cluster_output_path = nightly_dir / "archetype_slot_clusters.json"
    cluster_asset: Dict[str, Any] = {
        "status": "SKIPPED",
        "output_json": str(cluster_output_path.resolve()),
    }
    cluster_cmd = _build_cluster_command(python_bin=python_bin, nightly_dir=nightly_dir)
    print(f"[NIGHTLY] cluster_cmd={' '.join(cluster_cmd)}")
    if args.dry_run:
        cluster_asset["status"] = "DRY_RUN"
    else:
        cluster_result = subprocess.run(cluster_cmd, cwd=str(repo_root))
        cluster_asset["status"] = "OK" if cluster_result.returncode == 0 else f"EXIT_{cluster_result.returncode}"
        cluster_asset["exists"] = bool(cluster_output_path.exists())

    manifest = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "date_tag": date_tag,
        "reference_ppt": str(reference_ppt.resolve()),
        "pages": str(args.pages),
        "rounds": rounds,
        "scenarios": [scenario.name for scenario in scenarios],
        "rows": run_rows,
        "scenario_summary": scenario_summary,
        "fix_record": str(fix_record_path.resolve()),
        "fix_plan": str(fix_plan_path.resolve()),
        "cluster_asset": cluster_asset,
    }
    manifest_path = nightly_dir / "nightly_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[NIGHTLY] manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
