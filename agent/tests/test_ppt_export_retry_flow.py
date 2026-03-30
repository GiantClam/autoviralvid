import pytest
import copy

from src.ppt_quality_gate import QualityIssue, QualityResult
import src.ppt_service as ppt_service
from src.schemas.ppt import ExportRequest, SlideContent, SlideElement
from src.ppt_service import PPTService


@pytest.mark.asyncio
async def test_quality_gate_triggers_slide_retry_and_persists_diagnostics(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.ppt_service as ppt_service
    import src.ppt_visual_qa as ppt_visual_qa
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_PARTIAL_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "3")

    # avoid test delays from retry backoff
    async def _fake_sleep(_seconds):
        return None

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)

    export_calls = []

    def _fake_export(**kwargs):
        export_calls.append(kwargs)
        return {
            "pptx_bytes": b"fake-pptx",
            "generator_meta": {"render_slides": 1},
            "render_spec": {
                "mode": "minimax_presentation",
                "slides": [{"slide_id": "s1", "page_number": 1, "slide_type": "grid_3"}],
            },
            "input_payload": {
                "slides": [
                    {
                        "slide_id": "s1",
                        "title": "Intro",
                        "elements": [{"type": "text", "content": "hello"}],
                    }
                ]
            },
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(
        pptx_rasterizer,
        "rasterize_pptx_bytes_to_png_bytes",
        lambda _pptx: [b"png-bytes"],
    )
    async def _fake_audit_rendered_slides(*_args, **_kwargs):
        return {"slide_count": 1, "blank_slide_ratio": 0.0, "low_contrast_ratio": 0.0}
    monkeypatch.setattr(ppt_visual_qa, "audit_rendered_slides", _fake_audit_rendered_slides)

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    validate_calls = {"count": 0}

    def _fake_validate_deck(_slides, **_kwargs):
        validate_calls["count"] += 1
        if validate_calls["count"] == 1:
            return QualityResult(
                ok=False,
                issues=[
                    QualityIssue(
                        slide_id="s1",
                        code="placeholder_pollution",
                        message="placeholder",
                        retry_scope="slide",
                        retry_target_ids=["s1"],
                    )
                ],
            )
        return QualityResult(ok=True, issues=[])

    monkeypatch.setattr(quality_gate, "validate_deck", _fake_validate_deck)

    persisted = []
    monkeypatch.setattr(ppt_service, "_persist_ppt_retry_diagnostic", lambda payload: persisted.append(payload))

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Intro",
                elements=[SlideElement(type="text", content="hello", block_id="b1")],
                narration="hello",
                duration=120,
            )
        ],
        title="Deck",
        author="AutoViralVid",
        retry_scope="deck",
        route_mode="standard",
        target_slide_ids=[],
    )

    svc = PPTService()
    result = await svc.export_pptx(req)

    assert result["attempts"] == 2
    assert result["retry_scope"] == "deck"
    assert result["route_mode"] == "standard"
    assert len(export_calls) == 3
    assert export_calls[1]["retry_scope"] == "slide"
    assert export_calls[2]["retry_scope"] == "deck"
    assert export_calls[2]["target_slide_ids"] == []
    assert export_calls[1]["route_mode"] == "standard"
    assert "failure_code" in str(export_calls[1]["retry_hint"])
    assert "quality_score" in result
    assert "observability_report" in result
    statuses = [row["status"] for row in persisted]
    assert "quality_gate_failed" in statuses
    assert "success" in statuses


@pytest.mark.asyncio
async def test_partial_retry_full_deck_result_skips_finalize_call(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.ppt_visual_qa as ppt_visual_qa
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_PARTIAL_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "3")

    async def _fake_sleep(_seconds):
        return None

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)

    calls = []

    def _fake_export(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        return {
            "pptx_bytes": b"ok",
            "generator_meta": {"render_slides": 1},
            "render_spec": {
                "mode": "minimax_presentation",
                "slides": [{"slide_id": "s1", "slide_type": "split_2", "page_number": 1}],
            },
            "input_payload": {
                "slides": [
                    {
                        "slide_id": "s1",
                        "title": "Intro",
                        "elements": [{"type": "text", "content": "hello"}],
                    }
                ]
            },
            "is_full_deck": bool(str(kwargs.get("retry_scope") or "").strip().lower() in {"deck", "slide"}),
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: [b"png-bytes"])

    async def _fake_audit_rendered_slides(*_args, **_kwargs):
        return {"slide_count": 1, "blank_slide_ratio": 0.0, "low_contrast_ratio": 0.0}

    monkeypatch.setattr(ppt_visual_qa, "audit_rendered_slides", _fake_audit_rendered_slides)
    monkeypatch.setattr(quality_gate, "validate_layout_diversity", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(quality_gate, "validate_visual_audit", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))

    validate_calls = {"count": 0}

    def _fake_validate_deck(_slides, **_kwargs):
        validate_calls["count"] += 1
        if validate_calls["count"] == 1:
            return QualityResult(
                ok=False,
                issues=[
                    QualityIssue(
                        slide_id="s1",
                        code="placeholder_pollution",
                        message="placeholder",
                        retry_scope="slide",
                        retry_target_ids=["s1"],
                    )
                ],
            )
        return QualityResult(ok=True, issues=[])

    monkeypatch.setattr(quality_gate, "validate_deck", _fake_validate_deck)

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Intro",
                elements=[SlideElement(type="text", content="hello", block_id="b1")],
                narration="hello",
                duration=120,
            )
        ],
        title="Deck",
        author="AutoViralVid",
        retry_scope="deck",
        route_mode="standard",
    )

    result = await PPTService().export_pptx(req)

    assert result["attempts"] == 2
    assert len(calls) == 2
    assert calls[0]["retry_scope"] == "deck"
    assert calls[1]["retry_scope"] == "slide"


@pytest.mark.asyncio
async def test_template_file_url_uses_template_edit_route(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.pptx_engine as pptx_engine
    import src.ppt_service as ppt_service
    import src.r2 as r2

    def _unexpected_export(**_kwargs):
        raise AssertionError("minimax exporter should not be called in template edit route")

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _unexpected_export)

    async def _fake_download_remote_file_bytes(_url: str, *, suffix: str = ".bin"):
        assert suffix == ".pptx"
        return b"fake-template-pptx-bytes"

    monkeypatch.setattr(ppt_service, "_download_remote_file_bytes", _fake_download_remote_file_bytes)

    def _fake_fill_template_pptx(*, template_bytes, slides, deck_title, author):
        assert template_bytes == b"fake-template-pptx-bytes"
        assert deck_title == "Deck"
        assert author == "AutoViralVid"
        assert isinstance(slides, list)
        return {
            "pptx_bytes": b"template-output-pptx",
            "replacement_count": 5,
            "token_keys": ["deck_title", "slide_1_title"],
            "slides_used": 1,
            "template_slide_count": 2,
            "engine": "xml",
            "cleaned_resource_count": 0,
        }

    monkeypatch.setattr(pptx_engine, "fill_template_pptx", _fake_fill_template_pptx)

    async def _fake_upload(_bytes, key, content_type):
        assert _bytes == b"template-output-pptx"
        assert content_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Intro",
                elements=[SlideElement(type="text", content="hello", block_id="b1")],
                narration="hello",
                duration=120,
            )
        ],
        title="Deck",
        author="AutoViralVid",
        route_mode="fast",
        template_file_url="https://example.com/template.pptx",
    )

    result = await PPTService().export_pptx(req)

    assert result["skill"] == "pptx_template_editor"
    assert result["generator_mode"] == "template_edit"
    assert result["retry_scope"] == "deck"
    assert result["attempts"] == 1
    assert result["route_mode"] == "fast"
    assert result["template_edit"]["replacement_count"] == 5
    assert result["template_edit"]["slides_used"] == 1
    assert result["template_edit"]["engine"] == "xml"
    assert result["url"].startswith("https://example.com/projects/")


@pytest.mark.asyncio
async def test_template_renderer_summary_surfaces_in_observability_and_alerts(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.ppt_service as ppt_service
    import src.ppt_visual_qa as ppt_visual_qa
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "1")

    def _fake_export(**_kwargs):
        return {
            "pptx_bytes": b"pptx-template-summary",
            "generator_meta": {"render_slides": 4},
            "render_spec": {
                "mode": "minimax_presentation",
                "slides": [{"slide_id": "s1", "slide_type": "split_2"}],
                "template_renderer_summary": {
                    "evaluated_slides": 4,
                    "skipped_slides": 3,
                    "skipped_ratio": 0.75,
                    "mode_counts": {"local_template": 1, "fallback_generic": 3},
                    "reason_counts": {"unsupported_layout": 3},
                    "reason_ratios": {"unsupported_layout": 1.0},
                },
            },
            "input_payload": {
                "slides": [
                    {"slide_id": "s1", "title": "Intro", "elements": [{"type": "text", "content": "hello"}]}
                ]
            },
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(quality_gate, "validate_deck", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(
        quality_gate,
        "validate_layout_diversity",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )
    monkeypatch.setattr(
        quality_gate,
        "validate_visual_audit",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )
    monkeypatch.setattr(pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: [b"png-bytes"])

    async def _fake_audit_rendered_slides(*_args, **_kwargs):
        return {"slide_count": 1, "blank_slide_ratio": 0.0, "low_contrast_ratio": 0.0}

    monkeypatch.setattr(ppt_visual_qa, "audit_rendered_slides", _fake_audit_rendered_slides)

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    persisted_observability = []
    monkeypatch.setattr(
        ppt_service,
        "_persist_ppt_observability_report",
        lambda payload: persisted_observability.append(payload),
    )

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Intro",
                elements=[SlideElement(type="text", content="hello", block_id="b1")],
                narration="hello",
                duration=120,
            )
        ],
        title="Deck",
        author="AutoViralVid",
        route_mode="standard",
    )

    result = await PPTService().export_pptx(req)

    summary = result.get("observability_report", {}).get("template_renderer_summary")
    assert isinstance(summary, dict)
    assert summary.get("skipped_ratio") == pytest.approx(0.75)
    codes = {str(item.get("code")) for item in result.get("alerts", [])}
    assert "template_renderer_fallback_ratio_high" in codes
    assert "template_renderer_fallback_reason_concentrated" in codes
    assert persisted_observability
    persisted_diag = persisted_observability[-1].get("diagnostics") or []
    assert any(item.get("status") == "template_renderer_summary" for item in persisted_diag if isinstance(item, dict))


def test_collect_strict_quality_blockers_detects_core_failures():
    blockers = ppt_service._collect_strict_quality_blockers(
        alerts=[],
        generator_meta={
            "render_each": {
                "subagent_runs": [
                    {"enabled": True, "applied": False, "skipped": True, "reason": "Error code: 403"},
                    {"enabled": True, "applied": False, "skipped": True, "reason": "Author openai is banned"},
                ]
            }
        },
        template_renderer_summary={
            "evaluated_slides": 12,
            "skipped_slides": 3,
            "skipped_ratio": 0.25,
            "reason_ratios": {"unsupported_layout": 1.0},
        },
        text_qa={
            "markitdown": {
                "ok": False,
                "error": "No module named markitdown",
                "issue_codes": ["markitdown_extraction_failed"],
            }
        },
    )
    codes = {str(item.get("code")) for item in blockers}
    assert "strict_subagent_all_skipped" in codes
    assert "strict_template_renderer_fallback_ratio_high" in codes
    assert "strict_template_renderer_reason_concentrated" in codes
    assert "strict_markitdown_unavailable" in codes


@pytest.mark.asyncio
async def test_strict_mode_fails_when_subagent_and_markitdown_are_blocked(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.ppt_visual_qa as ppt_visual_qa
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "1")

    def _fake_export(**_kwargs):
        return {
            "pptx_bytes": b"pptx-strict-blocked",
            "generator_meta": {
                "render_each": {
                    "subagent_runs": [
                        {
                            "enabled": True,
                            "applied": False,
                            "skipped": True,
                            "reason": "Error code: 403 - Author openai is banned",
                        }
                    ]
                }
            },
            "render_spec": {
                "mode": "minimax_presentation",
                "slides": [{"slide_id": "s1", "slide_type": "split_2"}],
                "template_renderer_summary": {
                    "evaluated_slides": 12,
                    "skipped_slides": 3,
                    "skipped_ratio": 0.25,
                    "reason_ratios": {"unsupported_layout": 1.0},
                    "reason_counts": {"unsupported_layout": 3},
                },
            },
            "input_payload": {
                "slides": [
                    {"slide_id": "s1", "title": "Intro", "elements": [{"type": "text", "content": "hello"}]}
                ]
            },
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(quality_gate, "validate_deck", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(
        quality_gate,
        "validate_layout_diversity",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )
    monkeypatch.setattr(
        quality_gate,
        "validate_visual_audit",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )
    monkeypatch.setattr(pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: [b"png-bytes"])

    async def _fake_audit_rendered_slides(*_args, **_kwargs):
        return {"slide_count": 1, "blank_slide_ratio": 0.0, "low_contrast_ratio": 0.0}

    monkeypatch.setattr(ppt_visual_qa, "audit_rendered_slides", _fake_audit_rendered_slides)
    monkeypatch.setattr(
        ppt_visual_qa,
        "run_markitdown_text_qa",
        lambda *_args, **_kwargs: {
            "enabled": True,
            "ok": False,
            "error": "No module named markitdown",
            "issue_codes": ["markitdown_extraction_failed"],
        },
    )

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    persisted_observability = []
    monkeypatch.setattr(
        ppt_service,
        "_persist_ppt_observability_report",
        lambda payload: persisted_observability.append(payload),
    )

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Intro",
                elements=[SlideElement(type="text", content="hello", block_id="b1")],
                narration="hello",
                duration=120,
            )
        ],
        title="Deck",
        author="AutoViralVid",
        route_mode="refine",
        quality_profile="high_density_consulting",
        constraint_hardness="strict",
    )

    with pytest.raises(RuntimeError, match="Strict quality gate failed"):
        await PPTService().export_pptx(req)

    assert persisted_observability
    assert persisted_observability[-1].get("status") == "failed"
    assert persisted_observability[-1].get("failure_code") == "strict_quality_gate_failed"


@pytest.mark.asyncio
async def test_text_qa_surfaces_in_observability_and_alerts(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.ppt_service as ppt_service
    import src.ppt_visual_qa as ppt_visual_qa
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "1")

    def _fake_export(**_kwargs):
        return {
            "pptx_bytes": b"pptx-text-qa",
            "generator_meta": {"render_slides": 2},
            "render_spec": {
                "mode": "minimax_presentation",
                "slides": [
                    {"slide_id": "s1", "slide_type": "split_2", "page_number": 1},
                    {"slide_id": "s2", "slide_type": "split_2", "page_number": 3},
                ],
            },
            "input_payload": {
                "slides": [
                    {
                        "slide_id": "s1",
                        "title": "结论：市场渗透加速",
                        "content_strategy": {
                            "assertion": "结论：市场渗透加速",
                            "evidence": ["同比提升 38%"],
                        },
                        "elements": [{"type": "text", "content": "证据：同比提升 38%"}],
                    },
                    {
                        "slide_id": "s2",
                        "title": "",
                        "content_strategy": {
                            "assertion": "关键结论：转化率提升",
                            "evidence": ["转化率提升 22%", "ROI 增长"],
                        },
                        "elements": [{"type": "text", "content": "TODO placeholder xxxx"}],
                    },
                ]
            },
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(quality_gate, "validate_deck", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(quality_gate, "validate_layout_diversity", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(quality_gate, "validate_visual_audit", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: [b"png-bytes"])

    async def _fake_audit_rendered_slides(*_args, **_kwargs):
        return {"slide_count": 2, "blank_slide_ratio": 0.0, "low_contrast_ratio": 0.0}

    monkeypatch.setattr(ppt_visual_qa, "audit_rendered_slides", _fake_audit_rendered_slides)
    monkeypatch.setattr(
        ppt_visual_qa,
        "run_markitdown_text_qa",
        lambda *_args, **_kwargs: {
            "enabled": True,
            "ok": True,
            "line_count": 8,
            "text_length": 180,
            "placeholder_hits": 2,
            "placeholder_ratio": 0.25,
            "issue_codes": ["markitdown_placeholder_text"],
        },
    )

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    persisted_observability = []
    monkeypatch.setattr(
        ppt_service,
        "_persist_ppt_observability_report",
        lambda payload: persisted_observability.append(payload),
    )

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="结论",
                elements=[SlideElement(type="text", content="证据", block_id="b1")],
                narration="n1",
                duration=120,
            ),
            SlideContent(
                slide_id="s2",
                title="补充",
                elements=[SlideElement(type="text", content="n2", block_id="b2")],
                narration="n2",
                duration=120,
            ),
        ],
        title="Deck",
        author="AutoViralVid",
        route_mode="standard",
    )

    result = await PPTService().export_pptx(req)

    text_qa = result.get("observability_report", {}).get("text_qa")
    assert isinstance(text_qa, dict)
    assert text_qa.get("page_number_discontinuous") is True
    codes = {str(item.get("code")) for item in result.get("alerts", [])}
    assert "text_qa_page_number_discontinuous" in codes
    assert "text_qa_placeholder_ratio_high" in codes
    assert "text_qa_assertion_coverage_low" in codes
    assert "text_qa_evidence_coverage_low" in codes
    assert "text_qa_markitdown_placeholder_ratio_high" in codes
    issue_codes = set(result.get("observability_report", {}).get("issue_codes") or [])
    assert "placeholder_text" in issue_codes
    assert "missing_assertion_title" in issue_codes
    assert "assertion_not_covered" in issue_codes
    assert "evidence_not_fully_covered" in issue_codes
    assert "markitdown_placeholder_text" in issue_codes
    assert (
        result.get("observability_report", {})
        .get("text_qa", {})
        .get("markitdown", {})
        .get("ok")
        is True
    )
    assert persisted_observability
    persisted_diag = persisted_observability[-1].get("diagnostics") or []
    assert any(item.get("status") == "text_qa_summary" for item in persisted_diag if isinstance(item, dict))


def test_build_image_video_slides_presigns_r2_public_urls(monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE", "https://s.autoviralvid.com")
    monkeypatch.setenv("R2_BUCKET", "autoviralvid")

    class _FakeR2:
        def generate_presigned_url(self, method, Params, ExpiresIn):
            assert method == "get_object"
            assert Params["Bucket"] == "autoviralvid"
            assert Params["Key"] == "projects/p1/slides/slide_001.png"
            assert ExpiresIn >= 3600
            return "https://signed.example.com/slide_001.png"

    monkeypatch.setattr("src.r2.get_r2_client", lambda: _FakeR2())

    slides = ppt_service._build_image_video_slides(
        ["https://s.autoviralvid.com/projects/p1/slides/slide_001.png"],
        [{"duration": 6}],
    )

    assert len(slides) == 1
    assert slides[0]["imageUrl"] == "https://signed.example.com/slide_001.png"


def test_presign_allows_known_domain_without_r2_public_base(monkeypatch):
    monkeypatch.delenv("R2_PUBLIC_BASE", raising=False)
    monkeypatch.delenv("R2_PUBLIC_HOSTS", raising=False)
    monkeypatch.setenv("R2_BUCKET", "autoviralvid")

    class _FakeR2:
        def generate_presigned_url(self, method, Params, ExpiresIn):
            assert method == "get_object"
            assert Params["Bucket"] == "autoviralvid"
            assert Params["Key"] == "projects/p2/slides/slide_002.png"
            assert ExpiresIn >= 3600
            return "https://signed.example.com/slide_002.png"

    monkeypatch.setattr("src.r2.get_r2_client", lambda: _FakeR2())

    signed = ppt_service._presign_r2_get_url_if_needed(
        "https://s.autoviralvid.com/projects/p2/slides/slide_002.png"
    )
    assert signed == "https://signed.example.com/slide_002.png"


def test_presign_skips_existing_signed_url(monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE", "https://s.autoviralvid.com")

    class _FakeR2:
        def generate_presigned_url(self, method, Params, ExpiresIn):  # pragma: no cover
            raise AssertionError("should not be called for already signed URL")

    monkeypatch.setattr("src.r2.get_r2_client", lambda: _FakeR2())

    existing = (
        "https://s.autoviralvid.com/projects/p3/slides/slide_003.png?"
        "X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc123"
    )
    assert ppt_service._presign_r2_get_url_if_needed(existing) == existing


def test_fetch_image_data_uri_sync_remote_disconnect_returns_empty(monkeypatch):
    from http.client import RemoteDisconnected

    def _raise_remote_disconnect(*_args, **_kwargs):
        raise RemoteDisconnected("Remote end closed connection without response")

    monkeypatch.setattr(ppt_service.urllib_request, "urlopen", _raise_remote_disconnect)
    assert (
        ppt_service._fetch_image_data_uri_sync("https://example.com/image.jpg")
        == ""
    )


@pytest.mark.asyncio
async def test_search_serper_images_returns_empty_on_exception(monkeypatch):
    def _raise_search_error(*_args, **_kwargs):
        raise RuntimeError("search failed")

    monkeypatch.setattr(ppt_service, "_search_serper_images_sync", _raise_search_error)
    result = await ppt_service._search_serper_images(
        query="cnc machine",
        api_key="dummy-key",
        num=3,
    )
    assert result == []


@pytest.mark.asyncio
async def test_schema_invalid_retries_failed_slide_only(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_visual_qa as ppt_visual_qa
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2
    from src.minimax_exporter import MiniMaxExportError
    from src.ppt_failure_classifier import classify_failure

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_PARTIAL_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "2")

    async def _fake_sleep(_seconds):
        return None

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)

    calls = []

    def _fake_export(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        if len(calls) == 1:
            raise MiniMaxExportError(
                message="schema invalid",
                classification=classify_failure("schema invalid"),
                detail="Render contract invalid: slides[0].blocks[1].content is required",
            )
        return {
            "pptx_bytes": b"ok",
            "generator_meta": {"render_slides": 1},
            "render_spec": {"mode": "minimax_presentation", "slides": [{"slide_id": "s1", "slide_type": "split_2"}]},
            "input_payload": {
                "slides": [
                    {"slide_id": "s1", "title": "Intro", "elements": [{"type": "text", "content": "hello"}]}
                ]
            },
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: [b"png-bytes"])
    async def _fake_audit_rendered_slides(*_args, **_kwargs):
        return {"slide_count": 1, "blank_slide_ratio": 0.0, "low_contrast_ratio": 0.0}
    monkeypatch.setattr(ppt_visual_qa, "audit_rendered_slides", _fake_audit_rendered_slides)

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Intro",
                elements=[SlideElement(type="text", content="hello", block_id="b1")],
                narration="hello",
                duration=120,
            )
        ],
        title="Deck",
        author="AutoViralVid",
        retry_scope="deck",
        route_mode="standard",
    )

    result = await PPTService().export_pptx(req)

    assert result["attempts"] == 2
    assert len(calls) == 3
    assert calls[1]["retry_scope"] == "slide"
    assert calls[1]["target_slide_ids"] == ["s1"]
    assert calls[2]["retry_scope"] == "deck"
    assert calls[2]["target_slide_ids"] == []


@pytest.mark.asyncio
async def test_retry_flow_downgrades_render_path_until_png_fallback(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.ppt_visual_qa as ppt_visual_qa
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2
    from src.minimax_exporter import MiniMaxExportError
    from src.ppt_failure_classifier import classify_failure

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_PARTIAL_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "3")

    async def _fake_sleep(_seconds):
        return None

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)

    calls = []

    def _fake_export(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        if len(calls) == 1:
            raise MiniMaxExportError(
                message="schema invalid",
                classification=classify_failure("schema invalid"),
                detail="Render contract invalid: slides[0].blocks[0].content is required",
            )
        if len(calls) == 2:
            raise MiniMaxExportError(
                message="timeout",
                classification=classify_failure("timeout"),
                detail="subprocess.TimeoutExpired: render timeout",
            )
        return {
            "pptx_bytes": b"ok",
            "generator_meta": {"render_slides": 1},
            "render_spec": {"mode": "minimax_presentation", "slides": [{"slide_id": "s1", "slide_type": "split_2"}]},
            "input_payload": {
                "slides": [
                    {"slide_id": "s1", "title": "Intro", "elements": [{"type": "text", "content": "hello"}]}
                ]
            },
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(
        quality_gate,
        "validate_deck",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )
    monkeypatch.setattr(
        quality_gate,
        "validate_layout_diversity",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )
    monkeypatch.setattr(
        quality_gate,
        "validate_visual_audit",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )
    monkeypatch.setattr(pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: [b"png-bytes"])

    async def _fake_audit_rendered_slides(*_args, **_kwargs):
        return {"slide_count": 1, "blank_slide_ratio": 0.0, "low_contrast_ratio": 0.0}

    monkeypatch.setattr(ppt_visual_qa, "audit_rendered_slides", _fake_audit_rendered_slides)

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Intro",
                elements=[SlideElement(type="text", content="hello", block_id="b1")],
                narration="hello",
                duration=120,
            )
        ],
        title="Deck",
        author="AutoViralVid",
        retry_scope="deck",
        route_mode="standard",
    )

    result = await PPTService().export_pptx(req)

    assert result["attempts"] == 3
    assert len(calls) == 4
    assert calls[1]["retry_scope"] == "slide"
    assert calls[2]["retry_scope"] == "slide"
    assert calls[3]["retry_scope"] == "deck"

    first_retry_slide = calls[1]["slides"][0]
    second_retry_slide = calls[2]["slides"][0]
    assert first_retry_slide["render_path"] == "svg"
    assert second_retry_slide["render_path"] == "png_fallback"
    assert second_retry_slide["svg_fallback_png"] is True


@pytest.mark.asyncio
async def test_fast_route_skips_rasterization_and_uses_single_attempt(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "5")

    calls = []

    def _fake_export(**kwargs):
        calls.append(kwargs)
        return {
            "pptx_bytes": b"pptx-fast",
            "generator_meta": {"render_slides": 1},
            "render_spec": {"mode": "minimax_presentation", "slides": [{"slide_id": "s1", "slide_type": "split_2"}]},
            "input_payload": {"slides": [{"slide_id": "s1", "title": "Fast", "elements": [{"type": "text", "content": "ok"}]}]},
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(quality_gate, "validate_deck", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(quality_gate, "validate_layout_diversity", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(
        pptx_rasterizer,
        "rasterize_pptx_bytes_to_png_bytes",
        lambda _pptx: (_ for _ in ()).throw(AssertionError("fast mode should not rasterize")),
    )

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Fast",
                elements=[SlideElement(type="text", content="ok", block_id="b1")],
                narration="ok",
                duration=120,
            )
        ],
        title="Fast Deck",
        author="AutoViralVid",
        route_mode="fast",
    )
    result = await PPTService().export_pptx(req)
    assert result["attempts"] == 1
    assert result["route_mode"] == "fast"
    assert len(calls) == 1
    assert calls[0]["route_mode"] == "fast"


@pytest.mark.asyncio
async def test_layout_gate_uses_input_payload_when_render_spec_lacks_layout_metadata(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.ppt_visual_qa as ppt_visual_qa
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "2")

    def _fake_export(**_kwargs):
        return {
            "pptx_bytes": b"pptx-layout-fallback",
            "generator_meta": {"render_slides": 8},
            "render_spec": {
                "mode": "minimax_presentation",
                "slides": [{"slide_id": f"r{i}", "slide_type": "quote_stat"} for i in range(8)],
            },
            "input_payload": {
                "slides": [
                    {"slide_id": "s1", "title": "Cover", "slide_type": "cover", "layout_grid": "hero_1", "elements": [{"type": "text", "content": "cover"}]},
                    {"slide_id": "s2", "title": "A", "slide_type": "content", "layout_grid": "grid_3", "elements": [{"type": "text", "content": "a"}]},
                    {"slide_id": "s3", "title": "B", "slide_type": "content", "layout_grid": "grid_4", "elements": [{"type": "text", "content": "b"}]},
                    {"slide_id": "s4", "title": "C", "slide_type": "content", "layout_grid": "bento_5", "elements": [{"type": "text", "content": "c"}]},
                    {"slide_id": "s5", "title": "D", "slide_type": "content", "layout_grid": "hero_1", "elements": [{"type": "text", "content": "d"}]},
                    {"slide_id": "s6", "title": "E", "slide_type": "content", "layout_grid": "bento_6", "elements": [{"type": "text", "content": "e"}]},
                    {"slide_id": "s7", "title": "F", "slide_type": "content", "layout_grid": "grid_3", "elements": [{"type": "text", "content": "f"}]},
                    {"slide_id": "s8", "title": "Summary", "slide_type": "summary", "layout_grid": "hero_1", "elements": [{"type": "text", "content": "summary"}]},
                ]
            },
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(quality_gate, "validate_deck", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(
        pptx_rasterizer,
        "rasterize_pptx_bytes_to_png_bytes",
        lambda _pptx: [b"png-bytes"],
    )
    async def _fake_audit_rendered_slides(*_args, **_kwargs):
        return {"slide_count": 1, "blank_slide_ratio": 0.0, "low_contrast_ratio": 0.0}
    monkeypatch.setattr(ppt_visual_qa, "audit_rendered_slides", _fake_audit_rendered_slides)

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id=f"s{i}",
                title=f"Slide {i}",
                elements=[SlideElement(type="text", content="ok", block_id=f"b{i}")],
                narration="ok",
                duration=120,
            )
            for i in range(1, 9)
        ],
        title="Layout fallback",
        author="AutoViralVid",
        route_mode="standard",
        quality_profile="high_density_consulting",
    )
    result = await PPTService().export_pptx(req)
    assert result["attempts"] == 1
    assert result["route_mode"] == "standard"


@pytest.mark.asyncio
async def test_standard_route_requires_native_rasterization(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.pptx_rasterizer as pptx_rasterizer
    from src.minimax_exporter import MiniMaxExportError

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "1")

    def _fake_export(**_kwargs):
        return {
            "pptx_bytes": b"pptx-no-raster",
            "generator_meta": {"render_slides": 1},
            "render_spec": {"mode": "minimax_presentation", "slides": [{"slide_id": "s1", "slide_type": "split_2"}]},
            "input_payload": {"slides": [{"slide_id": "s1", "title": "Intro", "elements": [{"type": "text", "content": "ok"}]}]},
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(quality_gate, "validate_deck", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(quality_gate, "validate_layout_diversity", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: [])

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Intro",
                elements=[SlideElement(type="text", content="ok", block_id="b1")],
                narration="ok",
                duration=120,
            )
        ],
        title="Native raster required",
        author="AutoViralVid",
        route_mode="standard",
    )

    with pytest.raises(MiniMaxExportError) as exc:
        await PPTService().export_pptx(req)
    assert "rasterization" in str(exc.value).lower()
