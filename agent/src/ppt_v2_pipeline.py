"""V2 pipeline entrypoint with serial-stage contract checks.

Phase P1 goal:
- Provide a dedicated V2 orchestration surface.
- Route through V1 executor safely while enforcing serial stage order.
- Keep input/output contract unchanged.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List

from src.schemas.ppt_pipeline import PPTPipelineRequest, PPTPipelineResult


_SERIAL_STAGE_ORDER = [
    "research",
    "outline_plan",
    "presentation_plan",
    "quality_gate",
    "export",
]


class PPTV2Pipeline:
    """V2 pipeline adapter with strict serial stage validation."""

    def __init__(
        self,
        *,
        v1_runner: Callable[[PPTPipelineRequest], Awaitable[PPTPipelineResult]],
    ) -> None:
        self._v1_runner = v1_runner

    @staticmethod
    def _stage_names(result: PPTPipelineResult) -> List[str]:
        return [str(getattr(stage, "stage", "") or "") for stage in (result.stages or [])]

    @staticmethod
    def _is_serial_order(stage_names: List[str]) -> bool:
        if stage_names == _SERIAL_STAGE_ORDER:
            return True
        return False

    async def run(self, req: PPTPipelineRequest) -> PPTPipelineResult:
        result = await self._v1_runner(req)
        stage_names = self._stage_names(result)
        if not self._is_serial_order(stage_names):
            raise ValueError(
                "V2 pipeline stage order mismatch: "
                + ",".join(stage_names or ["<empty>"])
            )

        if isinstance(result.export, dict):
            export_obj: Dict[str, Any] = dict(result.export)
            export_obj.setdefault(
                "pipeline_v2",
                {
                    "enabled": True,
                    "engine": "drawingml_core",
                    "adapter_mode": "v1_bridge",
                    "stage_order": list(stage_names),
                },
            )
            result.export = export_obj
        return result

