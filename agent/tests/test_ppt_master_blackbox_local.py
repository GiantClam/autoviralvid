from __future__ import annotations

from pathlib import Path

from src import ppt_master_blackbox_local as blackbox


def test_run_blackbox_request_delegates_to_native_runtime(monkeypatch, tmp_path: Path) -> None:
    project_path = tmp_path / "proj"
    project_path.mkdir(parents=True, exist_ok=True)

    def _fake_project_init(**kwargs):  # noqa: ANN001
        _ = kwargs
        return project_path

    def _fake_native_run(**kwargs):  # noqa: ANN001
        _ = kwargs
        return {
            "run_id": "run_x",
            "stages": [{"stage": "step7_svg_to_pptx.py", "ok": True}],
            "artifacts": {
                "design_spec": str(project_path / "design_spec.md"),
                "source_md": str(project_path / "sources" / "prompt_source.md"),
            },
            "export": {"output_pptx": str(project_path / "demo.pptx")},
        }

    monkeypatch.setattr(blackbox, "_project_init", _fake_project_init)
    monkeypatch.setattr(
        "src.ppt_master_native_runtime.run_native_pipeline",
        _fake_native_run,
    )

    result = blackbox.run_blackbox_request(
        {
            "prompt": "Create a university classroom deck on the Strait of Hormuz crisis.",
            "project_name": "ai_gen_test",
            "output_base_dir": str(tmp_path),
            "total_pages": 10,
            "style": "professional",
            "language": "zh-CN",
            "include_images": True,
            "template_family": "auto",
        }
    )

    assert result["export"]["generator_mode"] == "ppt_master_skill_runtime_local_skill"
    assert result["export"]["output_pptx"].endswith(".pptx")
    assert Path(result["artifacts"]["runtime_request"]).exists()
    assert Path(project_path / "runtime_result.json").exists()
