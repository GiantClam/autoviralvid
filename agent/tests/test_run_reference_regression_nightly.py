import importlib.util
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "run_reference_regression_nightly.py"
    spec = importlib.util.spec_from_file_location("run_reference_regression_nightly", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_parse_scenarios_defaults():
    mod = _load_module()
    scenarios = mod._parse_scenarios("")
    assert [s.name for s in scenarios] == ["dev", "holdout", "challenge"]


def test_parse_scenarios_invalid_raises():
    mod = _load_module()
    try:
        mod._parse_scenarios("dev,unknown")
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_build_phase_tag_and_date_tag():
    mod = _load_module()
    assert mod._normalize_date_tag("2026-04-01") == "2026-04-01"
    assert mod._build_phase_tag(date_tag="2026-04-01", scenario="dev", round_index=2) == "2026-04-01-dev-r2"


def test_score_stats_and_flaky_detection():
    mod = _load_module()
    rows = [
        {"score": 64.1},
        {"score": 64.6},
    ]
    stats = mod._score_stats(rows)
    assert stats["count"] == 2
    assert stats["max"] >= stats["min"]
    assert mod._is_flaky(rows, threshold=0.3) is True
    assert mod._is_flaky(rows, threshold=0.6) is False


def test_build_once_command_includes_critic_and_focus():
    mod = _load_module()
    scenario = mod._SCENARIO_PRESETS["challenge"]
    cmd = mod._build_once_command(
        python_bin="python",
        reference_ppt=Path("ref.pptx"),
        pages="1-20",
        phase="2026-04-01-challenge-r1",
        output_dir=Path("output/nightly"),
        fix_record_path=Path("output/nightly/fix_record.nightly.json"),
        fix_plan_path=Path("output/nightly/fix_plan.nightly.json"),
        scenario=scenario,
        run_mode="local",
    )
    assert "--visual-critic-repair" in cmd
    assert "on" in cmd
    assert "--focus-cluster" in cmd
    idx = cmd.index("--focus-cluster")
    assert cmd[idx + 1] == "geometry"
    mode_idx = cmd.index("--mode")
    assert cmd[mode_idx + 1] == "local"
    pipeline_idx = cmd.index("--reconstruct-via-pipeline")
    assert cmd[pipeline_idx + 1] == "off"


def test_build_cluster_command_writes_default_cluster_output():
    mod = _load_module()
    cmd = mod._build_cluster_command(
        python_bin="python",
        nightly_dir=Path("output/nightly/2026-04-01"),
    )
    assert cmd[1].endswith("build_archetype_slot_clusters.py")
    assert "--nightly-dir" in cmd
    assert "--output" in cmd
    out_idx = cmd.index("--output")
    assert cmd[out_idx + 1].endswith("archetype_slot_clusters.json")
