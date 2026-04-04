from __future__ import annotations

import io
import json
import os
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
    assert out["patch"].get("template_family") in {
        "dashboard_dark",
        "split_media_dark",
        "consulting_warm_light",
        "comparison_cards_light",
    }
    assert out["patch"].get("palette_key")
    ctx = out.get("context")
    assert isinstance(ctx, dict)
    assert ctx.get("agent_type") == "content-page-generator"
    assert isinstance(ctx.get("template_candidates"), list)
    assert str(ctx.get("template_selection_mode") or "").strip()
    assert isinstance(ctx.get("recommended_load_skills"), list)
    assert "ppt-orchestra-skill" in set(ctx.get("recommended_load_skills") or [])


def test_execute_installed_skill_request_emits_theme_recipe_and_tone(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "version": 1,
        "requested_skills": ["design-style-skill"],
        "slide": {
            "slide_id": "s-theme",
            "slide_type": "content",
            "title": "课堂流程梳理",
        },
        "deck": {"title": "课堂流程梳理", "theme_recipe": "classroom_soft"},
    }
    out = exec_mod.execute_installed_skill_request(payload)
    patch = out.get("patch") if isinstance(out.get("patch"), dict) else {}
    ctx = out.get("context") if isinstance(out.get("context"), dict) else {}
    assert patch.get("theme_recipe") == "classroom_soft"
    assert patch.get("tone") == "light"
    assert ctx.get("theme_recipe") == "classroom_soft"
    assert ctx.get("tone") == "light"


def test_resolve_template_plan_is_independent_of_style_variant_for_same_layout():
    slide = {"slide_type": "content", "layout_grid": "split_2", "title": "Overview"}
    deck = {"title": "Deck"}
    sharp = exec_mod._resolve_template_plan("content", "sharp", slide, deck, preferred_tone="light")
    rounded = exec_mod._resolve_template_plan("content", "rounded", slide, deck, preferred_tone="light")
    assert sharp.get("selected") == rounded.get("selected")


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


def test_execute_installed_skill_request_honors_template_whitelist(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "requested_skills": ["design-style-skill"],
        "slide": {
            "slide_id": "s-whitelist",
            "slide_type": "content",
            "template_family": "dashboard_dark",
            "template_family_whitelist": ["split_media_dark", "consulting_warm_light"],
        },
        "deck": {"title": "Deck"},
    }
    out = exec_mod.execute_installed_skill_request(payload)
    patch = out.get("patch") if isinstance(out.get("patch"), dict) else {}
    assert patch.get("template_family") in {"split_media_dark", "consulting_warm_light"}


def test_execute_installed_skill_request_avoids_repeating_same_template_when_candidates_exist(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "requested_skills": ["design-style-skill", "ppt-orchestra-skill"],
        "slide": {
            "slide_id": "s-template-rotate",
            "slide_type": "content",
            "layout_grid": "split_2",
            "template_candidates": ["dashboard_dark", "split_media_dark"],
            "blocks": [{"block_type": "body", "content": "Execution overview"}],
        },
        "deck": {
            "title": "Deck",
            "content_slide_index": 3,
            "used_template_families": ["dashboard_dark", "dashboard_dark"],
        },
    }
    out = exec_mod.execute_installed_skill_request(payload)
    patch = out.get("patch") if isinstance(out.get("patch"), dict) else {}
    assert patch.get("template_family") == "split_media_dark"
    ctx = out.get("context") if isinstance(out.get("context"), dict) else {}
    assert "split_media_dark" in (ctx.get("template_candidates") or [])


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


def test_execute_installed_skill_request_prefers_project_venv_python_for_python_bin(monkeypatch, tmp_path):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "true")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_BIN", "python")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ARGS", json.dumps(["-m", "src.ppt_direct_skill_runtime"]))

    runtime_cwd = tmp_path / "runtime-cwd"
    if os.name == "nt":
        venv_python = runtime_cwd / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = runtime_cwd / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("", encoding="utf-8")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_CWD", str(runtime_cwd))

    def _fake_subprocess_run(cmd, input, capture_output, text, timeout, check, cwd, **kwargs):
        assert Path(cmd[0]).resolve() == venv_python.resolve()
        body = {
            "results": [
                {
                    "skill": "slide-making-skill",
                    "status": "applied",
                    "patch": {"layout_grid": "grid_3"},
                }
            ],
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(body), stderr="")

    monkeypatch.setattr(exec_mod.subprocess, "run", _fake_subprocess_run)

    out = exec_mod.execute_installed_skill_request(
        {
            "requested_skills": ["slide-making-skill"],
            "slide": {"slide_id": "s13b", "slide_type": "content"},
        }
    )
    assert out.get("patch", {}).get("layout_grid") == "grid_3"


def test_execute_installed_skill_request_ppt_master_strict_missing_spec_errors(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    monkeypatch.setattr("src.ppt_master_skill_adapter.resolve_ppt_master_skill_spec_path", lambda: "")
    payload = {
        "requested_skills": ["ppt-master"],
        "execution_profile": "dev_strict",
        "slide": {"slide_id": "s-pm", "slide_type": "content"},
    }
    out = exec_mod.execute_installed_skill_request(payload)
    results = out.get("results")
    assert isinstance(results, list) and len(results) == 1
    row = results[0]
    assert row.get("skill") == "ppt-master"
    assert row.get("status") == "error"
    assert str(row.get("note") or "").strip() == "ppt_master_skill_spec_missing"


def test_execute_installed_skill_request_ppt_master_uses_request_profile(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    payload = {
        "requested_skills": ["ppt-master"],
        "execution_profile": "dev_strict",
        "force_ppt_master": True,
        "slide": {"slide_id": "s-pm-ok", "slide_type": "content", "layout_grid": "timeline"},
    }
    out = exec_mod.execute_installed_skill_request(payload)
    results = out.get("results")
    assert isinstance(results, list) and len(results) == 1
    row = results[0]
    assert row.get("skill") == "ppt-master"
    assert row.get("status") in {"applied", "noop"}
    outputs = row.get("outputs") if isinstance(row.get("outputs"), dict) else {}
    adapter_info = outputs.get("ppt_master_adapter") if isinstance(outputs.get("ppt_master_adapter"), dict) else {}
    assert adapter_info.get("execution_profile") == "dev_strict"
    assert adapter_info.get("force_hit") is True


def test_execute_installed_skill_request_reports_policy_violation_for_unauthorized_field(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")

    def _fake_runtime(**_kwargs):
        return {
            "enabled": True,
            "reason": "",
            "parsed": {
                "results": [
                    {
                        "skill": "color-font-skill",
                        "status": "applied",
                        "patch": {"palette_key": "business_authority", "layout_grid": "grid_4"},
                        "outputs": {},
                    }
                ]
            },
        }

    monkeypatch.setattr(exec_mod, "_invoke_direct_skill_runtime", _fake_runtime)
    out = exec_mod.execute_installed_skill_request(
        {"requested_skills": ["color-font-skill"], "slide": {"slide_id": "s-pol-1", "slide_type": "content"}}
    )
    row = out["results"][0]
    assert row["status"] == "applied"
    assert row["patch"].get("palette_key") == "business_authority"
    assert "layout_grid" not in row["patch"]
    assert "skill_write_policy_violation:layout_grid" in str(row.get("note") or "")
    violations = out.get("skill_write_violations") if isinstance(out.get("skill_write_violations"), list) else []
    assert any(v.get("field") == "layout_grid" for v in violations if isinstance(v, dict))


def test_execute_installed_skill_request_reports_policy_conflict_and_keeps_first_writer(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")

    def _fake_runtime(**_kwargs):
        return {
            "enabled": True,
            "reason": "",
            "parsed": {
                "results": [
                    {
                        "skill": "slide-making-skill",
                        "status": "applied",
                        "patch": {"layout_grid": "grid_3"},
                        "outputs": {},
                    },
                    {
                        "skill": "ppt-orchestra-skill",
                        "status": "applied",
                        "patch": {"layout_grid": "timeline"},
                        "outputs": {},
                    },
                ]
            },
        }

    monkeypatch.setattr(exec_mod, "_invoke_direct_skill_runtime", _fake_runtime)
    out = exec_mod.execute_installed_skill_request(
        {
            "requested_skills": ["slide-making-skill", "ppt-orchestra-skill"],
            "slide": {"slide_id": "s-pol-2", "slide_type": "content"},
        }
    )
    assert out.get("patch", {}).get("layout_grid") == "grid_3"
    conflicts = out.get("skill_write_conflicts") if isinstance(out.get("skill_write_conflicts"), list) else []
    assert any(c.get("field") == "layout_grid" for c in conflicts if isinstance(c, dict))
    row2 = out["results"][1]
    assert "skill_write_conflict_dropped:layout_grid" in str(row2.get("note") or "")
    assert "layout_grid" not in row2.get("patch", {})


def test_execute_installed_skill_request_dev_strict_marks_violation_as_error(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")

    def _fake_runtime(**_kwargs):
        return {
            "enabled": True,
            "reason": "",
            "parsed": {
                "results": [
                    {
                        "skill": "design-style-skill",
                        "status": "applied",
                        "patch": {"palette_key": "pure_tech_blue"},
                        "outputs": {},
                    }
                ]
            },
        }

    monkeypatch.setattr(exec_mod, "_invoke_direct_skill_runtime", _fake_runtime)
    out = exec_mod.execute_installed_skill_request(
        {
            "requested_skills": ["design-style-skill"],
            "execution_profile": "dev_strict",
            "slide": {"slide_id": "s-pol-3", "slide_type": "content"},
        }
    )
    row = out["results"][0]
    assert row["status"] == "error"
    assert row.get("patch") == {}
    assert "skill_write_policy_violation:palette_key" in str(row.get("note") or "")


def test_execute_installed_skill_request_dev_strict_enforces_primary_visual_writer(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    monkeypatch.setenv("PPT_PRIMARY_VISUAL_SINGLE_WRITER", "true")
    monkeypatch.setenv("PPT_PRIMARY_VISUAL_SKILL", "ppt-orchestra-skill")

    def _fake_runtime(**_kwargs):
        return {
            "enabled": True,
            "reason": "",
            "parsed": {
                "results": [
                    {
                        "skill": "slide-making-skill",
                        "status": "applied",
                        "patch": {"layout_grid": "grid_4", "render_path": "svg"},
                        "outputs": {},
                    }
                ]
            },
        }

    monkeypatch.setattr(exec_mod, "_invoke_direct_skill_runtime", _fake_runtime)
    out = exec_mod.execute_installed_skill_request(
        {
            "requested_skills": ["slide-making-skill"],
            "execution_profile": "dev_strict",
            "slide": {"slide_id": "s-pol-4", "slide_type": "content"},
        }
    )
    row = out["results"][0]
    assert row["status"] == "error"
    assert row.get("patch") == {}
    assert "skill_write_policy_violation:layout_grid" in str(row.get("note") or "")
    violations = out.get("skill_write_violations") if isinstance(out.get("skill_write_violations"), list) else []
    assert any(v.get("reason") == "primary_visual_writer_only" for v in violations if isinstance(v, dict))


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
