from __future__ import annotations

import pytest

from src.ppt_pipeline_graph import run_stage13_graph
from src.schemas.ppt_outline import OutlinePlan, StickyNote
from src.schemas.ppt_pipeline import PPTPipelineRequest
from src.schemas.ppt_plan import ContentBlock, PresentationPlan, SlidePlan, SlideContentStrategy
from src.schemas.ppt_research import ResearchContext, ResearchQuestion


def _build_research() -> ResearchContext:
    return ResearchContext(
        topic="AI deck",
        language="en-US",
        audience="leaders",
        purpose="briefing",
        style_preference="professional",
        key_data_points=["k1", "k2", "k3"],
        reference_materials=[{"title": "r1", "url": "https://example.com"}],
        completeness_score=0.8,
        enrichment_strategy="none",
        questions=[
            ResearchQuestion(question="Who is the audience?", category="audience", why="context"),
            ResearchQuestion(question="What is the goal?", category="purpose", why="direction"),
            ResearchQuestion(question="What data is needed?", category="data", why="evidence"),
        ],
    )


def _build_outline(research: ResearchContext) -> OutlinePlan:
    _ = research
    return OutlinePlan(
        title="AI deck",
        total_pages=3,
        theme_suggestion="business_authority",
        style_suggestion="soft",
        logic_flow="cover to content to summary",
        notes=[
            StickyNote(page_number=1, core_message="Cover", layout_hint="cover", key_points=["a", "b", "c"]),
            StickyNote(page_number=2, core_message="Core", layout_hint="split_2", key_points=["a", "b", "c"]),
            StickyNote(page_number=3, core_message="Summary", layout_hint="summary", key_points=["a", "b", "c"]),
        ],
    )


def _build_plan() -> PresentationPlan:
    slides = []
    for idx, slide_type in enumerate(["cover", "content", "summary"], start=1):
        slides.append(
            SlidePlan(
                page_number=idx,
                slide_type=slide_type,  # type: ignore[arg-type]
                layout_grid="cover" if idx == 1 else ("split_2" if idx == 2 else "summary"),
                blocks=[
                    ContentBlock(block_type="title", position="top", content=f"Slide {idx}", emphasis=[]),
                    ContentBlock(block_type="body", position="center", content="content body", emphasis=[]),
                ],
                bg_style="light",
                content_strategy=SlideContentStrategy(
                    assertion=f"assert {idx}",
                    evidence=["e1"],
                    page_role="argument" if idx < 3 else "summary",
                    render_path="svg",
                ),
            )
        )
    return PresentationPlan(
        title="AI deck",
        theme="business_authority",
        style="soft",
        slides=slides,
        global_notes="flow",
    )


@pytest.mark.asyncio
async def test_stage13_graph_runs_in_strict_serial_order():
    order: list[str] = []

    async def _research_builder(_req):
        order.append("research")
        return _build_research()

    async def _outline_builder(req):
        order.append("outline")
        return _build_outline(req.research)

    async def _presentation_builder(_req):
        order.append("presentation")
        return _build_plan()

    state = await run_stage13_graph(
        request=PPTPipelineRequest(topic="AI deck", language="en-US", total_pages=3),
        research_builder=_research_builder,
        outline_builder=_outline_builder,
        presentation_builder=_presentation_builder,
    )

    assert order == ["research", "outline", "presentation"]
    assert state.get("stage") == "complete"
    assert state.get("research") is not None
    assert state.get("outline") is not None
    assert state.get("presentation") is not None

