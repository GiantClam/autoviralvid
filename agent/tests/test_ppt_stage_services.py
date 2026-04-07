from __future__ import annotations

import pytest

from src.ppt_executor_service import PPTExecutorService
from src.ppt_strategist_service import PPTStrategistService
from src.schemas.ppt_outline import OutlinePlanRequest
from src.schemas.ppt_plan import PresentationPlanRequest
from src.schemas.ppt_research import ResearchRequest


class _Delegate:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_research_context(self, req):
        _ = req
        self.calls.append("research")
        return "research-ok"

    async def generate_outline_plan(self, req):
        _ = req
        self.calls.append("outline")
        return "outline-ok"

    async def generate_presentation_plan(self, req):
        _ = req
        self.calls.append("presentation")
        return "presentation-ok"


@pytest.mark.asyncio
async def test_stage_services_delegate_calls():
    delegate = _Delegate()
    strategist = PPTStrategistService(delegate=delegate)
    executor = PPTExecutorService(delegate=delegate)

    research = await strategist.generate_research_context(ResearchRequest(topic="AI"))
    outline = await strategist.generate_outline_plan(
        OutlinePlanRequest.model_construct(research=research, total_pages=3)
    )
    plan = await executor.generate_presentation_plan(
        PresentationPlanRequest.model_construct(outline=outline, research=research)
    )

    assert research == "research-ok"
    assert outline == "outline-ok"
    assert plan == "presentation-ok"
    assert delegate.calls == ["research", "outline", "presentation"]

