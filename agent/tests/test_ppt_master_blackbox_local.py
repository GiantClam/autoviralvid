from __future__ import annotations

import json
from pathlib import Path

from src import ppt_master_blackbox_local as blackbox


def test_run_blackbox_request_skill_runtime(monkeypatch, tmp_path: Path) -> None:
    project_path = tmp_path / "proj"
    project_path.mkdir(parents=True, exist_ok=True)

    def _fake_load(self):  # noqa: ANN001
        return blackbox.SkillDefinition(
            name="ppt-master",
            description="skill",
            source_path="SKILL.md",
            workflow_steps=[blackbox.SkillStep(title="Step 1", blocking=False)],
            scripts={"project_manager.py": "init"},
        )

    registry = blackbox.SkillToolRegistry()

    def _project_init(**kwargs):  # noqa: ANN001
        _ = kwargs
        return project_path

    def _pipeline_run(**kwargs):  # noqa: ANN001
        _ = kwargs
        return {
            "run_id": "run_x",
            "stages": [],
            "artifacts": {"render_payload": {"theme": {"palette": "blue"}}},
            "export": {"output_pptx": str(project_path / "demo.pptx")},
        }

    def _materialize_design_spec(**kwargs):  # noqa: ANN001
        _ = kwargs
        target = project_path / "design_spec.json"
        target.write_text(json.dumps({"ok": True}), encoding="utf-8")
        return str(target)

    def _image_gen(**kwargs):  # noqa: ANN001
        _ = kwargs
        return {"status": "enabled", "reason": "ok"}

    registry.register("project.init", _project_init)
    registry.register("pipeline.run", _pipeline_run)
    registry.register("design_spec.materialize", _materialize_design_spec)
    registry.register("image.generate_cover", _image_gen)
    registry.register("web.search", lambda **kwargs: {"ok": True, "items": []})
    registry.register("web.fetch", lambda **kwargs: {"ok": True, "content": ""})

    monkeypatch.setattr(blackbox.PPTMasterSkillLoader, "load", _fake_load)
    monkeypatch.setattr(blackbox, "_build_tool_registry", lambda: registry)

    result = blackbox.run_blackbox_request(
        {
            "prompt": "请制作大学课堂课件，主题为霍尔木兹海峡危机",
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
    assert Path(result["artifacts"]["pipeline_result"]).exists()
    assert Path(result["artifacts"]["runtime_trace"]).exists()
    assert Path(result["artifacts"]["skill_manifest"]).exists()


def test_build_tool_registry_contains_skill_tools() -> None:
    registry = blackbox._build_tool_registry()
    tools = registry.list_tools()
    assert "project.init" in tools
    assert "pipeline.run" in tools
    assert "web.search" in tools
    assert "web.fetch" in tools
    assert "design_spec.materialize" in tools
    assert "image.generate_cover" in tools
