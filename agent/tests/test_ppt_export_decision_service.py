from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.ppt_export_decision_service import PPTExportDecisionService


@pytest.mark.asyncio
async def test_build_decision_returns_expected_profiles_and_meta():
    svc = PPTExportDecisionService()
    req = SimpleNamespace(
        title="Deck",
        author="Author",
        retry_hint="hint",
        minimax_style_variant="business_clean",
        minimax_palette_key="auto",
        theme_recipe="auto",
        tone="auto",
        template_family="auto",
        skill_profile="auto",
        hardness_profile="minimal",
        schema_profile="default",
        contract_profile="strict",
        quality_profile="lenient_draft",
        svg_mode="safe",
        template_file_url="",
    )

    def _layer1(**_kwargs):
        return {"style_variant": "v1", "palette_key": "p1", "theme_recipe": "t1"}

    async def _hydrate(payload):
        return {**payload, "slides": payload.get("slides", [])}

    result = await svc.build_decision(
        req=req,
        slides_data=[{"title": "S1"}],
        requested_execution_profile="prod_safe",
        requested_force_ppt_master=False,
        dev_fast_fail=True,
        run_layer1_design_skill_chain=_layer1,
        resolve_quality_profile_id=lambda *_args, **_kwargs: "lenient_draft",
        derive_deck_archetype_profile=lambda *_args, **_kwargs: "business_default",
        canonicalize_pipeline_palette=lambda palette, **_kwargs: str(palette),
        default_palette_for_archetype=lambda *_args, **_kwargs: "default_palette",
        apply_skill_planning_to_render_payload=lambda payload, **_kwargs: payload,
        apply_visual_orchestration=lambda payload: payload,
        hydrate_image_assets=_hydrate,
        collect_image_asset_issues=lambda _payload: ["missing_image"],
    )

    assert result.requested_quality_profile == "lenient_draft"
    assert result.effective_style_variant == "v1"
    assert result.effective_palette_key == "p1"
    assert result.build_meta.get("decision_source") == "layer1+skill_planning"
    assert result.build_meta.get("image_asset_issues") == ["missing_image"]

