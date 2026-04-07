"""Thin strategist service for research and outline planning stages."""

from __future__ import annotations

from typing import Any

from src.schemas.ppt_outline import OutlinePlan, OutlinePlanRequest
from src.schemas.ppt_research import ResearchContext, ResearchRequest


class PPTStrategistService:
    """Facade over strategist-facing stage methods."""

    def __init__(self, *, delegate: Any) -> None:
        self._delegate = delegate

    async def generate_research_context(
        self, req: ResearchRequest
    ) -> ResearchContext:
        return await self._delegate.generate_research_context(req)

    async def generate_outline_plan(self, req: OutlinePlanRequest) -> OutlinePlan:
        return await self._delegate.generate_outline_plan(req)

