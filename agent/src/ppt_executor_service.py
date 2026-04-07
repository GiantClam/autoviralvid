"""Thin executor service for wireframe/presentation planning stage."""

from __future__ import annotations

from typing import Any

from src.schemas.ppt_plan import PresentationPlan, PresentationPlanRequest


class PPTExecutorService:
    """Facade over executor-facing stage methods."""

    def __init__(self, *, delegate: Any) -> None:
        self._delegate = delegate

    async def generate_presentation_plan(
        self, req: PresentationPlanRequest
    ) -> PresentationPlan:
        return await self._delegate.generate_presentation_plan(req)

