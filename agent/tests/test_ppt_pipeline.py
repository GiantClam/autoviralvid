import pytest

from src.ppt_service_v2 import (
    PPTService,
    _pipeline_export_timeout_sec,
    _resolve_quality_profile_id,
)
from src.schemas.ppt_pipeline import PPTPipelineRequest


@pytest.mark.asyncio
async def test_run_ppt_pipeline_without_export(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    svc = PPTService()

    result = await svc.run_ppt_pipeline(
        PPTPipelineRequest(
            topic="Lingchuang company overview",
            audience="investor audience",
            purpose="fundraising pitch",
            style_preference="professional",
            constraints=["<=10 slides", "<=15 minutes"],
            total_pages=8,
            route_mode="standard",
            quality_profile="lenient_draft",
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
    assert len(result.artifacts.render_payload["slides"]) >= 8
    assert result.artifacts.render_payload.get("svg_mode") == "on"
    runtime = result.artifacts.render_payload.get("skill_planning_runtime")
    assert isinstance(runtime, dict)
    assert runtime.get("enabled") is True
    assert isinstance(runtime.get("slides"), list)
    assert any(
        isinstance(slide, dict)
        and isinstance(slide.get("load_skills"), list)
        and slide.get("load_skills")
        for slide in result.artifacts.render_payload["slides"]
        if isinstance(slide, dict)
    )
    assert all(
        str(slide.get("slide_type") or "").lower()
        not in {"split_2", "asymmetric_2", "grid_2", "grid_3", "grid_4", "bento_5", "bento_6", "timeline"}
        for slide in result.artifacts.render_payload["slides"]
    )
    assert all(
        str(slide.get("bg_style") or "").lower() in {"dark", "light"}
        for slide in result.artifacts.render_payload["slides"]
    )


@pytest.mark.asyncio
async def test_run_ppt_pipeline_quality_gate_fails_when_plan_is_empty(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
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
                topic="AI workflow platform",
                total_pages=6,
                with_export=False,
                save_artifacts=False,
            )
        )


def test_resolve_quality_profile_auto_mapping():
    assert _resolve_quality_profile_id("auto", topic="AI 融资路演", purpose="", audience="", total_pages=8) == "investor_pitch"
    assert _resolve_quality_profile_id("auto", topic="", purpose="季度 status report", audience="", total_pages=8) == "status_report"
    assert _resolve_quality_profile_id("auto", topic="", purpose="新人 training onboarding", audience="", total_pages=8) == "training_deck"
    assert _resolve_quality_profile_id("auto", topic="", purpose="技术评审", audience="", total_pages=8) == "tech_review"
    assert _resolve_quality_profile_id("auto", topic="", purpose="品牌发布会 launch", audience="", total_pages=8) == "marketing_pitch"
    assert _resolve_quality_profile_id("auto", topic="产品介绍", purpose="", audience="", total_pages=18) == "high_density_consulting"
    assert _resolve_quality_profile_id("auto", topic="产品介绍", purpose="", audience="", total_pages=8) == "default"


def test_pipeline_export_timeout_default_cap(monkeypatch):
    monkeypatch.delenv("PPT_PIPELINE_EXPORT_TIMEOUT_SEC", raising=False)
    timeout = _pipeline_export_timeout_sec(slide_count=20, route_mode="standard")
    assert 120 <= timeout <= 540


@pytest.mark.asyncio
async def test_run_ppt_pipeline_research_timeout(monkeypatch):
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "false")
    monkeypatch.setenv("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "false")
    svc = PPTService()

    monkeypatch.setattr(
        "src.ppt_service_v2._pipeline_stage_timeout_sec",
        lambda stage, default: 1 if str(stage).lower() == "research" else default,
    )

    async def _slow_research(_req):
        import asyncio

        await asyncio.sleep(2)
        raise AssertionError("unreachable")

    monkeypatch.setattr(svc, "generate_research_context", _slow_research)

    with pytest.raises(ValueError, match="Research stage timeout"):
        await svc.run_ppt_pipeline(
            PPTPipelineRequest(
                topic="pipeline timeout test",
                total_pages=6,
                with_export=False,
                save_artifacts=False,
            )
        )


