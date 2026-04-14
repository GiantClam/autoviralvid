from pathlib import Path

import pytest

from src.ppt_quality_gate import QualityResult
from src.ppt_service_v2 import PPTService
from src.schemas.ppt_pipeline import PPTPipelineRequest


@pytest.mark.asyncio
async def test_run_ppt_pipeline_without_export_has_expected_stage_order(monkeypatch):
    monkeypatch.setattr(
        "src.ppt_quality_gate.validate_deck",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )

    svc = PPTService()
    result = await svc.run_ppt_pipeline(
        PPTPipelineRequest(
            topic="AI governance strategy",
            total_pages=6,
            quality_profile="lenient_draft",
            web_enrichment=False,
            with_export=False,
            save_artifacts=False,
        )
    )

    stage_order = [stage.stage for stage in result.stages]
    assert stage_order == [
        "research",
        "outline_plan",
        "presentation_plan",
        "quality_gate",
        "export",
    ]
    assert result.export is None
    assert len(result.artifacts.render_payload.get("slides") or []) == 6


@pytest.mark.asyncio
async def test_run_ppt_pipeline_with_export_writes_pptx(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.ppt_quality_gate.validate_deck",
        lambda *_args, **_kwargs: QualityResult(ok=True, issues=[]),
    )

    def _fake_export(**_kwargs):
        return {"pptx_bytes": b"deck-bytes", "slide_image_urls": []}

    monkeypatch.setattr("src.ppt_service_v2.export_minimax_pptx", _fake_export)

    svc = PPTService()
    svc.output_base = tmp_path

    result = await svc.run_ppt_pipeline(
        PPTPipelineRequest(
            topic="International relations briefing",
            total_pages=5,
            quality_profile="lenient_draft",
            web_enrichment=False,
            with_export=True,
            save_artifacts=False,
            route_mode="fast",
        )
    )

    assert isinstance(result.export, dict)
    output_pptx = Path(str(result.export.get("output_pptx") or ""))
    assert output_pptx.exists()
    assert output_pptx.read_bytes() == b"deck-bytes"
