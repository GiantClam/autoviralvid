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


def test_outline_request_uses_full_requirement_text():
    module, _ = _load_script_module()
    req = module.build_outline_request(module.DEFAULT_REQUIREMENT, 12)
    assert req["language"] == "zh-CN"
    assert req["num_slides"] == 12
    assert req["style"] == "professional"
    assert "灵创智能企业推介" in req["requirement"]
    assert "高端五轴联动加工中心" in req["requirement"]


def test_export_request_enables_mainflow_quality_controls():
    module, _ = _load_script_module()
    req = module.build_export_request([{"title": "x"}], "灵创智能企业推介")
    assert req["generator_mode"] == "official"
    assert req["route_mode"] == "refine"
    assert req["quality_profile"] == "high_density_consulting"
    assert req["constraint_hardness"] == "strict"
    assert req["visual_priority"] is True
    assert req["original_style"] is False
    assert req["disable_local_style_rewrite"] is False


def test_script_no_longer_direct_calls_node_generator():
    _, script_path = _load_script_module()
    text = script_path.read_text(encoding="utf-8")
    assert "scripts/generate-pptx-minimax.mjs" not in text
    assert "/api/v1/ppt/export" in text


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
    resp = module.call_api("POST", "/api/v1/ppt/outline", {"requirement": "x"})
    assert resp["success"] is True
    assert resp["data"]["title"] == "灵创智能企业推介"


def test_call_api_honors_custom_timeout(monkeypatch):
    module, _ = _load_script_module()
    seen = {}

    def _fake_run(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return SimpleNamespace(returncode=0, stdout=b'{"success":true,"data":{}}', stderr=b"")

    monkeypatch.setattr(module.subprocess, "run", _fake_run)
    resp = module.call_api("POST", "/api/v1/ppt/export", {"slides": []}, timeout_sec=1234)
    assert resp["success"] is True
    assert seen["timeout"] == 1234
