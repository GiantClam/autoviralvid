from __future__ import annotations

import pytest

from src.ppt_export_reorchestrate_service import PPTExportReorchestrateService


@pytest.mark.asyncio
async def test_reorchestrate_returns_not_updated_when_no_repaired_slides():
    svc = PPTExportReorchestrateService()
    seed = [{"slide_id": "s1", "render_path": "png"}]

    async def _hydrate(_payload):
        return {"slides": []}

    out = await svc.reorchestrate(
        seed_slides=seed,
        title="Deck",
        effective_style_variant="v",
        effective_palette_key="p",
        effective_theme_recipe="t",
        effective_tone="auto",
        effective_template_family="auto",
        effective_skill_profile="general",
        requested_execution_profile="prod_safe",
        requested_force_ppt_master=False,
        quality_profile="lenient_draft",
        req_hardness_profile="minimal",
        req_schema_profile="default",
        req_contract_profile="strict",
        req_svg_mode="on",
        route_mode="fast",
        current_design_decision={"deck": {"ok": True}},
        apply_skill_planning_to_render_payload=lambda payload, **_kwargs: payload,
        apply_visual_orchestration=lambda payload: payload,
        hydrate_image_assets=_hydrate,
        normalize_design_decision_v1=lambda value: value if isinstance(value, dict) else {},
        build_design_decision_v1=lambda **_kwargs: {"deck": {"fallback": True}},
        freeze_retry_visual_identity=lambda slides, _decision: slides,
    )

    assert out.updated is False
    assert out.slides == seed
    assert out.design_decision == {"deck": {"ok": True}}


@pytest.mark.asyncio
async def test_reorchestrate_preserves_critic_repair_and_builds_missing_decision():
    svc = PPTExportReorchestrateService()
    seed = [
        {"slide_id": "s1", "visual": {"critic_repair": {"score": 90}}},
        {"slide_id": "s2"},
    ]

    async def _hydrate(payload):
        slides = [dict(item) for item in (payload.get("slides") or [])]
        for row in slides:
            row.pop("visual", None)
        return {"slides": slides, "design_decision_v1": {}}

    def _build_design(**kwargs):
        return {"deck": {"decision_source": kwargs.get("decision_source")}}

    out = await svc.reorchestrate(
        seed_slides=seed,
        title="Deck",
        effective_style_variant="v",
        effective_palette_key="p",
        effective_theme_recipe="t",
        effective_tone="auto",
        effective_template_family="auto",
        effective_skill_profile="general",
        requested_execution_profile="prod_safe",
        requested_force_ppt_master=False,
        quality_profile="lenient_draft",
        req_hardness_profile="minimal",
        req_schema_profile="default",
        req_contract_profile="strict",
        req_svg_mode="on",
        route_mode="fast",
        current_design_decision={},
        apply_skill_planning_to_render_payload=lambda payload, **_kwargs: payload,
        apply_visual_orchestration=lambda payload: payload,
        hydrate_image_assets=_hydrate,
        normalize_design_decision_v1=lambda _value: {},
        build_design_decision_v1=_build_design,
        freeze_retry_visual_identity=lambda slides, _decision: slides,
    )

    assert out.updated is True
    assert out.design_decision.get("deck", {}).get("decision_source") == "retry_reorchestrate"
    s1 = next(item for item in out.slides if item.get("slide_id") == "s1")
    assert s1.get("visual", {}).get("critic_repair", {}).get("score") == 90

