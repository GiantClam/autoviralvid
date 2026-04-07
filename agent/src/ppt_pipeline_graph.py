"""Strict serial pipeline graph for PPT Stage 1-3 orchestration."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from src.schemas.ppt_outline import OutlinePlan, OutlinePlanRequest
from src.schemas.ppt_pipeline import PPTPipelineRequest
from src.schemas.ppt_plan import PresentationPlan, PresentationPlanRequest
from src.schemas.ppt_research import ResearchContext, ResearchRequest


class PPTPipelineState(TypedDict, total=False):
    stage: str
    request: PPTPipelineRequest
    research: ResearchContext
    outline: OutlinePlan
    presentation: PresentationPlan


ResearchBuilder = Callable[[ResearchRequest], Awaitable[ResearchContext]]
OutlineBuilder = Callable[[OutlinePlanRequest], Awaitable[OutlinePlan]]
PresentationBuilder = Callable[[PresentationPlanRequest], Awaitable[PresentationPlan]]


def build_stage13_graph(
    *,
    research_builder: ResearchBuilder,
    outline_builder: OutlineBuilder,
    presentation_builder: PresentationBuilder,
):
    """Compile a strict serial graph: research -> outline -> presentation."""

    async def _research_node(state: PPTPipelineState) -> PPTPipelineState:
        req = state["request"]
        research = await research_builder(
            ResearchRequest(
                topic=req.topic,
                language=req.language,
                audience=req.audience,
                purpose=req.purpose,
                style_preference=req.style_preference,
                constraints=req.constraints,
                required_facts=req.required_facts,
                geography=req.geography,
                time_range=req.time_range,
                domain_terms=req.domain_terms,
                web_enrichment=req.web_enrichment,
                min_completeness=req.research_min_completeness,
                desired_citations=req.desired_citations,
                max_web_queries=req.max_web_queries,
                max_search_results=req.max_search_results,
            )
        )
        return {"research": research, "stage": "outline"}

    async def _outline_node(state: PPTPipelineState) -> PPTPipelineState:
        req = state["request"]
        outline = await outline_builder(
            OutlinePlanRequest(
                research=state["research"],
                total_pages=req.total_pages,
            )
        )
        return {"outline": outline, "stage": "presentation"}

    async def _presentation_node(state: PPTPipelineState) -> PPTPipelineState:
        presentation = await presentation_builder(
            PresentationPlanRequest(
                outline=state["outline"],
                research=state["research"],
            )
        )
        return {"presentation": presentation, "stage": "complete"}

    graph = StateGraph(PPTPipelineState)
    graph.add_node("research", _research_node)
    graph.add_node("outline", _outline_node)
    graph.add_node("presentation", _presentation_node)
    graph.add_edge(START, "research")
    graph.add_edge("research", "outline")
    graph.add_edge("outline", "presentation")
    graph.add_edge("presentation", END)
    return graph.compile()


async def run_stage13_graph(
    *,
    request: PPTPipelineRequest,
    research_builder: ResearchBuilder,
    outline_builder: OutlineBuilder,
    presentation_builder: PresentationBuilder,
) -> PPTPipelineState:
    """Run the compiled stage-1/2/3 serial graph and return terminal state."""
    app = build_stage13_graph(
        research_builder=research_builder,
        outline_builder=outline_builder,
        presentation_builder=presentation_builder,
    )
    out = await app.ainvoke({"request": request, "stage": "research"})
    return dict(out or {})

