import json
import subprocess
from pathlib import Path

from src.minimax_exporter import export_minimax_pptx


def _sample_slide() -> dict:
    return {
        "slide_id": "s1",
        "title": "Intro",
        "slide_type": "content",
        "layout_grid": "split_2",
        "elements": [{"type": "text", "content": "hello"}],
        "blocks": [
            {"block_type": "title", "card_id": "title", "content": "Intro"},
            {"block_type": "body", "card_id": "left", "content": "hello"},
        ],
    }


def test_exporter_uses_module_orchestrator_for_slide_retry(monkeypatch):
    import src.minimax_exporter as exporter

    monkeypatch.setenv("PPT_MODULE_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_MODULE_RETRY_MAX_PARALLEL", "3")

    calls = []

    def _fake_run(cmd, capture_output=True, text=True, timeout=180):
        calls.append(list(cmd))
        cmd_list = [str(item) for item in cmd]
        assert "--output" in cmd_list
        assert "--render-output" in cmd_list
        output_path = Path(cmd_list[cmd_list.index("--output") + 1])
        render_path = Path(cmd_list[cmd_list.index("--render-output") + 1])
        output_path.write_bytes(b"pptx-module-retry")
        render_path.write_text(
            json.dumps({"mode": "minimax_presentation", "slides": [{"slide_id": "s1", "page_number": 1}]}),
            encoding="utf-8",
        )
        stdout = json.dumps(
            {
                "success": True,
                "render_each": {"ok": True, "slide_results": [{"slide_id": "s1", "ok": True}]},
                "compile": {"ok": True},
            }
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(exporter.subprocess, "run", _fake_run)

    result = export_minimax_pptx(
        slides=[_sample_slide()],
        title="Deck",
        author="AutoViralVid",
        retry_scope="slide",
        target_slide_ids=["s1"],
        generator_mode="official",
        timeout=30,
    )

    assert calls, "subprocess should be invoked"
    flattened = " ".join(str(item) for item in calls[0])
    assert "orchestrate-pptx-modules.mjs" in flattened
    assert "--target-slide-ids" in calls[0]
    assert result["is_full_deck"] is True
    assert result["generator_meta"].get("module_retry_enabled") is True
    assert result["generator_meta"].get("module_retry_target_slide_ids") == ["s1"]


def test_exporter_module_retry_enables_subagent_exec_flag_by_default_on_worker(monkeypatch):
    import src.minimax_exporter as exporter

    monkeypatch.setenv("PPT_MODULE_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_EXECUTION_ROLE", "worker")

    calls = []

    def _fake_run(cmd, capture_output=True, text=True, timeout=180):
        calls.append(list(cmd))
        cmd_list = [str(item) for item in cmd]
        output_path = Path(cmd_list[cmd_list.index("--output") + 1])
        render_path = Path(cmd_list[cmd_list.index("--render-output") + 1])
        output_path.write_bytes(b"pptx-module-retry")
        render_path.write_text(
            json.dumps({"mode": "minimax_presentation", "slides": [{"slide_id": "s1", "page_number": 1}]}),
            encoding="utf-8",
        )
        stdout = json.dumps(
            {
                "success": True,
                "render_each": {"ok": True, "slide_results": [{"slide_id": "s1", "ok": True}]},
                "compile": {"ok": True},
            }
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(exporter.subprocess, "run", _fake_run)

    export_minimax_pptx(
        slides=[_sample_slide()],
        title="Deck",
        author="AutoViralVid",
        retry_scope="slide",
        target_slide_ids=["s1"],
        generator_mode="official",
        timeout=30,
    )

    assert calls, "subprocess should be invoked"
    assert "--subagent-exec" in calls[0]


def test_exporter_module_retry_enables_subagent_exec_flag_on_web_by_default(monkeypatch):
    import src.minimax_exporter as exporter

    monkeypatch.setenv("PPT_MODULE_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_EXECUTION_ROLE", "web")

    calls = []

    def _fake_run(cmd, capture_output=True, text=True, timeout=180):
        calls.append(list(cmd))
        cmd_list = [str(item) for item in cmd]
        output_path = Path(cmd_list[cmd_list.index("--output") + 1])
        render_path = Path(cmd_list[cmd_list.index("--render-output") + 1])
        output_path.write_bytes(b"pptx-module-retry")
        render_path.write_text(
            json.dumps({"mode": "minimax_presentation", "slides": [{"slide_id": "s1", "page_number": 1}]}),
            encoding="utf-8",
        )
        stdout = json.dumps(
            {
                "success": True,
                "render_each": {"ok": True, "slide_results": [{"slide_id": "s1", "ok": True}]},
                "compile": {"ok": True},
            }
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(exporter.subprocess, "run", _fake_run)

    export_minimax_pptx(
        slides=[_sample_slide()],
        title="Deck",
        author="AutoViralVid",
        retry_scope="slide",
        target_slide_ids=["s1"],
        generator_mode="official",
        timeout=30,
    )

    assert calls, "subprocess should be invoked"
    assert "--subagent-exec" in calls[0]


def test_module_retry_defaults_on_on_vercel_web_role(monkeypatch):
    import src.minimax_exporter as exporter

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("PPT_MODULE_RETRY_ENABLED", raising=False)
    monkeypatch.delenv("PPT_EXECUTION_ROLE", raising=False)
    assert exporter._module_retry_enabled() is True


def test_module_retry_can_be_explicitly_enabled_on_vercel(monkeypatch):
    import src.minimax_exporter as exporter

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("PPT_MODULE_RETRY_ENABLED", "true")
    assert exporter._module_retry_enabled() is True


def test_module_mainflow_defaults_on_for_worker(monkeypatch):
    import src.minimax_exporter as exporter

    monkeypatch.setenv("PPT_EXECUTION_ROLE", "worker")
    monkeypatch.delenv("PPT_MODULE_MAINFLOW_ENABLED", raising=False)
    assert exporter._module_mainflow_enabled() is True


def test_module_mainflow_defaults_on_for_web(monkeypatch):
    import src.minimax_exporter as exporter

    monkeypatch.setenv("PPT_EXECUTION_ROLE", "web")
    monkeypatch.delenv("PPT_MODULE_MAINFLOW_ENABLED", raising=False)
    assert exporter._module_mainflow_enabled() is True


def test_module_mainflow_can_be_explicitly_disabled_on_worker(monkeypatch):
    import src.minimax_exporter as exporter

    monkeypatch.setenv("PPT_EXECUTION_ROLE", "worker")
    monkeypatch.setenv("PPT_MODULE_MAINFLOW_ENABLED", "false")
    assert exporter._module_mainflow_enabled() is False


def test_exporter_uses_module_orchestrator_for_mainflow_when_enabled(monkeypatch):
    import src.minimax_exporter as exporter

    monkeypatch.setenv("PPT_MODULE_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_EXECUTION_ROLE", "worker")
    monkeypatch.delenv("PPT_MODULE_MAINFLOW_ENABLED", raising=False)

    calls = []

    def _fake_run(cmd, capture_output=True, text=True, timeout=180):
        calls.append(list(cmd))
        cmd_list = [str(item) for item in cmd]
        output_path = Path(cmd_list[cmd_list.index("--output") + 1])
        render_path = Path(cmd_list[cmd_list.index("--render-output") + 1])
        output_path.write_bytes(b"pptx-module-mainflow")
        render_path.write_text(
            json.dumps({"mode": "minimax_presentation", "slides": [{"slide_id": "s1", "page_number": 1}]}),
            encoding="utf-8",
        )
        stdout = json.dumps(
            {
                "success": True,
                "render_each": {"ok": True, "slide_results": [{"slide_id": "s1", "ok": True}]},
                "compile": {"ok": True},
            }
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(exporter.subprocess, "run", _fake_run)

    result = export_minimax_pptx(
        slides=[_sample_slide()],
        title="Deck",
        author="AutoViralVid",
        retry_scope="deck",
        target_slide_ids=[],
        generator_mode="official",
        timeout=30,
    )

    assert calls, "subprocess should be invoked"
    flattened = " ".join(str(item) for item in calls[0])
    assert "orchestrate-pptx-modules.mjs" in flattened
    assert "--render-each" in calls[0]
    assert "--subagent-exec" in calls[0]
    assert "--target-slide-ids" not in calls[0]
    assert result["is_full_deck"] is True
    assert result["generator_meta"].get("module_orchestrator_mode") == "mainflow"
    assert result["generator_meta"].get("module_mainflow_enabled") is True
    assert result["generator_meta"].get("module_mainflow_render_each_enabled") is True


def test_exporter_mainflow_can_enable_render_each_explicitly(monkeypatch):
    import src.minimax_exporter as exporter

    monkeypatch.setenv("PPT_MODULE_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_EXECUTION_ROLE", "worker")
    monkeypatch.setenv("PPT_MODULE_MAINFLOW_RENDER_EACH_ENABLED", "true")

    calls = []

    def _fake_run(cmd, capture_output=True, text=True, timeout=180):
        calls.append(list(cmd))
        cmd_list = [str(item) for item in cmd]
        output_path = Path(cmd_list[cmd_list.index("--output") + 1])
        render_path = Path(cmd_list[cmd_list.index("--render-output") + 1])
        output_path.write_bytes(b"pptx-module-mainflow-render-each")
        render_path.write_text(
            json.dumps({"mode": "minimax_presentation", "slides": [{"slide_id": "s1", "page_number": 1}]}),
            encoding="utf-8",
        )
        stdout = json.dumps({"success": True, "compile": {"ok": True}})
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(exporter.subprocess, "run", _fake_run)

    export_minimax_pptx(
        slides=[_sample_slide()],
        title="Deck",
        author="AutoViralVid",
        retry_scope="deck",
        target_slide_ids=[],
        generator_mode="official",
        timeout=30,
    )

    assert calls, "subprocess should be invoked"
    assert "--render-each" in calls[0]
