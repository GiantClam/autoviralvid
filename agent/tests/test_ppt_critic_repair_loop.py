import copy

import pytest

from src.ppt_quality_gate import QualityIssue, QualityResult, QualityScoreResult
from src.schemas.ppt import ExportRequest, SlideContent, SlideElement
from src.ppt_service import PPTService


@pytest.mark.asyncio
async def test_visual_critic_patch_applies_before_retry(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.ppt_service as ppt_service
    import src.ppt_visual_qa as ppt_visual_qa
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_PARTIAL_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("PPT_VISUAL_CRITIC_REPAIR_ENABLED", "true")

    async def _fake_sleep(_seconds):
        return None

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)
    monkeypatch.setattr(ppt_service, "_apply_skill_planning_to_render_payload", lambda payload, **_kwargs: payload)
    monkeypatch.setattr(ppt_service, "_apply_visual_orchestration", lambda payload, **_kwargs: payload)

    async def _fake_hydrate(payload):
        return payload

    monkeypatch.setattr(ppt_service, "_hydrate_image_assets", _fake_hydrate)

    export_calls = []

    def _fake_export(**kwargs):
        export_calls.append(copy.deepcopy(kwargs))
        return {
            "pptx_bytes": b"pptx",
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
            "is_full_deck": True,
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(quality_gate, "validate_deck", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(quality_gate, "validate_layout_diversity", lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]))
    monkeypatch.setattr(
        quality_gate,
        "score_deck_quality",
        lambda *_args, **_kwargs: QualityScoreResult(
            score=92.0,
            passed=True,
            threshold=75.0,
            warn_threshold=68.0,
            dimensions={},
            issue_counts={},
            diagnostics={},
        ),
    )
    monkeypatch.setattr(pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: [b"png"])

    async def _fake_audit_rendered_slides(*_args, **_kwargs):
        return {
            "slide_count": 1,
            "blank_slide_ratio": 0.0,
            "low_contrast_ratio": 0.35,
            "slides": [
                {
                    "slide": 1,
                    "local_issues": ["low_contrast"],
                    "multimodal_issues": ["card_overlap"],
                    "contrast": 10.0,
                    "edge_density": 0.05,
                    "mean_luminance": 135.0,
                }
            ],
        }

    monkeypatch.setattr(ppt_visual_qa, "audit_rendered_slides", _fake_audit_rendered_slides)

    validate_visual_calls = {"count": 0}

    def _fake_validate_visual_audit(*_args, **_kwargs):
        validate_visual_calls["count"] += 1
        if validate_visual_calls["count"] == 1:
            return QualityResult(
                ok=False,
                issues=[
                    QualityIssue(
                        slide_id="s1",
                        code="visual_low_contrast_ratio_high",
                        message="contrast too low",
                        retry_scope="slide",
                        retry_target_ids=["s1"],
                    )
                ],
            )
        return QualityResult(ok=True, issues=[])

    monkeypatch.setattr(quality_gate, "validate_visual_audit", _fake_validate_visual_audit)

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
    assert len(export_calls) == 2
    # second attempt should carry visual critic mutations
    retry_slides = export_calls[1]["slides"]
    assert isinstance(retry_slides, list) and retry_slides
    patched_slide = retry_slides[0]
    assert bool((patched_slide.get("visual") or {}).get("critic_repair", {}).get("enabled")) is True
    assert bool((patched_slide.get("visual") or {}).get("force_high_contrast")) is True
    statuses = [str(row.get("status")) for row in result.get("diagnostics", []) if isinstance(row, dict)]
    assert "visual_critic_patch" in statuses

