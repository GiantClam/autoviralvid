from __future__ import annotations

import pytest

from src.ppt_service_v2 import PPTService
from src.ppt_v2_pipeline import PPTV2Pipeline
from src.schemas.ppt_outline import OutlinePlan
from src.schemas.ppt_pipeline import (
    PPTPipelineArtifacts,
    PPTPipelineRequest,
    PPTPipelineResult,
    PPTPipelineStageStatus,
)
from src.schemas.ppt_plan import PresentationPlan
from src.schemas.ppt_research import ResearchContext


def _build_result(*, stage_order: list[str], export: dict | None) -> PPTPipelineResult:
    research = ResearchContext.model_construct(
        topic="t",
        language="en-US",
        audience="a",
        purpose="p",
        style_preference="s",
        questions=[],
        key_data_points=[],
        reference_materials=[],
        evidence=[],
        gap_report=[],
        completeness_score=1.0,
        enrichment_strategy="none",
    )
    outline = OutlinePlan.model_construct(
        title="t",
        total_pages=1,
        theme_suggestion="business_authority",
        style_suggestion="soft",
        logic_flow="flow",
        notes=[],
    )
    presentation = PresentationPlan.model_construct(
        title="t",
        theme="business_authority",
        style="soft",
        slides=[],
        global_notes="flow",
    )
    artifacts = PPTPipelineArtifacts.model_construct(
        research=research,
        outline_plan=outline,
        presentation_plan=presentation,
        render_payload={},
    )
    stages = [
        PPTPipelineStageStatus.model_construct(
            stage=stage,
            ok=True,
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:00:00Z",
            diagnostics=[],
        )
        for stage in stage_order
    ]
    return PPTPipelineResult.model_construct(
        run_id="rid",
        stages=stages,
        artifacts=artifacts,
        export=export,
    )


@pytest.mark.asyncio
async def test_v2_pipeline_adds_export_metadata():
    async def _runner(_req):
        return _build_result(
            stage_order=[
                "research",
                "outline_plan",
                "presentation_plan",
                "quality_gate",
                "export",
            ],
            export={"url": "https://example.com/pptx"},
        )

    out = await PPTV2Pipeline(v1_runner=_runner).run(PPTPipelineRequest(topic="deck"))
    assert isinstance(out.export, dict)
    meta = out.export.get("pipeline_v2") or {}
    assert meta.get("enabled") is True
    assert meta.get("engine") == "drawingml_core"
    assert meta.get("adapter_mode") == "v1_bridge"


@pytest.mark.asyncio
async def test_v2_pipeline_rejects_non_serial_stage_order():
    async def _runner(_req):
        return _build_result(
            stage_order=[
                "research",
                "presentation_plan",
                "outline_plan",
                "quality_gate",
                "export",
            ],
            export={},
        )

    with pytest.raises(ValueError, match="stage order mismatch"):
        await PPTV2Pipeline(v1_runner=_runner).run(PPTPipelineRequest(topic="deck"))


@pytest.mark.asyncio
async def test_service_routes_between_v1_and_v2_by_env(monkeypatch):
    svc = PPTService()

    async def _fake_v1(_req):
        return _build_result(
            stage_order=[
                "research",
                "outline_plan",
                "presentation_plan",
                "quality_gate",
                "export",
            ],
            export={"url": "https://example.com/v1"},
        )

    monkeypatch.setattr(svc, "_run_ppt_pipeline_v1", _fake_v1)

    monkeypatch.setenv("PPT_PIPELINE_V2_ENABLED", "false")
    out_v1 = await svc.run_ppt_pipeline(PPTPipelineRequest(topic="deck-v1"))
    assert isinstance(out_v1.export, dict)
    assert "pipeline_v2" not in out_v1.export

    monkeypatch.setenv("PPT_PIPELINE_V2_ENABLED", "true")
    out_v2 = await svc.run_ppt_pipeline(PPTPipelineRequest(topic="deck-v2"))
    assert isinstance(out_v2.export, dict)
    assert out_v2.export.get("pipeline_v2", {}).get("enabled") is True


