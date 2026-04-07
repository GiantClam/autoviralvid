import pytest

from src.ppt_export_text_qa_service import PPTExportTextQAService


@pytest.mark.asyncio
async def test_text_qa_service_skips_markitdown_when_disabled(monkeypatch):
    monkeypatch.setenv("PPT_TEXT_QA_MARKITDOWN_ENABLED", "false")
    svc = PPTExportTextQAService()
    markitdown_called = {"v": False}

    def _audit(_slides, *, render_spec):
        assert isinstance(render_spec, dict)
        return {"issue_codes": ["placeholder_text"]}

    def _markitdown(_pptx_bytes, *, timeout_sec):
        markitdown_called["v"] = True
        _ = timeout_sec
        return {}

    out = await svc.run(
        export_result={"input_payload": {"slides": [{"slide_id": "s1"}]}, "pptx_bytes": b"x"},
        slides_data=[{"slide_id": "fallback"}],
        render_spec={},
        audit_textual_slides=_audit,
        run_markitdown_text_qa=_markitdown,
    )
    assert out == {"issue_codes": ["placeholder_text"]}
    assert markitdown_called["v"] is False


@pytest.mark.asyncio
async def test_text_qa_service_markitdown_exception_is_degraded(monkeypatch):
    monkeypatch.setenv("PPT_TEXT_QA_MARKITDOWN_ENABLED", "true")
    monkeypatch.setenv("PPT_TEXT_QA_MARKITDOWN_TIMEOUT_SEC", "20")
    svc = PPTExportTextQAService()

    def _audit(_slides, *, render_spec):
        assert isinstance(render_spec, dict)
        return {}

    def _markitdown(_pptx_bytes, *, timeout_sec):
        _ = timeout_sec
        raise RuntimeError("markitdown boom")

    out = await svc.run(
        export_result={"input_payload": {"slides": [{"slide_id": "s1"}]}, "pptx_bytes": b"x"},
        slides_data=[],
        render_spec={},
        audit_textual_slides=_audit,
        run_markitdown_text_qa=_markitdown,
    )
    md = out.get("markitdown") or {}
    assert md.get("ok") is False
    assert "markitdown_extraction_failed" in (md.get("issue_codes") or [])


@pytest.mark.asyncio
async def test_text_qa_service_merges_markitdown_issue_codes(monkeypatch):
    monkeypatch.setenv("PPT_TEXT_QA_MARKITDOWN_ENABLED", "true")
    svc = PPTExportTextQAService()

    def _audit(_slides, *, render_spec):
        assert isinstance(render_spec, dict)
        return {"issue_codes": ["placeholder_text"]}

    def _markitdown(_pptx_bytes, *, timeout_sec):
        _ = timeout_sec
        return {"issue_codes": ["placeholder_text", "markitdown_placeholder_text"]}

    out = await svc.run(
        export_result={"input_payload": {"slides": [{"slide_id": "s1"}]}, "pptx_bytes": b"x"},
        slides_data=[],
        render_spec={},
        audit_textual_slides=_audit,
        run_markitdown_text_qa=_markitdown,
    )
    assert out.get("issue_codes") == ["markitdown_placeholder_text", "placeholder_text"]

