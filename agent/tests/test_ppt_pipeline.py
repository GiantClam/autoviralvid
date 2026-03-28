import pytest

from src.ppt_service import PPTService
from src.schemas.ppt_pipeline import PPTPipelineRequest


@pytest.mark.asyncio
async def test_run_ppt_pipeline_without_export():
    svc = PPTService()

    result = await svc.run_ppt_pipeline(
        PPTPipelineRequest(
            topic="灵创智能企业介绍",
            audience="投资人",
            purpose="融资路演",
            style_preference="professional",
            constraints=["10页以内", "15分钟"],
            total_pages=8,
            with_export=False,
            save_artifacts=False,
        )
    )

    assert result.run_id
    assert [stage.stage for stage in result.stages] == [
        "research",
        "outline_plan",
        "presentation_plan",
        "quality_gate",
        "export",
    ]
    assert all(stage.ok for stage in result.stages)
    assert result.stages[-1].diagnostics == ["skipped by request"]
    assert result.export is None
    assert len(result.artifacts.presentation_plan.slides) == 8
    assert len(result.artifacts.render_payload["slides"]) == 8
    assert result.artifacts.render_payload.get("svg_mode") == "on"
    assert all(
        str(slide.get("slide_type") or "").lower()
        not in {"split_2", "asymmetric_2", "grid_2", "grid_3", "grid_4", "bento_5", "bento_6", "timeline"}
        for slide in result.artifacts.render_payload["slides"]
    )
    assert all(
        str(slide.get("bg_style") or "").lower() == "dark"
        for slide in result.artifacts.render_payload["slides"]
    )


@pytest.mark.asyncio
async def test_run_ppt_pipeline_quality_gate_fails_when_plan_is_empty(monkeypatch):
    svc = PPTService()

    from src.ppt_quality_gate import QualityIssue, QualityResult

    def _force_quality_fail(_slides, **_kwargs):
        return QualityResult(
            ok=False,
            issues=[
                QualityIssue(
                    slide_id="slide-1",
                    code="blank_area_high",
                    message="forced failure",
                    retry_scope="slide",
                    retry_target_ids=["slide-1"],
                )
            ],
        )

    monkeypatch.setattr("src.ppt_quality_gate.validate_deck", _force_quality_fail)

    with pytest.raises(ValueError, match="Quality gate failed"):
        await svc.run_ppt_pipeline(
            PPTPipelineRequest(
                topic="AI工作流平台",
                total_pages=6,
                with_export=False,
                save_artifacts=False,
            )
        )
