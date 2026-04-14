from __future__ import annotations

import sys
import types

import pytest

import src.ppt_template_export_service as template_service_mod
from src.ppt_template_export_service import PPTTemplateExportService


@pytest.mark.asyncio
async def test_template_export_flow_returns_expected_payload(monkeypatch):
    svc = PPTTemplateExportService()

    monkeypatch.setattr(
        template_service_mod.pptx_engine,
        "fill_template_pptx",
        lambda **_kwargs: {
            "pptx_bytes": b"pptx",
            "replacement_count": 2,
            "template_slide_count": 3,
            "slides_used": 2,
            "engine": "template-engine",
            "markitdown_used": True,
            "token_keys": ["{{title}}"],
            "cleaned_resource_count": 1,
            "markitdown_ok": True,
            "markitdown_issue": "",
        },
    )

    out = await svc.run_template_edit_flow(
        template_file_url="https://example.com/template.pptx",
        title="Deck",
        author="Author",
        raw_slides_data=[{"slide_id": "s1", "title": "Intro"}],
        effective_template_family="auto",
        effective_style_variant="business_clean",
        effective_palette_key="palette",
        enforce_skill_runtime=False,
        download_remote_file_bytes=lambda *_args, **_kwargs: _async_value(b"template"),
        upload_bytes_to_r2=lambda _b, key, content_type: _async_value(
            f"https://example.com/{key}"
        ),
        new_id=lambda: "proj1",
        run_markitdown_text_qa=lambda *_args, **_kwargs: {"ok": True},
        audit_textual_slides=lambda *_args, **_kwargs: {"ok": True, "issue_codes": []},
        assert_skill_runtime_success=lambda **_kwargs: None,
    )

    assert out.url.endswith("/projects/proj1/pptx/presentation.pptx")
    assert out.template_result.get("replacement_count") == 2
    statuses = [str(item.get("status") or "") for item in out.diagnostics]
    assert "template_edit_applied" in statuses
    assert "template_markitdown_probe" in statuses
    assert isinstance(out.template_skill_runtime, dict)


@pytest.mark.asyncio
async def test_template_export_flow_enforce_runtime_raises(monkeypatch):
    svc = PPTTemplateExportService()

    fake_mod = types.SimpleNamespace(
        execute_installed_skill_request=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("skill fail")
        )
    )
    monkeypatch.setitem(sys.modules, "src.installed_skill_executor", fake_mod)

    with pytest.raises(RuntimeError, match="template_skill_runtime_failed:"):
        await svc.run_template_edit_flow(
            template_file_url="https://example.com/template.pptx",
            title="Deck",
            author="Author",
            raw_slides_data=[],
            effective_template_family="auto",
            effective_style_variant="business_clean",
            effective_palette_key="palette",
            enforce_skill_runtime=True,
            download_remote_file_bytes=lambda *_args, **_kwargs: _async_value(
                b"template"
            ),
            upload_bytes_to_r2=lambda _b, key, content_type: _async_value(
                f"https://example.com/{key}"
            ),
            new_id=lambda: "proj2",
            run_markitdown_text_qa=lambda *_args, **_kwargs: {"ok": True},
            audit_textual_slides=lambda *_args, **_kwargs: {"ok": True},
            assert_skill_runtime_success=lambda **_kwargs: None,
        )


async def _async_value(value):
    return value
