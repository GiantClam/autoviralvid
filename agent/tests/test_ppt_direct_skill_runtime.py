from __future__ import annotations

import io
import json

from src import ppt_direct_skill_runtime as runtime_mod


def test_execute_direct_skill_runtime_resolves_requested_skills():
    payload = {
        "version": 1,
        "requested_skills": [
            "ppt-orchestra-skill",
            "slide-making-skill",
            "design-style-skill",
            "color-font-skill",
            "pptx",
            "ppt-editing-skill",
        ],
        "slide": {
            "slide_id": "s1",
            "slide_type": "content",
            "title": "Workflow Overview",
            "blocks": [{"block_type": "workflow", "content": "step1 -> step2"}],
        },
        "deck": {
            "title": "Demo Deck",
            "topic": "Demo Deck",
            "total_slides": 8,
            "template_family": "dashboard_dark",
        },
    }
    out = runtime_mod.execute_direct_skill_runtime(payload)
    assert out.get("version") == 1
    results = out.get("results")
    assert isinstance(results, list)
    assert len(results) == 6
    statuses = {str(row.get("skill")): str(row.get("status")) for row in results if isinstance(row, dict)}
    assert statuses.get("ppt-orchestra-skill") in {"applied", "noop"}
    assert statuses.get("slide-making-skill") in {"applied", "noop"}
    assert statuses.get("design-style-skill") in {"applied", "noop"}
    assert statuses.get("color-font-skill") in {"applied", "noop"}
    assert statuses.get("pptx") in {"applied", "noop"}
    assert statuses.get("ppt-editing-skill") in {"applied", "noop"}
    patch = out.get("patch") if isinstance(out.get("patch"), dict) else {}
    assert patch.get("agent_type")
    assert patch.get("template_family")
    context = out.get("context") if isinstance(out.get("context"), dict) else {}
    assert isinstance(context.get("recommended_load_skills"), list)
    assert "slide-making-skill" in (context.get("recommended_load_skills") or [])


def test_execute_direct_skill_runtime_handles_unknown_skill_as_noop():
    out = runtime_mod.execute_direct_skill_runtime(
        {"requested_skills": ["unknown-skill"], "slide": {"slide_id": "s2"}, "deck": {"title": "X"}}
    )
    results = out.get("results")
    assert isinstance(results, list) and len(results) == 1
    assert results[0].get("skill") == "unknown-skill"
    assert results[0].get("status") == "noop"


def test_execute_direct_skill_runtime_cover_prefers_hero_template_when_generic_input():
    payload = {
        "requested_skills": ["design-style-skill", "ppt-orchestra-skill"],
        "slide": {
            "slide_id": "cover-1",
            "slide_type": "cover",
            "template_family": "dashboard_dark",
            "title": "Deck Cover",
        },
        "deck": {"title": "Demo", "template_family": "dashboard_dark"},
    }
    out = runtime_mod.execute_direct_skill_runtime(payload)
    patch = out.get("patch") if isinstance(out.get("patch"), dict) else {}
    assert patch.get("template_family") in {"hero_dark", "hero_tech_cover"}
    context = out.get("context") if isinstance(out.get("context"), dict) else {}
    directives = context.get("page_skill_directives")
    assert isinstance(directives, list) and len(directives) > 0


def test_execute_direct_skill_runtime_rotates_content_layout_with_history():
    payload = {
        "requested_skills": ["slide-making-skill", "ppt-orchestra-skill"],
        "slide": {
            "slide_id": "s-layout",
            "slide_type": "content",
            "title": "Execution Plan",
        },
        "deck": {
            "title": "Demo Deck",
            "total_slides": 12,
            "content_slide_index": 4,
            "used_content_layouts": ["split_2", "split_2", "grid_3", "split_2"],
        },
    }
    out = runtime_mod.execute_direct_skill_runtime(payload)
    patch = out.get("patch") if isinstance(out.get("patch"), dict) else {}
    assert patch.get("layout_grid") in {"grid_3", "grid_4", "asymmetric_2", "timeline"}
    assert patch.get("layout_grid") != "split_2"
    context = out.get("context") if isinstance(out.get("context"), dict) else {}
    assert isinstance(context.get("text_constraints"), dict)
    assert isinstance(context.get("image_policy"), dict)


def test_main_reads_stdin_and_writes_json(monkeypatch):
    stdin = io.StringIO(json.dumps({"requested_skills": ["slide-making-skill"], "slide": {"slide_id": "s3"}}))
    stdout = io.StringIO()
    monkeypatch.setattr(runtime_mod.sys, "stdin", stdin)
    monkeypatch.setattr(runtime_mod.sys, "stdout", stdout)
    code = runtime_mod.main()
    assert code == 0
    parsed = json.loads(stdout.getvalue())
    assert parsed.get("version") == 1
    assert isinstance(parsed.get("results"), list)
    assert parsed["results"][0]["skill"] == "slide-making-skill"
