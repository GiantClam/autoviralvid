import pytest
from pydantic import ValidationError

import src.ppt_service as ppt_service
from src.ppt_service import PPTService
from src.schemas.ppt_outline import OutlinePlanRequest
from src.schemas.ppt_plan import ContentBlock, PresentationPlanRequest
from src.schemas.ppt_research import ResearchRequest


@pytest.mark.asyncio
async def test_research_outline_plan_flow_contract():
    svc = PPTService()

    research = await svc.generate_research_context(
        ResearchRequest(
            topic="AI marketing automation",
            audience="investors",
            purpose="fundraising pitch",
            style_preference="business",
            constraints=["10 slides", "15 minutes"],
            required_facts=["CAC", "LTV", "pipeline conversion"],
            geography="China",
            time_range="2023-2025",
        )
    )
    assert len(research.key_data_points) >= 5
    assert len(research.reference_materials) >= 3
    assert 0.0 <= research.completeness_score <= 1.0
    assert research.required_facts
    assert isinstance(research.gap_report, list)
    assert research.enrichment_strategy in {"none", "web", "web+fallback"}

    outline = await svc.generate_outline_plan(
        OutlinePlanRequest(research=research, total_pages=8)
    )
    assert outline.total_pages == len(outline.notes)
    assert outline.notes[0].layout_hint == "cover"
    assert outline.notes[-1].layout_hint == "summary"
    for idx in range(1, len(outline.notes)):
        assert outline.notes[idx].layout_hint != outline.notes[idx - 1].layout_hint
    middle_layouts = [str(item.layout_hint) for item in outline.notes[1:-1]]
    for start in range(0, max(0, len(middle_layouts) - 4)):
        window = middle_layouts[start:start + 5]
        assert any(layout in {"hero_1", "cover", "summary", "section", "divider"} for layout in window)

    plan = await svc.generate_presentation_plan(
        PresentationPlanRequest(outline=outline, research=research)
    )
    assert len(plan.slides) == outline.total_pages
    for slide in plan.slides:
        assert any(block.block_type == "title" for block in slide.blocks)
        assert any(block.block_type != "title" for block in slide.blocks)
        assert slide.content_strategy is not None
        title_block = next(block for block in slide.blocks if block.block_type == "title")
        assert title_block.content == slide.content_strategy.assertion
        assert slide.content_strategy.page_role in {"argument", "evidence", "transition", "summary"}
        assert slide.content_strategy.render_path in {"pptxgenjs", "svg"}


def test_content_block_rejects_placeholder_content():
    with pytest.raises(ValidationError):
        ContentBlock(
            block_type="body",
            position="left",
            content="TODO: fill this later",
            emphasis=[],
        )


@pytest.mark.asyncio
async def test_research_uses_serper_when_key_is_configured(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    async def _fake_serper_search(*, query: str, api_key: str, num: int = 5, gl: str = "us", hl: str = "zh-cn"):
        assert api_key == "test-key"
        return [
            {
                "title": f"{query} market report",
                "url": "https://example.com/market-report",
                "snippet": "Market grew 30% year-over-year with strong automation demand.",
            },
            {
                "title": f"{query} benchmark",
                "url": "https://example.com/benchmark",
                "snippet": "Benchmark indicates conversion lift after workflow adoption.",
            },
            {
                "title": f"{query} industry data",
                "url": "https://example.com/industry-data",
                "snippet": "Industry baseline shows higher ROI in data-driven campaigns.",
            },
        ]

    monkeypatch.setattr(ppt_service, "_search_serper_web", _fake_serper_search)

    svc = PPTService()
    research = await svc.generate_research_context(
        ResearchRequest(topic="AI marketing automation")
    )

    assert len(research.reference_materials) >= 3
    assert any("example.com/market-report" in row["url"] for row in research.reference_materials)
    assert any("30%" in point or "ROI" in point for point in research.key_data_points)
    assert research.enrichment_applied is True
    assert any(item.provenance == "web" for item in research.evidence)


@pytest.mark.asyncio
async def test_research_gap_driven_queries_include_required_facts(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    captured_queries = []

    async def _fake_serper_search(*, query: str, api_key: str, num: int = 5, gl: str = "us", hl: str = "zh-cn"):
        captured_queries.append(query)
        return []

    monkeypatch.setattr(ppt_service, "_search_serper_web", _fake_serper_search)

    svc = PPTService()
    research = await svc.generate_research_context(
        ResearchRequest(
            topic="AI marketing automation",
            required_facts=["CAC payback period", "pipeline conversion rate"],
            geography="US",
            time_range="2022-2025",
            web_enrichment=True,
            max_web_queries=3,
        )
    )

    assert captured_queries, "gap-driven enrichment should trigger web queries"
    joined = " | ".join(captured_queries).lower()
    assert "cac payback period" in joined or "pipeline conversion rate" in joined
    assert research.reference_materials
    assert research.completeness_score >= 0.3
