from __future__ import annotations

import json
import subprocess

from src.ppt_subagent_executor import (
    _build_llm_input,
    _create_openai_client,
    _load_skill_content,
    execute_subagent_task,
)


def _sample_task() -> dict:
    return {
        "slide_id": "s2",
        "slide_type": "content",
        "agent_type": "content-page-generator",
        "render_path": "svg",
        "layout_grid": "",
        "load_skills": ["slide-making-skill", "design-style-skill"],
        "prompt": "Refine this slide for clarity.",
        "slide_data": {
            "slide_id": "s2",
            "title": "Current state",
            "blocks": [{"block_type": "body", "content": "draft"}],
        },
    }


def test_subagent_executor_applies_llm_patch_and_merges_skills(monkeypatch):
    monkeypatch.setenv("PPT_SUBAGENT_ENABLE_SKILL_RUNTIME", "false")

    def _fake_model(llm_input: dict) -> dict:
        assert llm_input["task_payload"]["slide_id"] == "s2"
        return {
            "slide_patch": {
                "title": "Optimized state",
                "layout_grid": "timeline",
                "render_path": "svg",
            },
            "load_skills": ["pptx", "design-style-skill"],
            "notes": "Adjusted for visual hierarchy.",
        }

    output = execute_subagent_task(_sample_task(), model_invoke=_fake_model)

    assert output["ok"] is True
    assert output["skipped"] is False
    assert "title" not in output["slide_patch"]
    assert output["slide_patch"]["layout_grid"] == "timeline"
    assert output["slide_patch"]["render_path"] == "svg"
    assert set(output["load_skills"]) >= {"slide-making-skill", "design-style-skill", "pptx"}
    assert output["notes"] == "Adjusted for visual hierarchy."


def test_subagent_executor_skips_when_no_model_credentials(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PPT_SUBAGENT_ENABLE_SKILL_RUNTIME", "false")

    output = execute_subagent_task(_sample_task())

    assert output["ok"] is True
    assert output["skipped"] is True
    assert output["reason"] == "llm_credentials_missing"
    assert output["slide_patch"]["layout_grid"] == "split_2"
    skill_runtime = output.get("skill_runtime") if isinstance(output.get("skill_runtime"), dict) else {}
    assert skill_runtime.get("enabled") is False
    trace = skill_runtime.get("trace") if isinstance(skill_runtime.get("trace"), list) else []
    assert trace == []


def test_subagent_executor_uses_installed_skill_executor_chain(monkeypatch):
    monkeypatch.setenv("PPT_INSTALLED_SKILL_EXECUTOR_ENABLED", "true")
    monkeypatch.setenv("PPT_INSTALLED_SKILL_EXECUTOR_BIN", "fake-skill-runner")
    monkeypatch.setenv("PPT_INSTALLED_SKILL_EXECUTOR_ARGS", json.dumps(["run", "--json"]))

    def _fake_subprocess_run(cmd, input, capture_output, text, timeout, check, cwd, **kwargs):
        assert cmd[0] == "fake-skill-runner"
        assert str(cwd or "").strip().lower().endswith("agent")
        payload = json.loads(str(input or "{}"))
        assert payload.get("requested_skills") == ["slide-making-skill", "design-style-skill"]
        body = {
            "results": [
                {
                    "skill": "slide-making-skill",
                    "status": "applied",
                    "patch": {"layout_grid": "timeline", "render_path": "svg"},
                    "note": "installed skill applied",
                },
                {
                    "skill": "design-style-skill",
                    "status": "applied",
                    "patch": {"template_family": "architecture_dark_panel"},
                },
            ]
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(body), stderr="")

    monkeypatch.setattr("src.ppt_subagent_executor.subprocess.run", _fake_subprocess_run)

    output = execute_subagent_task(
        _sample_task(),
        model_invoke=lambda _llm_input: {"skipped": True, "reason": "llm_credentials_missing"},
    )

    assert output["ok"] is True
    assert output["slide_patch"]["layout_grid"] == "timeline"
    assert output["slide_patch"]["render_path"] == "svg"
    assert output["slide_patch"]["template_family"] == "architecture_dark_panel"
    skill_runtime = output.get("skill_runtime") if isinstance(output.get("skill_runtime"), dict) else {}
    trace = skill_runtime.get("trace") if isinstance(skill_runtime.get("trace"), list) else []
    assert any(
        item.get("source") == "installed_skill_executor" and item.get("skill") == "slide-making-skill"
        for item in trace
        if isinstance(item, dict)
    )


def test_subagent_executor_uses_default_installed_executor_on_worker(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("PPT_EXECUTION_ROLE", "worker")
    monkeypatch.delenv("PPT_INSTALLED_SKILL_EXECUTOR_ENABLED", raising=False)
    monkeypatch.delenv("PPT_INSTALLED_SKILL_EXECUTOR_BIN", raising=False)
    monkeypatch.delenv("PPT_INSTALLED_SKILL_EXECUTOR_ARGS", raising=False)

    def _fake_subprocess_run(cmd, input, capture_output, text, timeout, check, cwd, **kwargs):
        assert cmd[0] == "uv"
        assert cmd[1:] == ["run", "python", "-m", "src.installed_skill_executor"]
        assert str(cwd or "").strip().lower().endswith("agent")
        payload = json.loads(str(input or "{}"))
        assert payload.get("requested_skills") == ["slide-making-skill", "design-style-skill"]
        body = {
            "results": [
                {"skill": "slide-making-skill", "status": "applied", "patch": {"layout_grid": "split_2"}},
                {"skill": "design-style-skill", "status": "noop", "patch": {}},
            ]
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(body), stderr="")

    monkeypatch.setattr("src.ppt_subagent_executor.subprocess.run", _fake_subprocess_run)

    output = execute_subagent_task(
        _sample_task(),
        model_invoke=lambda _llm_input: {"skipped": True, "reason": "llm_credentials_missing"},
    )

    assert output["ok"] is True
    assert output["slide_patch"]["layout_grid"] == "split_2"


def test_subagent_executor_uses_installed_executor_by_default_on_web_role(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("PPT_EXECUTION_ROLE", raising=False)
    monkeypatch.delenv("PPT_INSTALLED_SKILL_EXECUTOR_ENABLED", raising=False)
    monkeypatch.delenv("PPT_INSTALLED_SKILL_EXECUTOR_BIN", raising=False)
    monkeypatch.delenv("PPT_INSTALLED_SKILL_EXECUTOR_ARGS", raising=False)

    called = {"value": False}

    def _fake_subprocess_run(cmd, input, capture_output, text, timeout, check, cwd, **kwargs):
        called["value"] = True
        payload = json.loads(str(input or "{}"))
        assert payload.get("requested_skills") == ["slide-making-skill", "design-style-skill"]
        body = {
            "results": [
                {"skill": "slide-making-skill", "status": "applied", "patch": {"layout_grid": "split_2"}},
                {"skill": "design-style-skill", "status": "noop", "patch": {}},
            ]
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(body), stderr="")

    monkeypatch.setattr("src.ppt_subagent_executor.subprocess.run", _fake_subprocess_run)

    output = execute_subagent_task(
        _sample_task(),
        model_invoke=lambda _llm_input: {"skipped": True, "reason": "llm_credentials_missing"},
    )

    assert output["ok"] is True
    assert output["slide_patch"]["layout_grid"] == "split_2"
    assert called["value"] is True


def test_subagent_executor_loads_skill_markdown_into_prompt(monkeypatch):
    monkeypatch.setenv("PPT_SUBAGENT_ENABLE_SKILL_RUNTIME", "false")
    captured = {"content": ""}
    task = _sample_task()
    task["load_skills"] = ["slide-making-skill", "ppt-orchestra-skill"]
    task["skill_directives"] = ["Only one title area is allowed at the top of the slide."]
    task["text_constraints"] = {"bullet_max_items": 4}

    def _fake_model(llm_input: dict) -> dict:
        messages = llm_input.get("messages") if isinstance(llm_input.get("messages"), list) else []
        text = "\n".join(str(row.get("content") or "") for row in messages if isinstance(row, dict))
        captured["content"] = text
        return {"slide_patch": {"layout_grid": "split_2"}, "notes": "ok"}

    output = execute_subagent_task(task, model_invoke=_fake_model)

    assert output["ok"] is True
    assert "Loaded skill specifications" in captured["content"]
    assert "Page-specific guidance" in captured["content"]
    assert "Only one title area is allowed at the top of the slide." in captured["content"]
    assert "SVG-to-PPTX Slide Making Skill" in captured["content"]
    assert "Slide Page Types (Standard)" in captured["content"]


def test_subagent_executor_filters_mojibake_text_patch_fields(monkeypatch):
    monkeypatch.setenv("PPT_SUBAGENT_ENABLE_SKILL_RUNTIME", "false")

    def _fake_model(_llm_input: dict) -> dict:
        return {
            "slide_patch": {
                "title": "锟斤拷锟侥诧拷品锟斤拷锟斤拷",
                "layout_grid": "timeline",
                "elements": [{"type": "text", "content": "锟斤拷锟斤拷锟斤拷"}],
            }
        }

    output = execute_subagent_task(_sample_task(), model_invoke=_fake_model)
    slide_patch = output.get("slide_patch") if isinstance(output.get("slide_patch"), dict) else {}
    assert slide_patch.get("layout_grid") == "timeline"
    assert "title" not in slide_patch
    assert "elements" not in slide_patch


def test_subagent_executor_drops_invalid_blocks_patch(monkeypatch):
    monkeypatch.setenv("PPT_SUBAGENT_ENABLE_SKILL_RUNTIME", "false")

    def _fake_model(_llm_input: dict) -> dict:
        return {
            "slide_patch": {
                "layout_grid": "split_2",
                "blocks": [
                    {"block_type": "text", "card_id": "c1", "content": ""},
                    {"block_type": "image", "card_id": "c2", "content": None},
                ],
            }
        }

    output = execute_subagent_task(_sample_task(), model_invoke=_fake_model)
    slide_patch = output.get("slide_patch") if isinstance(output.get("slide_patch"), dict) else {}
    assert slide_patch.get("layout_grid") == "split_2"
    assert "blocks" not in slide_patch


def test_load_skill_content_supports_alias_pptx():
    doc = _load_skill_content("pptx")
    assert isinstance(doc, dict)
    assert doc.get("found") is True
    assert "pptx-generator" in str(doc.get("path") or "").lower()


def test_create_openai_client_prefers_aiberm_over_openrouter(monkeypatch):
    monkeypatch.setenv("CONTENT_LLM_MODEL", "openai/gpt-5.3-codex")
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")

    client, model, provider = _create_openai_client()

    assert client is not None
    assert model == "openai/gpt-5.3-codex"
    assert provider == "aiberm"
    assert "aiberm.example" in str(getattr(client, "base_url", ""))


def test_subagent_executor_handles_none_load_skills(monkeypatch):
    monkeypatch.setenv("PPT_SUBAGENT_ENABLE_SKILL_RUNTIME", "false")
    task = _sample_task()
    task["load_skills"] = None

    output = execute_subagent_task(
        task,
        model_invoke=lambda _llm_input: {"slide_patch": {"layout_grid": "timeline"}, "load_skills": ["pptx"]},
    )

    assert output["ok"] is True
    assert output["slide_patch"]["layout_grid"] == "timeline"
    assert "pptx" in output["load_skills"]


def test_build_llm_input_strips_surrogate_characters():
    bad = f"prefix{chr(0xDC80)}suffix"
    payload = {"slide_id": "s1", "load_skills": ["pptx"]}
    llm_input = _build_llm_input(
        payload,
        f"Prompt {bad}",
        [bad],
        f"Skill {bad}",
        f"Guidance {bad}",
    )
    messages = llm_input.get("messages")
    assert isinstance(messages, list)
    text = "\n".join(str(item.get("content") or "") for item in messages if isinstance(item, dict))
    assert chr(0xDC80) not in text

