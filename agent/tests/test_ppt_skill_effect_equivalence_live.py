from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from src.ppt_subagent_executor import (
    _build_page_guidance_text,
    _build_llm_input,
    _create_openai_client,
    _dedupe_skills,
    _parse_json_object,
    _sanitize_patch,
    execute_subagent_task,
)


def _sample_task(load_skills: List[str]) -> Dict[str, Any]:
    return {
        "slide_id": "s-live-1",
        "slide_type": "content",
        "agent_type": "content-page-generator",
        "render_path": "svg",
        "layout_grid": "split_2",
        "load_skills": list(load_skills),
        "prompt": "Refine this slide for executive audience.",
        "slide_data": {
            "slide_id": "s-live-1",
            "title": "Business architecture",
            "blocks": [{"block_type": "body", "content": "draft"}],
        },
    }


def _read_skill(skill_root: Path, skill_name: str) -> Tuple[Path, str]:
    skill_file = skill_root / skill_name / "SKILL.md"
    if not skill_file.exists():
        raise AssertionError(f"skill markdown missing: {skill_file}")
    content = skill_file.read_text(encoding="utf-8", errors="ignore").strip()
    if not content:
        raise AssertionError(f"skill markdown empty: {skill_file}")
    return skill_file, content


def _build_direct_skill_content(skill_root: Path, skill_names: List[str]) -> str:
    sections: List[str] = []
    for skill in skill_names:
        skill_file, content = _read_skill(skill_root, skill)
        sections.append(f"## Skill: {skill}\nSource: {skill_file}\n\n{content}")
    return "\n\n---\n\n".join(sections)


def _capture_project_llm_input(
    monkeypatch: pytest.MonkeyPatch,
    *,
    skill_root: Path,
    skill_names: List[str],
) -> Dict[str, Any]:
    monkeypatch.setenv("PPT_SUBAGENT_ENABLE_SKILL_RUNTIME", "false")
    if not str(os.getenv("CONTENT_LLM_MODEL", "")).strip():
        monkeypatch.setenv("CONTENT_LLM_MODEL", "openai/gpt-5.3-codex")
    monkeypatch.setenv("PPT_SUBAGENT_SKILL_CONTENT_MAX_CHARS", "500000")
    monkeypatch.setenv("PPT_SUBAGENT_SKILL_ROOTS", str(skill_root))

    captured: Dict[str, Any] = {}

    def _fake_model(llm_input: Dict[str, Any]) -> Dict[str, Any]:
        captured["llm_input"] = llm_input
        return {"slide_patch": {"layout_grid": "split_2"}, "notes": "ok"}

    out = execute_subagent_task(_sample_task(skill_names), model_invoke=_fake_model)
    assert out.get("ok") is True
    llm_input = captured.get("llm_input")
    if not isinstance(llm_input, dict):
        raise AssertionError("failed to capture llm input")
    return llm_input


def _build_direct_llm_input(project_llm_input: Dict[str, Any], skill_content: str, skill_names: List[str]) -> Dict[str, Any]:
    payload = project_llm_input.get("task_payload")
    if not isinstance(payload, dict):
        raise AssertionError("project llm input missing task_payload")
    prompt = str(_sample_task(skill_names).get("prompt"))
    hints = [f"load_skill:{item}" for item in _dedupe_skills(skill_names)]
    if hints:
        hints.append("loaded_skill_specs:" + ",".join(_dedupe_skills(skill_names)))
    page_guidance = _build_page_guidance_text(payload)
    return _build_llm_input(payload, prompt, hints, skill_content, page_guidance)


def _invoke_live_json(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    client, model, _provider = _create_openai_client()
    if client is None:
        pytest.skip(
            "live equivalence requires AIBERM_API_BASE+AIBERM_API_KEY, "
            "or CRAZYROUTE_API_BASE+CRAZYROUTE_API_KEY, "
            "or OPENROUTER_API_KEY, or OPENAI_API_KEY"
        )
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    choices = getattr(response, "choices", None) or []
    content = ""
    if choices:
        content = str(getattr(choices[0].message, "content", "") or "")
    parsed = _parse_json_object(content)
    if not parsed:
        pytest.skip("live model did not return valid JSON object for this case")
    return parsed


def _normalize_effect(result: Dict[str, Any]) -> Dict[str, Any]:
    patch = _sanitize_patch(result.get("slide_patch"))
    focus_keys = ("slide_type", "layout_grid", "render_path", "template_family", "skill_profile")
    focused_patch = {key: patch.get(key) for key in focus_keys if key in patch}
    return {
        "patch": focused_patch,
        "load_skills": _dedupe_skills(result.get("load_skills")),
    }


def _live_enabled() -> bool:
    return str(os.getenv("PPT_SKILL_EQ_LIVE", "0")).strip().lower() in {"1", "true", "yes", "on"}


@pytest.mark.parametrize(
    ("label", "skill_root", "skill_names"),
    [
        (
            "anthropic_pptx",
            Path("tests/fixtures/skills_reference/anthropic/skills"),
            ["pptx"],
        ),
        (
            "minimax_pptx_generator",
            Path("../vendor/minimax-skills/skills"),
            ["pptx-generator"],
        ),
        (
            "minimax_pptx_plugin",
            Path("../vendor/minimax-skills/plugins/pptx-plugin/skills"),
            [
                "ppt-orchestra-skill",
                "slide-making-skill",
                "design-style-skill",
                "color-font-skill",
                "ppt-editing-skill",
            ],
        ),
        (
            "ppt_master",
            Path("tests/fixtures/skills_reference/ppt-master/skills"),
            ["ppt-master"],
        ),
    ],
)
def test_project_and_direct_skill_loading_build_identical_messages(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    skill_root: Path,
    skill_names: List[str],
):
    agent_root = Path(__file__).resolve().parents[1]
    resolved_root = (agent_root / skill_root).resolve()
    if not resolved_root.exists():
        raise AssertionError(f"{label} skill root missing: {resolved_root}")

    project_llm_input = _capture_project_llm_input(
        monkeypatch,
        skill_root=resolved_root,
        skill_names=skill_names,
    )
    direct_skill_content = _build_direct_skill_content(resolved_root, skill_names)
    direct_llm_input = _build_direct_llm_input(project_llm_input, direct_skill_content, skill_names)

    expected_model = str(os.getenv("CONTENT_LLM_MODEL", "")).strip() or "openai/gpt-5.3-codex"
    assert project_llm_input.get("model") == expected_model
    assert direct_llm_input.get("model") == expected_model
    assert project_llm_input.get("messages") == direct_llm_input.get("messages")
    assert project_llm_input.get("task_payload") == direct_llm_input.get("task_payload")


@pytest.mark.parametrize(
    ("label", "skill_root", "skill_names"),
    [
        ("anthropic_pptx", Path("tests/fixtures/skills_reference/anthropic/skills"), ["pptx"]),
        ("minimax_pptx_generator", Path("../vendor/minimax-skills/skills"), ["pptx-generator"]),
        (
            "minimax_pptx_plugin",
            Path("../vendor/minimax-skills/plugins/pptx-plugin/skills"),
            ["ppt-orchestra-skill", "slide-making-skill", "design-style-skill", "color-font-skill", "ppt-editing-skill"],
        ),
        ("ppt_master", Path("tests/fixtures/skills_reference/ppt-master/skills"), ["ppt-master"]),
    ],
)
def test_live_model_effect_consistent_between_project_and_direct_skill_loading(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    skill_root: Path,
    skill_names: List[str],
):
    if not _live_enabled():
        pytest.skip("set PPT_SKILL_EQ_LIVE=1 to run live model equivalence checks")

    agent_root = Path(__file__).resolve().parents[1]
    resolved_root = (agent_root / skill_root).resolve()
    if not resolved_root.exists():
        raise AssertionError(f"{label} skill root missing: {resolved_root}")

    project_llm_input = _capture_project_llm_input(
        monkeypatch,
        skill_root=resolved_root,
        skill_names=skill_names,
    )
    direct_skill_content = _build_direct_skill_content(resolved_root, skill_names)
    direct_llm_input = _build_direct_llm_input(project_llm_input, direct_skill_content, skill_names)

    project_messages = copy.deepcopy(project_llm_input.get("messages") or [])
    direct_messages = copy.deepcopy(direct_llm_input.get("messages") or [])
    if not isinstance(project_messages, list) or not isinstance(direct_messages, list):
        raise AssertionError("invalid messages in llm input")

    # 先保证“项目路径”和“直接加载 skill 路径”输入完全一致。
    assert project_messages == direct_messages
    # 在一致输入上做一次真实模型调用 smoke，验证当前环境可运行。
    live_result = _invoke_live_json(project_messages)
    normalized = _normalize_effect(live_result)
    assert isinstance(normalized.get("patch"), dict)
    assert isinstance(normalized.get("load_skills"), list)
