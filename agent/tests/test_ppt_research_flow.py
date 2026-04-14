import pytest

from src.ppt_service_v2 import PPTService
from src.schemas.ppt_outline import OutlinePlanRequest
from src.schemas.ppt_plan import PresentationPlanRequest
from src.schemas.ppt_research import ResearchRequest


@pytest.mark.asyncio
async def test_generate_research_context_returns_minimum_fields():
    svc = PPTService()
    ctx = await svc.generate_research_context(
        ResearchRequest(
            topic="AI governance for enterprises",
            audience="strategy leaders",
            purpose="decision briefing",
            style_preference="professional",
            web_enrichment=False,
        )
    )

    assert ctx.topic == "AI governance for enterprises"
    assert len(ctx.key_data_points) >= 3
    assert len(ctx.reference_materials) >= 1
    assert ctx.completeness_score >= 0.5


@pytest.mark.asyncio
async def test_outline_plan_has_cover_and_summary():
    svc = PPTService()
    research = await svc.generate_research_context(
        ResearchRequest(topic="Market outlook", web_enrichment=False)
    )

    outline = await svc.generate_outline_plan(
        OutlinePlanRequest(research=research, total_pages=8)
    )

    assert outline.total_pages == 8
    assert outline.notes[0].layout_hint == "cover"
    assert outline.notes[-1].layout_hint == "summary"


@pytest.mark.asyncio
async def test_presentation_plan_matches_outline_length_and_title_blocks():
    svc = PPTService()
    research = await svc.generate_research_context(
        ResearchRequest(topic="Energy security", web_enrichment=False)
    )
    outline = await svc.generate_outline_plan(
        OutlinePlanRequest(research=research, total_pages=6)
    )

    plan = await svc.generate_presentation_plan(
        PresentationPlanRequest(outline=outline, research=research)
    )

    assert len(plan.slides) == len(outline.notes)
    for slide in plan.slides:
        assert any(block.block_type == "title" for block in slide.blocks)
