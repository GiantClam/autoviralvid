from __future__ import annotations

from pathlib import Path

from src import ppt_master_blackbox_local as blackbox
from src import ppt_master_native_runtime as native_runtime


def test_native_runtime_missing_prompt_raises(tmp_path: Path) -> None:
    project_path = tmp_path / "proj"
    project_path.mkdir(parents=True, exist_ok=True)
    try:
        native_runtime.run_native_pipeline(
            request_payload={},
            project_path=project_path,
            timeout_sec=300,
        )
    except RuntimeError as exc:
        assert "missing_prompt" in str(exc)
    else:
        raise AssertionError("expected missing_prompt runtime error")


def test_blackbox_request_delegates_to_native_runtime(monkeypatch, tmp_path: Path) -> None:
    project_path = tmp_path / "proj"
    project_path.mkdir(parents=True, exist_ok=True)

    called = {"value": False}

    def _fake_run_native_pipeline(*, request_payload, project_path, timeout_sec):  # noqa: ANN001
        called["value"] = True
        return {
            "run_id": "native_x",
            "stages": [{"stage": "step7_svg_to_pptx.py", "ok": True}],
            "artifacts": {
                "design_spec": str(project_path / "design_spec.md"),
            },
            "export": {"output_pptx": str(project_path / "demo.pptx")},
        }

    def _fake_project_init(**kwargs):  # noqa: ANN001
        _ = kwargs
        return project_path

    monkeypatch.setattr(blackbox, "_project_init", _fake_project_init)
    monkeypatch.setattr(
        "src.ppt_master_native_runtime.run_native_pipeline",
        _fake_run_native_pipeline,
    )

    out = blackbox.run_blackbox_request(
        {
            "prompt": "Create a deck about global shipping security.",
            "project_name": "demo",
            "output_base_dir": str(tmp_path),
            "timeout_sec": 600,
        }
    )
    assert called["value"] is True
    assert isinstance(out, dict)
    assert out.get("run_id") == "native_x"
    assert str((out.get("export") or {}).get("output_pptx") or "").endswith(".pptx")
    assert (project_path / "runtime_result.json").exists()
