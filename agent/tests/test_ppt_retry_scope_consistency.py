import pytest
from pydantic import ValidationError

from src.ppt_quality_gate import QualityResult, QualityScoreResult
from src.ppt_service_v2 import PPTService
from src.schemas.ppt import ExportRequest, SlideContent, SlideElement
from src.schemas.ppt_pipeline import PPTPipelineRequest


def test_export_request_rejects_non_deck_retry_scope():
    with pytest.raises(ValidationError):
        ExportRequest(
            slides=[],
            title="Deck",
            author="AutoViralVid",
            retry_scope="slide",
        )


def test_export_request_rejects_remote_export_channel():
    with pytest.raises(ValidationError):
        ExportRequest(
            slides=[],
            title="Deck",
            author="AutoViralVid",
            export_channel="remote",
        )


def test_pipeline_request_rejects_remote_export_channel():
    with pytest.raises(ValidationError):
        PPTPipelineRequest(
            topic="Deck Topic",
            export_channel="remote",
        )


@pytest.mark.asyncio
async def test_export_pptx_normalizes_retry_scope_to_deck(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.ppt_service_v2 as ppt_service
    import src.ppt_visual_qa as ppt_visual_qa
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    calls = []

    def _fake_export(**kwargs):
        calls.append(dict(kwargs))
        return {
            "pptx_bytes": b"ok",
            "generator_meta": {"render_slides": 1},
            "render_spec": {
                "mode": "minimax_presentation",
                "slides": [{"slide_id": "s1", "slide_type": "split_2"}],
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
            "is_full_deck": True,
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    monkeypatch.setattr(ppt_service, "_run_layer1_design_skill_chain", lambda **_kwargs: {})
    monkeypatch.setattr(
        ppt_service,
        "_apply_skill_planning_to_render_payload",
        lambda payload, **_kwargs: payload,
    )
    monkeypatch.setattr(ppt_service, "_require_direct_skill_runtime", lambda: False)
    monkeypatch.setattr(
        quality_gate, "validate_deck", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[])
    )
    monkeypatch.setattr(
        quality_gate, "validate_layout_diversity", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[])
    )
    monkeypatch.setattr(
        quality_gate, "validate_visual_audit", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[])
    )
    monkeypatch.setattr(
        quality_gate,
        "score_deck_quality",
        lambda *_args, **_kwargs: QualityScoreResult(
            score=90.0,
            passed=True,
            threshold=75.0,
            warn_threshold=82.0,
            dimensions={},
            issue_counts={},
            diagnostics={},
        ),
    )
    monkeypatch.setattr(pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: [])
    async def _fake_audit_rendered_slides(*_args, **_kwargs):
        return {
            "slide_count": 1,
            "blank_slide_ratio": 0.0,
            "low_contrast_ratio": 0.0,
        }

    monkeypatch.setattr(ppt_visual_qa, "audit_rendered_slides", _fake_audit_rendered_slides)
    monkeypatch.setattr(
        r2, "upload_bytes_to_r2", lambda _bytes, key, content_type: f"https://example.com/{key}"
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
        route_mode="fast",
        retry_scope="deck",
        target_slide_ids=["s1"],
        target_block_ids=["b1"],
    )
    result = await PPTService().export_pptx(req)

    assert calls
    assert calls[0]["retry_scope"] == "deck"
    assert calls[0]["target_slide_ids"] == []
    assert calls[0]["target_block_ids"] == []
    assert result["retry_scope"] == "deck"
    assert result.get("retry_target_ids", []) == []


