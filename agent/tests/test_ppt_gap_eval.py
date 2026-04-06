import json
from types import SimpleNamespace
from pathlib import Path

from src.ppt_gap_eval import (
    EVAL_QUALITY_PROFILE,
    _extract_baseline_slides_from_pptx,
    _pipeline_request_payload,
    build_baseline_score_record,
    extract_decision_execution_metrics,
    extract_topic_fact_metrics,
    extract_visual_professional_score,
    main,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_gap_eval_aggregate_produces_pass_verdict(tmp_path: Path):
    _write_json(
        tmp_path / "baseline-score.json",
        {
            "visual_avg_score": 8.1,
            "baseline_source_mode": "pptx_extract_to_minimax_json",
        },
    )

    courseware_scores = [8.6, 8.8, 8.7]
    work_scores = [8.3, 8.4, 8.2]
    pitch_scores = [8.5, 8.1, 8.2]

    for idx, score in enumerate(courseware_scores, start=1):
        _write_json(
            tmp_path / "courseware-runs" / f"cw-{idx}.json",
            {
                "run_id": f"cw-{idx}",
                "visual_avg_score": score,
                "accuracy_gate_passed": True,
                "candidate_mode": "pipeline_export",
            },
        )

    for idx, score in enumerate(work_scores, start=1):
        _write_json(
            tmp_path / "work-report-runs" / f"wr-{idx}.json",
            {
                "run_id": f"wr-{idx}",
                "visual_avg_score": score,
                "accuracy_gate_passed": True,
                "candidate_mode": "pipeline_export",
            },
        )

    for idx, score in enumerate(pitch_scores, start=1):
        _write_json(
            tmp_path / "pitch-runs" / f"ip-{idx}.json",
            {
                "run_id": f"ip-{idx}",
                "visual_avg_score": score,
                "accuracy_gate_passed": True,
                "candidate_mode": "pipeline_export",
            },
        )

    aggregate_path = tmp_path / "aggregate-report.json"
    verdict_path = tmp_path / "verdict.json"
    rc = main(
        [
            "aggregate",
            "--in",
            str(tmp_path),
            "--out",
            str(aggregate_path),
            "--verdict",
            str(verdict_path),
        ]
    )
    assert rc == 0

    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))

    assert aggregate["themes"]["courseware"]["mean_delta_vs_baseline"] > 0
    assert aggregate["baseline"]["baseline_source_mode"] == "pptx_extract_to_minimax_json"
    assert aggregate["themes"]["courseware"]["candidate_modes"] == ["pipeline_export"]
    assert aggregate["themes"]["work_report"]["pass_rate"] >= (2.0 / 3.0)
    assert aggregate["themes"]["investor_pitch"]["pass_rate"] >= (2.0 / 3.0)
    assert verdict["overall_pass"] is True
    assert verdict["failed_rules"] == []


def test_gap_eval_aggregate_fails_when_run_count_is_less_than_three(tmp_path: Path):
    _write_json(tmp_path / "baseline-score.json", {"visual_avg_score": 8.0, "baseline_source_mode": "test"})

    _write_json(
        tmp_path / "courseware-runs" / "cw-1.json",
        {"run_id": "cw-1", "visual_avg_score": 8.9, "accuracy_gate_passed": True},
    )
    _write_json(
        tmp_path / "work-report-runs" / "wr-1.json",
        {"run_id": "wr-1", "visual_avg_score": 8.9, "accuracy_gate_passed": True},
    )
    _write_json(
        tmp_path / "pitch-runs" / "ip-1.json",
        {"run_id": "ip-1", "visual_avg_score": 8.9, "accuracy_gate_passed": True},
    )

    aggregate_path = tmp_path / "aggregate-report.json"
    verdict_path = tmp_path / "verdict.json"
    rc = main(
        [
            "aggregate",
            "--in",
            str(tmp_path),
            "--out",
            str(aggregate_path),
            "--verdict",
            str(verdict_path),
        ]
    )
    assert rc == 0

    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["overall_pass"] is False
    assert "courseware_total_runs_ge_3" in verdict["failed_rules"]
    assert "work_report_total_runs_ge_3" in verdict["failed_rules"]
    assert "investor_pitch_total_runs_ge_3" in verdict["failed_rules"]


def test_gap_eval_aggregate_fails_on_quality_profile_mismatch(tmp_path: Path):
    _write_json(
        tmp_path / "baseline-score.json",
        {
            "visual_avg_score": 8.1,
            "baseline_source_mode": "pptx_extract_to_minimax_json",
            "quality_profile": EVAL_QUALITY_PROFILE,
        },
    )

    for idx in range(1, 4):
        _write_json(
            tmp_path / "courseware-runs" / f"cw-{idx}.json",
            {
                "run_id": f"cw-{idx}",
                "visual_avg_score": 8.8,
                "accuracy_gate_passed": True,
                "quality_profile": EVAL_QUALITY_PROFILE,
            },
        )
    for idx in range(1, 4):
        _write_json(
            tmp_path / "work-report-runs" / f"wr-{idx}.json",
            {
                "run_id": f"wr-{idx}",
                "visual_avg_score": 8.6,
                "accuracy_gate_passed": True,
                "quality_profile": EVAL_QUALITY_PROFILE,
            },
        )
    for idx in range(1, 4):
        _write_json(
            tmp_path / "pitch-runs" / f"ip-{idx}.json",
            {
                "run_id": f"ip-{idx}",
                "visual_avg_score": 8.6,
                "accuracy_gate_passed": True,
                "quality_profile": "lenient_draft" if idx == 1 else EVAL_QUALITY_PROFILE,
            },
        )

    aggregate_path = tmp_path / "aggregate-report.json"
    verdict_path = tmp_path / "verdict.json"
    rc = main(
        [
            "aggregate",
            "--in",
            str(tmp_path),
            "--out",
            str(aggregate_path),
            "--verdict",
            str(verdict_path),
        ]
    )
    assert rc == 0

    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert verdict["overall_pass"] is False
    assert "investor_pitch_quality_profile_match" in verdict["failed_rules"]


def test_extract_visual_professional_score_prefers_existing_payload():
    payload = {
        "visual_professional_score": {
            "color_consistency_score": 9.1,
            "layout_order_score": 8.8,
            "hierarchy_clarity_score": 8.9,
            "visual_avg_score": 8.93,
            "accuracy_gate_passed": True,
            "abnormal_tags": ["none"],
            "diagnostics": {"source": "existing"},
            "scorer_version": "v1",
        }
    }
    out = extract_visual_professional_score(payload)
    assert out["visual_avg_score"] == 8.93
    assert out["accuracy_gate_passed"] is True
    assert out["diagnostics"]["source"] == "existing"


def test_extract_visual_professional_score_falls_back_to_quality_score_branch():
    payload = {
        "quality_score": {
            "score": 79.0,
            "threshold": 72.0,
            "warn_threshold": 80.0,
            "passed": True,
            "dimensions": {"visual": 80.0, "layout": 78.0, "consistency": 76.0},
            "issue_counts": {"layout_homogeneous": 1},
            "diagnostics": {"visual_style_drift_ratio": 0.1, "visual_low_contrast_ratio": 0.1, "visual_issue_pressure": 0.2},
        },
        "observability_report": {"issue_codes": ["layout_homogeneous"]},
        "text_qa": {"issue_codes": []},
    }
    out = extract_visual_professional_score(payload)
    assert out["scorer_version"] == "v1"
    assert 0.0 <= out["visual_avg_score"] <= 10.0


def test_pipeline_request_payload_uses_canonical_quality_profile():
    payload = _pipeline_request_payload("courseware")
    assert payload["quality_profile"] == EVAL_QUALITY_PROFILE


def test_build_baseline_score_record_uses_canonical_quality_profile(monkeypatch, tmp_path: Path):
    baseline_pptx = tmp_path / "baseline.pptx"
    baseline_pptx.write_bytes(b"pptx")

    monkeypatch.setattr(
        "src.ppt_gap_eval._extract_baseline_slides_from_pptx",
        lambda _baseline: [{"slide_id": "s1", "title": "Baseline"}],
    )
    seen: dict = {}

    def _fake_score_visual_professional_metrics(*, slides=None, profile=None, **_kwargs):
        seen["profile"] = profile
        return SimpleNamespace(
            color_consistency_score=8.1,
            layout_order_score=8.2,
            hierarchy_clarity_score=8.3,
            visual_avg_score=8.2,
            accuracy_gate_passed=True,
            abnormal_tags=[],
            diagnostics={},
        )

    monkeypatch.setattr("src.ppt_gap_eval.score_visual_professional_metrics", _fake_score_visual_professional_metrics)
    record = build_baseline_score_record(baseline_pptx)

    assert seen["profile"] == EVAL_QUALITY_PROFILE
    assert record["quality_profile"] == EVAL_QUALITY_PROFILE


def test_run_rejects_quality_profile_mismatch_from_input_files(tmp_path: Path):
    out_root = tmp_path / "out"
    input_payload = {
        "data": {
            "run_id": "mismatch-run",
            "quality_profile": "lenient_draft",
            "export": {
                "quality_profile": "lenient_draft",
                "visual_professional_score": {
                    "color_consistency_score": 8.2,
                    "layout_order_score": 8.1,
                    "hierarchy_clarity_score": 8.0,
                    "visual_avg_score": 8.1,
                    "accuracy_gate_passed": True,
                    "abnormal_tags": [],
                    "diagnostics": {},
                },
            },
        }
    }
    input_file = tmp_path / "input-run.json"
    _write_json(input_file, input_payload)

    try:
        main(
            [
                "run",
                "--theme",
                "work_report",
                "--runs",
                "1",
                "--input-files",
                str(input_file),
                "--out",
                str(out_root),
            ]
        )
    except RuntimeError as exc:
        assert "quality_profile_mismatch" in str(exc)
    else:
        raise AssertionError("expected run to fail on quality profile mismatch")


def test_extract_baseline_slides_uses_no_compare_flag(monkeypatch, tmp_path: Path):
    baseline_pptx = tmp_path / "baseline.pptx"
    baseline_pptx.write_bytes(b"pptx")
    captured_cmd: dict = {}

    def _fake_run(cmd, capture_output, text, check):  # noqa: ANN001
        captured_cmd["cmd"] = list(cmd)
        out_index = cmd.index("--output") + 1
        out_path = Path(cmd[out_index])
        _write_json(out_path, {"slides": [{"slide_id": "s1"}]})
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("src.ppt_gap_eval.subprocess.run", _fake_run)
    slides = _extract_baseline_slides_from_pptx(baseline_pptx)
    assert slides == [{"slide_id": "s1"}]
    assert "--no-compare" in captured_cmd["cmd"]


def test_gap_eval_offline_matrix_generates_required_artifacts_without_live_renderer(tmp_path: Path):
    out_root = tmp_path / "ppt_gap_eval" / "2026-04-06"
    _write_json(
        out_root / "baseline-score.json",
        {
            "visual_avg_score": 8.1,
            "baseline_source_mode": "fixture",
            "quality_profile": EVAL_QUALITY_PROFILE,
        },
    )

    def _make_run_input(path: Path, run_id: str, score: float) -> None:
        _write_json(
            path,
            {
                "data": {
                    "run_id": run_id,
                    "quality_profile": EVAL_QUALITY_PROFILE,
                    "export": {
                        "quality_profile": EVAL_QUALITY_PROFILE,
                        "visual_professional_score": {
                            "color_consistency_score": score,
                            "layout_order_score": score,
                            "hierarchy_clarity_score": score,
                            "visual_avg_score": score,
                            "accuracy_gate_passed": True,
                            "abnormal_tags": [],
                            "diagnostics": {"source": "fixture"},
                        },
                    },
                }
            },
        )

    fixture_root = tmp_path / "fixtures"
    courseware_inputs = []
    work_inputs = []
    pitch_inputs = []
    for idx, score in enumerate([8.9, 9.0, 9.1], start=1):
        p = fixture_root / f"courseware-{idx}.json"
        _make_run_input(p, f"cw-{idx}", score)
        courseware_inputs.append(str(p))
    for idx, score in enumerate([8.5, 8.6, 8.7], start=1):
        p = fixture_root / f"work-{idx}.json"
        _make_run_input(p, f"wr-{idx}", score)
        work_inputs.append(str(p))
    for idx, score in enumerate([8.4, 8.5, 8.6], start=1):
        p = fixture_root / f"pitch-{idx}.json"
        _make_run_input(p, f"ip-{idx}", score)
        pitch_inputs.append(str(p))

    rc = main(["run", "--theme", "courseware", "--runs", "3", "--input-files", *courseware_inputs, "--out", str(out_root)])
    assert rc == 0
    rc = main(["run", "--theme", "work_report", "--runs", "3", "--input-files", *work_inputs, "--out", str(out_root)])
    assert rc == 0
    rc = main(["run", "--theme", "investor_pitch", "--runs", "3", "--input-files", *pitch_inputs, "--out", str(out_root)])
    assert rc == 0
    rc = main(["aggregate", "--in", str(out_root), "--out", str(out_root / "aggregate-report.json"), "--verdict", str(out_root / "verdict.json")])
    assert rc == 0

    assert (out_root / "baseline-score.json").exists()
    assert len(list((out_root / "courseware-runs").glob("*.json"))) == 3
    assert len(list((out_root / "work-report-runs").glob("*.json"))) == 3
    assert len(list((out_root / "pitch-runs").glob("*.json"))) == 3
    assert (out_root / "aggregate-report.json").exists()
    assert (out_root / "verdict.json").exists()

    verdict = json.loads((out_root / "verdict.json").read_text(encoding="utf-8"))
    assert verdict["overall_pass"] is True


def test_extract_topic_fact_metrics_detects_cross_topic_contamination():
    payload = {
        "slides": [
            {
                "title": "融资路演总览",
                "blocks": [
                    {"block_type": "body", "content": "市场机会与商业模式"},
                    {"block_type": "body", "content": "本季度工作汇报与课程总结"},
                ],
            }
        ],
        "text_qa": {"issue_codes": []},
    }
    metrics = extract_topic_fact_metrics(payload, theme="investor_pitch", prompt="请制作一份融资路演PPT")
    assert metrics["topic_consistency_score"] < 1.0
    assert metrics["cross_topic_contamination_count"] >= 1


def test_extract_decision_execution_metrics_detects_owner_conflict():
    payload = {
        "design_decision_v1": {
            "decision_trace": [
                {
                    "source": "layer1",
                    "owner": "a.py",
                    "owned_fields": ["template_family"],
                },
                {
                    "source": "render",
                    "owner": "b.mjs",
                    "owned_fields": ["template_family"],
                },
            ]
        },
        "observability_report": {"node_semantic_additions_count": 2},
    }
    metrics = extract_decision_execution_metrics(payload)
    assert metrics["decision_uniqueness_passed"] is False
    assert metrics["decision_owner_conflict_count"] == 1
    assert metrics["node_semantic_additions_count"] == 2
