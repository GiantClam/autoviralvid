from __future__ import annotations

from src import ppt_master_pipeline_runtime as runtime


def test_run_passthrough_to_local_blackbox(monkeypatch) -> None:
    captured = {}

    def _fake_blackbox(payload):
        captured["payload"] = payload
        return {"export": {"output_pptx": "/tmp/demo.pptx"}, "artifacts": {}}

    monkeypatch.setattr(
        "src.ppt_master_blackbox_local.run_blackbox_request",
        _fake_blackbox,
    )
    request_payload = {"prompt": "topic", "total_pages": 8}
    result = runtime._run(request_payload)

    assert captured["payload"] == request_payload
    assert result["export"]["output_pptx"] == "/tmp/demo.pptx"


def test_read_stdin_payload_invalid_json_returns_empty(monkeypatch) -> None:
    class _FakeBuffer:
        def read(self):
            return b"not-json"

    class _FakeStdin:
        buffer = _FakeBuffer()

    monkeypatch.setattr(runtime.sys, "stdin", _FakeStdin())
    parsed = runtime._read_stdin_payload()
    assert parsed == {}
