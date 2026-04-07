from src.ppt_design_decision import (
    apply_design_decision_to_slides,
    attach_design_decision_v1,
    build_design_decision_v1,
    freeze_retry_visual_identity,
)


def test_build_design_decision_v1_contains_deck_and_slide_rows():
    decision = build_design_decision_v1(
        style_variant="sharp",
        palette_key="business_authority",
        theme_recipe="consulting_clean",
        tone="light",
        template_family="dashboard_dark",
        quality_profile="default",
        route_mode="standard",
        skill_profile="general-content",
        slides=[{"slide_id": "s1", "layout_grid": "grid_3", "render_path": "svg"}],
        decision_source="unit_test",
    )
    assert decision["version"] == "v1"
    assert decision["deck"]["style_variant"] == "sharp"
    assert decision["deck"]["palette_key"] == "business_authority"
    assert decision["deck"]["theme_recipe"] == "consulting_clean"
    assert decision["deck"]["tone"] == "light"
    assert decision["slides"][0]["slide_id"] == "s1"
    assert decision["slides"][0]["layout_grid"] == "grid_3"


def test_apply_design_decision_to_slides_fills_auto_fields():
    slides = [{"slide_id": "s1", "template_family": "auto", "layout_grid": ""}]
    decision = {
        "version": "v1",
        "deck": {"template_family": "ops_lifecycle_light"},
        "slides": [{"slide_id": "s1", "layout_grid": "timeline"}],
    }
    out = apply_design_decision_to_slides(slides, decision)
    assert out[0]["template_family"] == "ops_lifecycle_light"
    assert out[0]["layout_grid"] == "timeline"


def test_freeze_retry_visual_identity_keeps_deck_visual_contract():
    slides = [
        {"slide_id": "s1", "style_variant": "soft", "palette_key": "modern_wellness", "template_family": "hero_dark"}
    ]
    decision = {
        "version": "v1",
        "deck": {
            "style_variant": "sharp",
            "palette_key": "business_authority",
            "theme_recipe": "consulting_clean",
            "tone": "light",
            "template_family": "dashboard_dark",
            "skill_profile": "general-content",
        },
    }
    out = freeze_retry_visual_identity(slides, decision)
    assert out[0]["style_variant"] == "sharp"
    assert out[0]["palette_key"] == "business_authority"
    assert out[0]["theme_recipe"] == "consulting_clean"
    assert out[0]["tone"] == "light"
    assert out[0]["template_family"] == "dashboard_dark"
    assert out[0]["template_id"] == "dashboard_dark"


def test_attach_design_decision_v1_adds_payload_field():
    payload = {
        "style_variant": "rounded",
        "palette_key": "pure_tech_blue",
        "slides": [{"slide_id": "s1", "layout_grid": "grid_3"}],
    }
    out = attach_design_decision_v1(payload, decision_source="unit_test")
    assert isinstance(out.get("design_decision_v1"), dict)
    assert out["design_decision_v1"]["deck"]["style_variant"] == "rounded"


def test_build_design_decision_v1_writes_owner_trace_metadata():
    decision = build_design_decision_v1(
        style_variant="soft",
        palette_key="education_office_classic",
        decision_source="owner_trace_test",
    )
    trace = decision.get("decision_trace") if isinstance(decision.get("decision_trace"), list) else []
    assert trace
    latest = trace[-1]
    assert latest.get("owner") == "agent/src/ppt_design_decision.py"
    owned_fields = latest.get("owned_fields") if isinstance(latest.get("owned_fields"), list) else []
    assert "style_variant" in owned_fields
    assert "template_family" in owned_fields


def test_freeze_retry_visual_identity_applies_slide_level_render_contract():
    slides = [
        {
            "slide_id": "s1",
            "style_variant": "soft",
            "palette_key": "modern_wellness",
            "template_family": "hero_dark",
            "layout_grid": "split_2",
            "render_path": "svg",
        }
    ]
    decision = {
        "version": "v1",
        "deck": {
            "style_variant": "sharp",
            "palette_key": "business_authority",
            "template_family": "dashboard_dark",
        },
        "slides": [
            {
                "slide_id": "s1",
                "template_family": "ops_lifecycle_light",
                "layout_grid": "timeline",
                "render_path": "svg",
            }
        ],
    }
    out = freeze_retry_visual_identity(slides, decision)
    assert out[0]["style_variant"] == "sharp"
    assert out[0]["palette_key"] == "business_authority"
    assert out[0]["template_family"] == "dashboard_dark"
    assert out[0]["layout_grid"] == "timeline"
    assert out[0]["render_path"] == "svg"
