from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.ppt_subagent_executor import execute_subagent_task


def _sample_task(load_skills: list[str]) -> dict:
    return {
        "slide_id": "s-eq-1",
        "slide_type": "content",
        "agent_type": "content-page-generator",
        "render_path": "svg",
        "layout_grid": "",
        "load_skills": list(load_skills),
        "prompt": "Generate a high-quality enterprise slide.",
        "slide_data": {
            "slide_id": "s-eq-1",
            "title": "Architecture overview",
            "blocks": [{"block_type": "body", "content": "draft"}],
        },
    }


def _read_skill_markdown(skill_root: Path, skill_name: str) -> tuple[Path, str]:
    skill_file = skill_root / skill_name / "SKILL.md"
    if not skill_file.exists():
        raise AssertionError(f"skill markdown missing: {skill_file}")
    content = skill_file.read_text(encoding="utf-8", errors="ignore").strip()
    if not content:
        raise AssertionError(f"skill markdown empty: {skill_file}")
    return skill_file, content


def _build_expected_skill_block(skill_root: Path, skill_names: list[str]) -> str:
    sections: list[str] = []
    for skill in skill_names:
        skill_file, content = _read_skill_markdown(skill_root, skill)
        sections.append(f"## Skill: {skill}\nSource: {skill_file}\n\n{content}")
    return "\n\n---\n\n".join(sections)


def _extract_user_content(messages: list[dict]) -> str:
    user_messages = [row for row in messages if isinstance(row, dict) and str(row.get("role")) == "user"]
    if not user_messages:
        raise AssertionError("llm input missing user message")
    return str(user_messages[-1].get("content") or "")


def _extract_loaded_skill_block(user_content: str) -> str:
    start_tag = "Loaded skill specifications:\n\n"
    end_tag = "\n\nReturn JSON with keys:"
    if start_tag not in user_content:
        raise AssertionError("prompt missing loaded skill start tag")
    if end_tag not in user_content:
        raise AssertionError("prompt missing loaded skill end tag")
    block = user_content.split(start_tag, 1)[1].split(end_tag, 1)[0]
    return block.strip()


def _capture_prompt_block(
    monkeypatch: pytest.MonkeyPatch,
    *,
    skill_root: Path,
    skill_names: list[str],
) -> tuple[str, dict]:
    monkeypatch.setenv("PPT_SUBAGENT_ENABLE_SKILL_RUNTIME", "false")
    monkeypatch.setenv("CONTENT_LLM_MODEL", "openai/gpt-5.3-codex")
    monkeypatch.setenv("PPT_SUBAGENT_SKILL_CONTENT_MAX_CHARS", "500000")
    monkeypatch.setenv("PPT_SUBAGENT_SKILL_ROOTS", str(skill_root))

    captured: dict = {}

    def _fake_model(llm_input: dict) -> dict:
        captured["llm_input"] = llm_input
        return {"slide_patch": {"layout_grid": "split_2"}, "notes": "ok"}

    output = execute_subagent_task(_sample_task(skill_names), model_invoke=_fake_model)
    assert output.get("ok") is True

    llm_input = captured.get("llm_input")
    if not isinstance(llm_input, dict):
        raise AssertionError("llm input capture failed")
    messages = llm_input.get("messages")
    if not isinstance(messages, list):
        raise AssertionError("llm input missing messages")

    user_content = _extract_user_content(messages)
    loaded_block = _extract_loaded_skill_block(user_content)
    return loaded_block, llm_input


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
def test_skill_prompt_block_matches_direct_skill_markdown(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    skill_root: Path,
    skill_names: list[str],
):
    agent_root = Path(__file__).resolve().parents[1]
    resolved_root = (agent_root / skill_root).resolve()
    if not resolved_root.exists():
        raise AssertionError(f"{label} skill root missing: {resolved_root}")

    expected = _build_expected_skill_block(resolved_root, skill_names)
    actual, llm_input = _capture_prompt_block(
        monkeypatch,
        skill_root=resolved_root,
        skill_names=skill_names,
    )

    assert llm_input.get("model") == "openai/gpt-5.3-codex"
    assert actual == expected
    assert expected in actual


