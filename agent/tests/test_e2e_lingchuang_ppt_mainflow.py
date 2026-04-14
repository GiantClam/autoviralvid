from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def _load_script_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "e2e_lingchuang_ppt.py"
    spec = importlib.util.spec_from_file_location("e2e_lingchuang_ppt", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, script_path


def test_generate_from_prompt_request_uses_full_requirement_text():
    module, _ = _load_script_module()
    req = module.build_generate_from_prompt_request(module.DEFAULT_REQUIREMENT, 12)
    assert req["language"] == "zh-CN"
    assert req["total_pages"] == 12
    assert req["style"] == "professional"
    assert req["web_enrichment"] is True
    assert req["image_asset_enrichment"] is True
    assert "灵创智能企业推介" in req["prompt"]
    assert "高端五轴联动加工中心" in req["prompt"]


def test_script_only_calls_prompt_master_endpoint():
    _, script_path = _load_script_module()
    text = script_path.read_text(encoding="utf-8")
    assert "scripts/generate-pptx-minimax.mjs" not in text
    assert "/api/v1/ppt/generate-from-prompt" in text
    assert "/api/v1/ppt/outline" not in text
    assert "/api/v1/ppt/content" not in text
    assert "/api/v1/ppt/export" not in text



def test_call_api_decodes_utf8_output_even_on_windows_locale(monkeypatch):
    module, _ = _load_script_module()

    payload = {"success": True, "data": {"title": "灵创智能企业推介"}}
    fake = SimpleNamespace(
        returncode=0,
        stdout=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stderr=b"",
    )

    def _fake_run(*args, **kwargs):
        return fake

    monkeypatch.setattr(module.subprocess, "run", _fake_run)
    resp = module.call_api("POST", "/api/v1/ppt/generate-from-prompt", {"requirement": "x"})
    assert resp["success"] is True
    assert resp["data"]["title"] == "灵创智能企业推介"


def test_call_api_honors_custom_timeout(monkeypatch):
    module, _ = _load_script_module()
    seen = {}

    def _fake_run(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return SimpleNamespace(returncode=0, stdout=b'{"success":true,"data":{}}', stderr=b"")

    monkeypatch.setattr(module.subprocess, "run", _fake_run)
    resp = module.call_api("POST", "/api/v1/ppt/generate-from-prompt", {"slides": []}, timeout_sec=1234)
    assert resp["success"] is True
    assert seen["timeout"] == 1234


