import pytest

from src.ppt_quality_gate import QualityIssue, QualityResult
from src.ppt_service_v2 import PPTService
from src.schemas.ppt_pipeline import PPTPipelineRequest


@pytest.mark.asyncio
async def test_run_ppt_pipeline_raises_when_quality_gate_fails(monkeypatch):
    monkeypatch.setattr(
        "src.ppt_quality_gate.validate_deck",
        lambda *_args, **_kwargs: QualityResult(
            ok=False,
            issues=[
                QualityIssue(
                    slide_id="slide-1",
                    code="quality_failed",
                    message="quality gate failed",
                    retry_scope="deck",
                    retry_target_ids=[],
                )
            ],
        ),
    )

    svc = PPTService()
    req = PPTPipelineRequest(
        topic="sample topic",
        total_pages=6,
        quality_profile="lenient_draft",
        web_enrichment=False,
        with_export=False,
        save_artifacts=False,
    )

    with pytest.raises(ValueError, match="Quality gate failed"):
        await svc.run_ppt_pipeline(req)
