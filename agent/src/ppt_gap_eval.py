"""PPT gap-eval utilities: single-run normalization + offline aggregation."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.ppt_quality_gate import QualityScoreResult, score_visual_professional_metrics

THEME_PROMPTS: Dict[str, str] = {
    "courseware": "请制作一份高中课堂展示课件，主题为“解码立法过程：理解其对国际关系的影响”",
    "work_report": "请制作一份企业季度工作汇报PPT，突出关键成果、问题与下阶段计划。",
    "investor_pitch": "请制作一份融资路演PPT，覆盖市场机会、产品方案、商业模式、财务预测和融资需求。",
}

THEME_OUTPUT_DIR = {
    "courseware": "courseware-runs",
    "work_report": "work-report-runs",
    "investor_pitch": "pitch-runs",
}
REQUIRED_RUNS_PER_THEME = 3
EVAL_QUALITY_PROFILE = "high_density_consulting"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _normalize_quality_profile(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text or EVAL_QUALITY_PROFILE


def _coerce_quality_score(payload: Dict[str, Any]) -> Optional[QualityScoreResult]:
    quality = payload.get("quality_score") if isinstance(payload.get("quality_score"), dict) else None
    if not isinstance(quality, dict):
        return None
    dims = quality.get("dimensions") if isinstance(quality.get("dimensions"), dict) else {}
    issue_counts_raw = quality.get("issue_counts") if isinstance(quality.get("issue_counts"), dict) else {}
    issue_counts = {str(k): int(v) for k, v in issue_counts_raw.items()}
    diags = quality.get("diagnostics") if isinstance(quality.get("diagnostics"), dict) else {}
    return QualityScoreResult(
        score=_to_float(quality.get("score"), 0.0),
        passed=bool(quality.get("passed", False)),
        threshold=_to_float(quality.get("threshold"), 72.0),
        warn_threshold=_to_float(quality.get("warn_threshold"), 80.0),
        dimensions={str(k): _to_float(v, 0.0) for k, v in dims.items()},
        issue_counts=issue_counts,
        diagnostics=diags,
    )


def extract_visual_professional_score(payload: Dict[str, Any]) -> Dict[str, Any]:
    existing = payload.get("visual_professional_score") if isinstance(payload.get("visual_professional_score"), dict) else None
    if isinstance(existing, dict):
        return {
            "color_consistency_score": _to_float(existing.get("color_consistency_score"), 0.0),
            "layout_order_score": _to_float(existing.get("layout_order_score"), 0.0),
            "hierarchy_clarity_score": _to_float(existing.get("hierarchy_clarity_score"), 0.0),
            "visual_avg_score": _to_float(existing.get("visual_avg_score"), 0.0),
            "accuracy_gate_passed": bool(existing.get("accuracy_gate_passed", False)),
            "abnormal_tags": [str(item) for item in (existing.get("abnormal_tags") or []) if str(item).strip()],
            "diagnostics": existing.get("diagnostics") if isinstance(existing.get("diagnostics"), dict) else {},
            "scorer_version": str(existing.get("scorer_version") or "v1"),
        }

    quality_score = _coerce_quality_score(payload)
    issue_codes: List[str] = []
    if isinstance(payload.get("observability_report"), dict):
        issue_codes = [
            str(item) for item in (payload.get("observability_report", {}).get("issue_codes") or []) if str(item).strip()
        ]
    text_issue_codes = []
    if isinstance(payload.get("text_qa"), dict):
        text_issue_codes = [str(item) for item in (payload.get("text_qa", {}).get("issue_codes") or []) if str(item).strip()]

    slides: List[Dict[str, Any]] = []
    for key in ("slides", "video_slides"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            slides = [row for row in value if isinstance(row, dict)]
            if slides:
                break

    scored = score_visual_professional_metrics(
        slides=slides,
        quality_score=quality_score,
        issue_codes=issue_codes,
        text_issue_codes=text_issue_codes,
        visual_audit=payload.get("visual_qa") if isinstance(payload.get("visual_qa"), dict) else None,
    )
    return {
        "color_consistency_score": float(scored.color_consistency_score),
        "layout_order_score": float(scored.layout_order_score),
        "hierarchy_clarity_score": float(scored.hierarchy_clarity_score),
        "visual_avg_score": float(scored.visual_avg_score),
        "accuracy_gate_passed": bool(scored.accuracy_gate_passed),
        "abnormal_tags": list(scored.abnormal_tags),
        "diagnostics": dict(scored.diagnostics),
        "scorer_version": "v1",
    }


def _extract_baseline_slides_from_pptx(baseline_pptx: Path) -> List[Dict[str, Any]]:
    repo_root = _repo_root()
    extractor_script = repo_root / "scripts" / "extract_to_minimax_json.py"
    if not extractor_script.exists():
        raise RuntimeError(f"extractor script missing: {extractor_script}")

    with tempfile.TemporaryDirectory(prefix="ppt-gap-baseline-") as tmpdir:
        out_path = Path(tmpdir) / "baseline.json"
        cmd = [
            sys.executable,
            str(extractor_script),
            "--input",
            str(baseline_pptx),
            "--output",
            str(out_path),
            "--no-compare",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"baseline extract failed: {(proc.stderr or proc.stdout)[:300]}")
        payload = _read_json(out_path)
        slides = payload.get("slides") if isinstance(payload.get("slides"), list) else []
        return [row for row in slides if isinstance(row, dict)]


def build_baseline_score_record(baseline_pptx: Path) -> Dict[str, Any]:
    slides = _extract_baseline_slides_from_pptx(baseline_pptx)
    scored = score_visual_professional_metrics(slides=slides, profile=EVAL_QUALITY_PROFILE)
    return {
        "baseline_pptx": str(baseline_pptx),
        "baseline_source_mode": "pptx_extract_to_minimax_json",
        "quality_profile": EVAL_QUALITY_PROFILE,
        "color_consistency_score": float(scored.color_consistency_score),
        "layout_order_score": float(scored.layout_order_score),
        "hierarchy_clarity_score": float(scored.hierarchy_clarity_score),
        "visual_avg_score": float(scored.visual_avg_score),
        "accuracy_gate_passed": bool(scored.accuracy_gate_passed),
        "abnormal_tags": list(scored.abnormal_tags),
        "diagnostics": dict(scored.diagnostics),
        "scorer_version": "v1",
    }


def _pipeline_request_payload(
    theme: str,
    *,
    candidate_mode: str = "pipeline_export",
    reference_desc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    prompt = THEME_PROMPTS.get(theme, THEME_PROMPTS["courseware"])
    purpose = {
        "courseware": "课程讲义",
        "work_report": "工作汇报",
        "investor_pitch": "融资路演",
    }.get(theme, "presentation")
    payload = {
        "topic": prompt,
        "audience": "high-school-students" if theme == "courseware" else "general",
        "purpose": purpose,
        "style_preference": "professional",
        "total_pages": 10,
        "language": "zh-CN",
        "with_export": True,
        "save_artifacts": True,
        "route_mode": "refine",
        "quality_profile": EVAL_QUALITY_PROFILE,
        "execution_profile": "auto",
    }
    if str(candidate_mode).strip().lower() == "reference_reconstruct":
        payload["reconstruct_from_reference"] = True
        if isinstance(reference_desc, dict):
            payload["reference_desc"] = reference_desc
    return payload


def _post_json(url: str, payload: Dict[str, Any], timeout_sec: int = 900) -> Dict[str, Any]:
    req = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=max(30, int(timeout_sec))) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc

    try:
        parsed = json.loads(body)
    except Exception as exc:
        raise RuntimeError(f"non-json response: {body[:280]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("invalid response shape")
    return parsed


def _normalize_pipeline_export_payload(resp_data: Dict[str, Any]) -> Dict[str, Any]:
    export_payload = resp_data.get("export") if isinstance(resp_data.get("export"), dict) else None
    if isinstance(export_payload, dict):
        return export_payload
    return resp_data


def _run_theme_once(
    theme: str,
    renderer_base: str,
    *,
    candidate_mode: str = "pipeline_export",
    reference_desc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = _pipeline_request_payload(
        theme,
        candidate_mode=candidate_mode,
        reference_desc=reference_desc,
    )
    endpoint = renderer_base.rstrip("/") + "/api/v1/ppt/pipeline"
    resp = _post_json(endpoint, payload)
    if not bool(resp.get("success")):
        raise RuntimeError(f"pipeline failed: {json.dumps(resp, ensure_ascii=False)[:500]}")
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    if not isinstance(data, dict):
        raise RuntimeError("pipeline response missing data dict")
    return data


def _list_run_files(run_dir: Path) -> List[Path]:
    if not run_dir.exists():
        return []
    return sorted(path for path in run_dir.glob("*.json") if path.is_file())


def _theme_stats(records: List[Dict[str, Any]], *, baseline_score: Optional[float] = None) -> Dict[str, Any]:
    total = len(records)
    visual_scores = [_to_float(row.get("visual_avg_score"), 0.0) for row in records]
    passing_runs = sum(
        1
        for row in records
        if (_to_float(row.get("visual_avg_score"), 0.0) > 8.0) and bool(row.get("accuracy_gate_passed", False))
    )
    pass_rate = (float(passing_runs) / float(total)) if total else 0.0
    mean_visual = float(statistics.mean(visual_scores)) if visual_scores else 0.0
    stddev_visual = float(statistics.pstdev(visual_scores)) if len(visual_scores) > 1 else 0.0
    accuracy_all_pass = all(bool(row.get("accuracy_gate_passed", False)) for row in records) if records else False

    out: Dict[str, Any] = {
        "total_runs": total,
        "passing_runs": passing_runs,
        "pass_rate": pass_rate,
        "mean_visual_avg_score": mean_visual,
        "stddev_visual_avg_score": stddev_visual,
        "accuracy_all_pass": bool(accuracy_all_pass),
        "candidate_modes": sorted(
            {
                str(row.get("candidate_mode") or "").strip()
                for row in records
                if str(row.get("candidate_mode") or "").strip()
            }
        ),
    }
    if baseline_score is not None:
        deltas = [(_to_float(row.get("visual_avg_score"), 0.0) - float(baseline_score)) for row in records]
        out["mean_delta_vs_baseline"] = float(statistics.mean(deltas)) if deltas else 0.0
    return out


def _theme_profile_mismatch_count(records: List[Dict[str, Any]], *, expected_profile: str) -> int:
    expected = _normalize_quality_profile(expected_profile)
    return sum(
        1
        for row in records
        if _normalize_quality_profile(row.get("quality_profile")) != expected
    )


def command_baseline(args: argparse.Namespace) -> int:
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    baseline_path = Path(args.baseline).resolve()
    record = build_baseline_score_record(baseline_path)
    _write_json(out_root / "baseline-score.json", record)
    print(json.dumps({"ok": True, "baseline_score": record.get("visual_avg_score")}, ensure_ascii=False))
    return 0


def command_run(args: argparse.Namespace) -> int:
    theme = str(args.theme)
    runs = max(1, int(args.runs))
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    baseline_score_value: Optional[float] = None
    baseline_source_mode = ""
    expected_quality_profile = EVAL_QUALITY_PROFILE
    baseline_record_path = out_root / "baseline-score.json"
    if theme == "courseware":
        if baseline_record_path.exists():
            baseline_record = _read_json(baseline_record_path)
            baseline_score_value = _to_float(baseline_record.get("visual_avg_score"), 0.0)
            baseline_source_mode = str(baseline_record.get("baseline_source_mode") or "").strip()
            expected_quality_profile = _normalize_quality_profile(baseline_record.get("quality_profile"))
        elif args.baseline:
            baseline_record = build_baseline_score_record(Path(args.baseline).resolve())
            _write_json(baseline_record_path, baseline_record)
            baseline_score_value = _to_float(baseline_record.get("visual_avg_score"), 0.0)
            baseline_source_mode = str(baseline_record.get("baseline_source_mode") or "").strip()
            expected_quality_profile = _normalize_quality_profile(baseline_record.get("quality_profile"))

    run_dir = out_root / THEME_OUTPUT_DIR[theme]
    run_dir.mkdir(parents=True, exist_ok=True)

    input_files = [Path(p).resolve() for p in (args.input_files or [])]
    reference_desc = {}
    if str(args.reference_desc_json or "").strip():
        reference_desc = _read_json(Path(args.reference_desc_json).resolve())
    candidate_mode = str(args.candidate_mode or "pipeline_export").strip().lower() or "pipeline_export"
    written: List[str] = []
    for idx in range(runs):
        run_candidate_mode = candidate_mode
        if input_files:
            source_path = input_files[idx % len(input_files)]
            source_payload = _read_json(source_path)
            run_data = source_payload.get("data") if isinstance(source_payload.get("data"), dict) else source_payload
            pipeline_run_id = str(run_data.get("run_id") or "") if isinstance(run_data, dict) else ""
            if isinstance(run_data, dict):
                source_candidate_mode = str(run_data.get("candidate_mode") or "").strip().lower()
                if source_candidate_mode:
                    run_candidate_mode = source_candidate_mode
        else:
            run_data = _run_theme_once(
                theme,
                renderer_base=str(args.renderer_base),
                candidate_mode=candidate_mode,
                reference_desc=reference_desc if isinstance(reference_desc, dict) else None,
            )
            pipeline_run_id = str(run_data.get("run_id") or "")

        export_payload = _normalize_pipeline_export_payload(run_data if isinstance(run_data, dict) else {})
        run_quality_profile = _normalize_quality_profile(
            export_payload.get("quality_profile")
            if isinstance(export_payload, dict)
            else run_data.get("quality_profile") if isinstance(run_data, dict) else ""
        )
        if run_quality_profile != expected_quality_profile:
            raise RuntimeError(
                "quality_profile_mismatch:"
                f" expected={expected_quality_profile} got={run_quality_profile} run={pipeline_run_id or idx + 1}"
            )
        visual = extract_visual_professional_score(export_payload)
        run_id = pipeline_run_id or str(uuid.uuid4())
        record = {
            "run_id": run_id,
            "theme": theme,
            "visual_avg_score": float(visual.get("visual_avg_score", 0.0)),
            "color_consistency_score": float(visual.get("color_consistency_score", 0.0)),
            "layout_order_score": float(visual.get("layout_order_score", 0.0)),
            "hierarchy_clarity_score": float(visual.get("hierarchy_clarity_score", 0.0)),
            "accuracy_gate_passed": bool(visual.get("accuracy_gate_passed", False)),
            "abnormal_tags": list(visual.get("abnormal_tags") or []),
            "scorer_version": str(visual.get("scorer_version") or "v1"),
            "candidate_mode": run_candidate_mode,
            "quality_profile": run_quality_profile,
            "source": {
                "pipeline_run_id": pipeline_run_id,
                "has_export_payload": bool(export_payload),
            },
        }
        if baseline_score_value is not None:
            record["baseline_visual_avg_score"] = float(baseline_score_value)
            record["delta_vs_baseline"] = float(record["visual_avg_score"] - baseline_score_value)
            if baseline_source_mode:
                record["baseline_source_mode"] = baseline_source_mode

        out_path = run_dir / f"{run_id}.json"
        _write_json(out_path, record)
        written.append(str(out_path))

    print(
        json.dumps(
            {
                "ok": True,
                "theme": theme,
                "runs": runs,
                "written": written,
                "baseline_visual_avg_score": baseline_score_value,
                "candidate_mode": candidate_mode,
            },
            ensure_ascii=False,
        )
    )
    return 0


def command_aggregate(args: argparse.Namespace) -> int:
    in_root = Path(args.input_dir).resolve()
    out_path = Path(args.out).resolve()
    verdict_path = Path(args.verdict).resolve()

    baseline_score = None
    baseline_source_mode = ""
    expected_quality_profile = EVAL_QUALITY_PROFILE
    baseline_path = in_root / "baseline-score.json"
    if baseline_path.exists():
        baseline_payload = _read_json(baseline_path)
        baseline_score = _to_float(baseline_payload.get("visual_avg_score"), 0.0)
        baseline_source_mode = str(baseline_payload.get("baseline_source_mode") or "").strip()
        expected_quality_profile = _normalize_quality_profile(baseline_payload.get("quality_profile"))

    theme_records: Dict[str, List[Dict[str, Any]]] = {
        "courseware": [_read_json(path) for path in _list_run_files(in_root / "courseware-runs")],
        "work_report": [_read_json(path) for path in _list_run_files(in_root / "work-report-runs")],
        "investor_pitch": [_read_json(path) for path in _list_run_files(in_root / "pitch-runs")],
    }

    themes_report = {
        "courseware": _theme_stats(theme_records["courseware"], baseline_score=baseline_score),
        "work_report": _theme_stats(theme_records["work_report"]),
        "investor_pitch": _theme_stats(theme_records["investor_pitch"]),
    }
    profile_mismatch_counts = {
        "courseware": _theme_profile_mismatch_count(theme_records["courseware"], expected_profile=expected_quality_profile),
        "work_report": _theme_profile_mismatch_count(theme_records["work_report"], expected_profile=expected_quality_profile),
        "investor_pitch": _theme_profile_mismatch_count(theme_records["investor_pitch"], expected_profile=expected_quality_profile),
    }
    for theme_name, mismatch_count in profile_mismatch_counts.items():
        themes_report[theme_name]["quality_profile_expected"] = expected_quality_profile
        themes_report[theme_name]["quality_profile_mismatch_count"] = int(mismatch_count)
        themes_report[theme_name]["quality_profiles"] = sorted(
            {
                _normalize_quality_profile(row.get("quality_profile"))
                for row in theme_records[theme_name]
            }
        )

    rule_results = {
        "courseware_total_runs_ge_3": themes_report["courseware"]["total_runs"] >= REQUIRED_RUNS_PER_THEME,
        "courseware_each_run_visual_gt_8_and_accuracy": all(
            (_to_float(row.get("visual_avg_score"), 0.0) > 8.0) and bool(row.get("accuracy_gate_passed", False))
            for row in theme_records["courseware"]
        )
        and (themes_report["courseware"]["total_runs"] >= REQUIRED_RUNS_PER_THEME),
        "courseware_mean_delta_vs_baseline_gt_0": _to_float(
            themes_report["courseware"].get("mean_delta_vs_baseline"), -999.0
        )
        > 0.0,
        "work_report_total_runs_ge_3": themes_report["work_report"]["total_runs"] >= REQUIRED_RUNS_PER_THEME,
        "work_report_mean_visual_gt_8": _to_float(themes_report["work_report"].get("mean_visual_avg_score"), 0.0) > 8.0,
        "work_report_pass_rate_ge_2_3": _to_float(themes_report["work_report"].get("pass_rate"), 0.0) >= (2.0 / 3.0),
        "work_report_accuracy_all_pass": bool(themes_report["work_report"].get("accuracy_all_pass", False)),
        "investor_pitch_total_runs_ge_3": themes_report["investor_pitch"]["total_runs"] >= REQUIRED_RUNS_PER_THEME,
        "investor_pitch_mean_visual_gt_8": _to_float(themes_report["investor_pitch"].get("mean_visual_avg_score"), 0.0) > 8.0,
        "investor_pitch_pass_rate_ge_2_3": _to_float(themes_report["investor_pitch"].get("pass_rate"), 0.0) >= (2.0 / 3.0),
        "investor_pitch_accuracy_all_pass": bool(themes_report["investor_pitch"].get("accuracy_all_pass", False)),
        "courseware_stability_stddev_le_0_50": _to_float(themes_report["courseware"].get("stddev_visual_avg_score"), 999.0)
        <= 0.50,
        "work_report_stability_stddev_le_0_50": _to_float(themes_report["work_report"].get("stddev_visual_avg_score"), 999.0)
        <= 0.50,
        "investor_pitch_stability_stddev_le_0_50": _to_float(
            themes_report["investor_pitch"].get("stddev_visual_avg_score"), 999.0
        )
        <= 0.50,
        "courseware_quality_profile_match": profile_mismatch_counts["courseware"] == 0,
        "work_report_quality_profile_match": profile_mismatch_counts["work_report"] == 0,
        "investor_pitch_quality_profile_match": profile_mismatch_counts["investor_pitch"] == 0,
    }
    failed_rules = [name for name, ok in rule_results.items() if not bool(ok)]
    overall_pass = len(failed_rules) == 0

    aggregate_report = {
        "baseline": {
            "visual_avg_score": baseline_score,
            "path": str(baseline_path) if baseline_path.exists() else "",
            "baseline_source_mode": baseline_source_mode,
            "quality_profile": expected_quality_profile,
        },
        "themes": themes_report,
        "rule_results": rule_results,
        "failed_rules": failed_rules,
        "overall_pass": overall_pass,
    }
    _write_json(out_path, aggregate_report)
    _write_json(
        verdict_path,
        {
            "overall_pass": overall_pass,
            "failed_rules": failed_rules,
            "rule_results": rule_results,
        },
    )
    print(json.dumps({"ok": True, "overall_pass": overall_pass, "failed_rules": failed_rules}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PPT gap evaluation helper")
    sub = parser.add_subparsers(dest="command", required=True)

    baseline = sub.add_parser("baseline", help="build baseline-score.json from baseline pptx")
    baseline.add_argument("--baseline", required=True)
    baseline.add_argument("--out", required=True)
    baseline.set_defaults(func=command_baseline)

    run = sub.add_parser("run", help="run theme generation/evidence collection")
    run.add_argument("--theme", choices=sorted(THEME_PROMPTS.keys()), required=True)
    run.add_argument("--runs", type=int, default=1)
    run.add_argument("--baseline", default="")
    run.add_argument("--renderer-base", default=os.getenv("RENDERER_BASE", "http://127.0.0.1:8124"))
    run.add_argument("--candidate-mode", choices=["pipeline_export", "reference_reconstruct"], default="pipeline_export")
    run.add_argument("--reference-desc-json", default="")
    run.add_argument("--input-files", nargs="*", default=[])
    run.add_argument("--out", required=True)
    run.set_defaults(func=command_run)

    agg = sub.add_parser("aggregate", help="aggregate run artifacts and emit verdict")
    agg.add_argument("--in", dest="input_dir", required=True)
    agg.add_argument("--out", required=True)
    agg.add_argument("--verdict", required=True)
    agg.set_defaults(func=command_aggregate)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
