from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

from src import installed_skill_executor as exec_mod


def test_execute_installed_skill_request_returns_results_for_all_requested_skills(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "version": 1,
        "requested_skills": ["slide-making-skill", "design-style-skill", "color-font-skill", "pptx"],
        "slide": {
            "slide_id": "s1",
            "slide_type": "content",
            "slide_data": {"title": "Example"},
        },
    }

    out = exec_mod.execute_installed_skill_request(payload)
    assert isinstance(out, dict)
    assert out.get("version") == 1
    results = out.get("results")
    assert isinstance(results, list)
    assert len(results) == 4
    by_skill = {str(item.get("skill")): item for item in results if isinstance(item, dict)}
    assert set(by_skill.keys()) == {
        "slide-making-skill",
        "design-style-skill",
        "color-font-skill",
        "pptx",
    }
    assert by_skill["slide-making-skill"]["status"] == "applied"
    assert by_skill["design-style-skill"]["status"] == "applied"
    assert by_skill["color-font-skill"]["status"] == "applied"
    assert by_skill["pptx"]["status"] == "applied"
    assert isinstance(out.get("patch"), dict)
    assert out["patch"].get("layout_grid") == "split_2"
    assert out["patch"].get("template_family") == "dashboard_dark"
    assert out["patch"].get("palette_key")
    ctx = out.get("context")
    assert isinstance(ctx, dict)
    assert ctx.get("agent_type") == "content-page-generator"
    assert isinstance(ctx.get("recommended_load_skills"), list)
    assert "ppt-orchestra-skill" in set(ctx.get("recommended_load_skills") or [])


def test_execute_installed_skill_request_unknown_skill_is_noop(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "requested_skills": ["unknown-skill"],
        "slide": {"slide_id": "s2", "slide_type": "content"},
    }
    out = exec_mod.execute_installed_skill_request(payload)
    results = out.get("results")
    assert isinstance(results, list)
    assert len(results) == 1
    row = results[0]
    assert row["skill"] == "unknown-skill"
    assert row["status"] == "noop"
    assert row["note"] == "unknown_skill_passthrough"


def test_execute_installed_skill_request_supports_ppt_editing_skill(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "version": 1,
        "requested_skills": ["ppt-editing-skill"],
        "slide": {
            "slide_id": "s10",
            "slide_type": "content",
            "template_family": "dashboard_dark",
        },
        "deck": {"title": "Template Deck", "template_family": "dashboard_dark"},
    }

    out = exec_mod.execute_installed_skill_request(payload)
    results = out.get("results")
    assert isinstance(results, list) and len(results) == 1
    row = results[0]
    assert row["skill"] == "ppt-editing-skill"
    assert row["status"] == "applied"
    outputs = row.get("outputs") if isinstance(row.get("outputs"), dict) else {}
    assert outputs.get("template_edit_pipeline") == "unpack->xml-edit->clean->pack"
    patch = out.get("patch") if isinstance(out.get("patch"), dict) else {}
    assert patch.get("skill_profile") == "template-edit"


def test_execute_installed_skill_request_emits_page_skill_directives(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "requested_skills": ["slide-making-skill", "ppt-orchestra-skill"],
        "slide": {"slide_id": "s-page", "slide_type": "content", "title": "Strategy"},
        "deck": {"title": "Deck"},
    }
    out = exec_mod.execute_installed_skill_request(payload)
    ctx = out.get("context") if isinstance(out.get("context"), dict) else {}
    directives = ctx.get("page_skill_directives")
    assert isinstance(directives, list) and len(directives) > 0
    assert isinstance(ctx.get("text_constraints"), dict)
    assert isinstance(ctx.get("image_policy"), dict)


def test_execute_installed_skill_request_rotates_content_layout_with_history(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "requested_skills": ["slide-making-skill", "ppt-orchestra-skill"],
        "slide": {"slide_id": "s-layout", "slide_type": "content", "title": "Execution Plan"},
        "deck": {
            "title": "Deck",
            "content_slide_index": 4,
            "used_content_layouts": ["split_2", "split_2", "grid_3", "split_2"],
        },
    }
    out = exec_mod.execute_installed_skill_request(payload)
    patch = out.get("patch") if isinstance(out.get("patch"), dict) else {}
    assert patch.get("layout_grid") in {"grid_3", "grid_4", "asymmetric_2", "timeline"}
    assert patch.get("layout_grid") != "split_2"
    ctx = out.get("context") if isinstance(out.get("context"), dict) else {}
    assert isinstance(ctx.get("text_constraints"), dict)


def test_execute_installed_skill_request_cover_prefers_hero_template(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "requested_skills": ["design-style-skill"],
        "slide": {"slide_id": "s-cover", "slide_type": "cover", "template_family": "dashboard_dark"},
        "deck": {"title": "Deck", "template_family": "dashboard_dark"},
    }
    out = exec_mod.execute_installed_skill_request(payload)
    patch = out.get("patch") if isinstance(out.get("patch"), dict) else {}
    assert patch.get("template_family") in {"hero_dark", "hero_tech_cover"}


def test_execute_installed_skill_request_uses_direct_runtime_when_configured(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_BIN", "fake-runtime")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ARGS", json.dumps(["run", "--json"]))

    def _fake_subprocess_run(cmd, input, capture_output, text, timeout, check, cwd, **kwargs):
        assert cmd[0] == "fake-runtime"
        req = json.loads(str(input or "{}"))
        assert req.get("requested_skills") == ["slide-making-skill"]
        body = {
            "results": [
                {
                    "skill": "slide-making-skill",
                    "status": "applied",
                    "patch": {"layout_grid": "timeline", "render_path": "svg"},
                    "outputs": {"note": "runtime"},
                }
            ],
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(body), stderr="")

    monkeypatch.setattr(exec_mod.subprocess, "run", _fake_subprocess_run)
    payload = {
        "requested_skills": ["slide-making-skill"],
        "slide": {"slide_id": "s11", "slide_type": "content"},
    }
    out = exec_mod.execute_installed_skill_request(payload)
    results = out.get("results")
    assert isinstance(results, list) and len(results) == 1
    row = results[0]
    assert row["status"] == "applied"
    assert row.get("source") == "direct_skill_runtime"
    assert out.get("patch", {}).get("layout_grid") == "timeline"


def test_execute_installed_skill_request_uses_default_direct_runtime_when_bin_missing(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "true")
    monkeypatch.delenv("PPT_DIRECT_SKILL_RUNTIME_BIN", raising=False)
    monkeypatch.delenv("PPT_DIRECT_SKILL_RUNTIME_ARGS", raising=False)
    monkeypatch.delenv("PPT_DIRECT_SKILL_RUNTIME_CWD", raising=False)

    def _fake_subprocess_run(cmd, input, capture_output, text, timeout, check, cwd, **kwargs):
        assert cmd[0] == "uv"
        assert cmd[1:] == ["run", "python", "-m", "src.ppt_direct_skill_runtime"]
        assert str(cwd or "").strip().lower().endswith("agent")
        req = json.loads(str(input or "{}"))
        assert req.get("requested_skills") == ["slide-making-skill"]
        body = {
            "results": [
                {
                    "skill": "slide-making-skill",
                    "status": "applied",
                    "patch": {"layout_grid": "split_2"},
                }
            ],
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(body), stderr="")

    monkeypatch.setattr(exec_mod.subprocess, "run", _fake_subprocess_run)

    payload = {
        "requested_skills": ["slide-making-skill"],
        "slide": {"slide_id": "s12", "slide_type": "content"},
    }
    out = exec_mod.execute_installed_skill_request(payload)
    row = out["results"][0]
    assert row["status"] == "applied"
    assert row.get("source") == "direct_skill_runtime"


def test_execute_installed_skill_request_with_local_direct_runtime_module(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "true")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_BIN", sys.executable)
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ARGS", json.dumps(["-m", "src.ppt_direct_skill_runtime"]))
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_CWD", str(Path(__file__).resolve().parents[1]))

    payload = {
        "requested_skills": ["slide-making-skill", "design-style-skill"],
        "slide": {"slide_id": "s13", "slide_type": "content", "title": "Architecture Review"},
        "deck": {"title": "Deck", "topic": "Deck", "total_slides": 8},
    }
    out = exec_mod.execute_installed_skill_request(payload)
    results = out.get("results")
    assert isinstance(results, list) and len(results) >= 2
    by_skill = {str(row.get("skill")): row for row in results if isinstance(row, dict)}
    assert by_skill["slide-making-skill"]["source"] == "direct_skill_runtime"
    assert by_skill["design-style-skill"]["source"] == "direct_skill_runtime"
    assert by_skill["slide-making-skill"]["status"] in {"applied", "noop"}
    assert by_skill["design-style-skill"]["status"] in {"applied", "noop"}


def test_main_reads_stdin_and_writes_json(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "requested_skills": ["slide-making-skill"],
        "slide": {"slide_id": "s3", "slide_type": "workflow", "slide_data": {}},
    }
    stdin = io.StringIO(json.dumps(payload, ensure_ascii=False))
    stdout = io.StringIO()
    monkeypatch.setattr(exec_mod.sys, "stdin", stdin)
    monkeypatch.setattr(exec_mod.sys, "stdout", stdout)

    code = exec_mod.main()
    assert code == 0
    parsed = json.loads(stdout.getvalue())
    assert parsed["version"] == 1
    assert isinstance(parsed.get("results"), list)
    assert parsed["results"][0]["skill"] == "slide-making-skill"
    assert parsed["results"][0]["status"] == "applied"
