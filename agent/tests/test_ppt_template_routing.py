from src.ppt_template_catalog import (
    contract_profile,
    quality_profile,
    resolve_template_for_slide,
    template_capabilities,
    template_profiles,
)


def test_template_routing_prefers_data_capability_for_dense_data_slide():
    slide = {
        "title": "Quarterly KPI review",
        "content_density": "dense",
        "blocks": [
            {"block_type": "title", "content": "KPI Snapshot"},
            {"block_type": "kpi", "content": "ROI 132%"},
            {"block_type": "chart", "content": "Q1-Q4 Trend"},
            {"block_type": "table", "content": "Channel breakdown"},
        ],
    }
    template = resolve_template_for_slide(
        slide=slide,
        slide_type="content",
        layout_grid="grid_3",
        desired_density="dense",
    )
    assert template in {"dashboard_dark", "ops_lifecycle_light", "kpi_dashboard_dark"}


def test_template_routing_weak_keyword_does_not_force_architecture():
    slide = {
        "title": "AI orchestration overview",
        "blocks": [{"block_type": "body", "content": "Product highlights"}],
    }
    template = resolve_template_for_slide(
        slide=slide,
        slide_type="content",
        layout_grid="split_2",
        desired_density="balanced",
    )
    assert template != "architecture_dark_panel"


def test_template_capabilities_and_contract_profile_loaded_from_catalog():
    cap = template_capabilities("consulting_warm_light")
    assert cap["visual_anchor_capacity"] >= 1
    assert "split_2" in cap["supported_layouts"]

    profile = contract_profile("chart_or_kpi_required")
    assert profile["min_visual_blocks"] >= 1
    assert any("chart" in group for group in profile["required_one_of_groups"])

    template_meta = template_profiles("consulting_warm_light")
    assert template_meta["quality_profile"] == "high_density_consulting"
    q = quality_profile(template_meta["quality_profile"])
    assert q["min_content_blocks"] >= 3


def test_template_routing_avoids_image_required_template_when_image_asset_missing():
    slide = {
        "title": "Workflow platform overview",
        "blocks": [
            {"block_type": "title", "content": "Platform overview"},
            {"block_type": "body", "content": "Orchestration and observability"},
            {"block_type": "list", "content": "Planner;Executor;Guardrail"},
            {"block_type": "image", "content": {"title": "visual intent only"}},
        ],
    }
    template = resolve_template_for_slide(
        slide=slide,
        slide_type="content",
        layout_grid="split_2",
        desired_density="balanced",
    )
    assert template not in {"neural_blueprint_light", "consulting_warm_light"}


def test_template_routing_avoids_contract_infeasible_templates_on_split_layout():
    slide = {
        "title": "业务进展",
        "blocks": [
            {"block_type": "title", "content": "业务进展"},
            {"block_type": "body", "content": "收入增长与渠道优化"},
            {"block_type": "list", "content": "增长动因;执行动作;风险控制"},
        ],
    }
    template = resolve_template_for_slide(
        slide=slide,
        slide_type="content",
        layout_grid="split_2",
        desired_density="dense",
    )
    assert template in {"split_media_dark", "consulting_warm_light"}
