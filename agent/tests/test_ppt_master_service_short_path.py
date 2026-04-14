from __future__ import annotations

import asyncio
import os

from src.ppt_master_service import PPTMasterService


def test_build_skill_runtime_request_defaults(monkeypatch) -> None:
    monkeypatch.delenv("PPT_MASTER_SKILL_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("PPT_MASTER_RUNTIME_TIMEOUT_SEC", raising=False)
    service = PPTMasterService()
    payload = service._build_skill_runtime_request(
        prompt="test topic",
        project_name="ai_gen_test",
        total_pages=10,
        style="professional",
        color_scheme=None,
        language="zh-CN",
        template_family="auto",
        include_images=False,
        web_enrichment=None,
        image_asset_enrichment=None,
    )

    assert payload["prompt"] == "test topic"
    assert payload["project_name"] == "ai_gen_test"
    assert payload["total_pages"] == 10
    assert payload["language"] == "zh-CN"
    assert payload["template_family"] == "auto"
    assert payload["include_images"] is False
    assert payload["web_enrichment"] is True
    assert payload["image_asset_enrichment"] is True
    assert payload["timeout_sec"] == 3600


def test_build_skill_runtime_request_timeout_override(monkeypatch) -> None:
    monkeypatch.setenv("PPT_MASTER_SKILL_TIMEOUT_SEC", "900")
    service = PPTMasterService()
    payload = service._build_skill_runtime_request(
        prompt="test",
        project_name="ai_gen_test",
        total_pages=10,
        style="professional",
        color_scheme=None,
        language="en-US",
        template_family="auto",
        include_images=False,
        web_enrichment=None,
        image_asset_enrichment=None,
    )
    assert payload["language"] == "en-US"
    assert payload["timeout_sec"] == 900


def test_runtime_command_defaults(monkeypatch) -> None:
    monkeypatch.delenv("PPT_MASTER_SKILL_RUNTIME_BIN", raising=False)
    monkeypatch.delenv("PPT_MASTER_SKILL_RUNTIME_ARGS", raising=False)
    service = PPTMasterService()
    command = service._runtime_command()
    assert len(command) >= 3
    assert command[1:] == ["-m", "src.ppt_master_pipeline_runtime"]


def test_build_skill_runtime_request_enrichment_override() -> None:
    service = PPTMasterService()
    payload = service._build_skill_runtime_request(
        prompt="test",
        project_name="ai_gen_test",
        total_pages=10,
        style="professional",
        color_scheme=None,
        language="zh-CN",
        template_family="auto",
        include_images=False,
        web_enrichment=False,
        image_asset_enrichment=False,
    )
    assert payload["web_enrichment"] is False
    assert payload["image_asset_enrichment"] is False


def test_ensure_runtime_env_no_codex_defaults(monkeypatch) -> None:
    monkeypatch.delenv("PPT_MASTER_CODEX_BIN", raising=False)
    service = PPTMasterService()
    service._ensure_runtime_env()
    assert os.getenv("PPT_MASTER_CODEX_BIN") is None


def test_run_skill_runtime_inproc(monkeypatch) -> None:
    monkeypatch.setenv("PPT_MASTER_RUNTIME_MODE", "inproc")
    service = PPTMasterService()

    def _fake_blackbox(payload):
        assert payload["prompt"] == "demo"
        return {"export": {"output_pptx": "/tmp/demo.pptx"}, "artifacts": {}}

    monkeypatch.setattr("src.ppt_master_blackbox_local.run_blackbox_request", _fake_blackbox)
    result = asyncio.run(service._run_skill_runtime({"prompt": "demo"}))
    assert result["export"]["output_pptx"] == "/tmp/demo.pptx"
