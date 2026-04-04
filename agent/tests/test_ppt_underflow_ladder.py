from src.ppt_layout_solver import solve_slide_layout


def test_layout_solver_underflow_triggers_visual_anchor_action():
    slide = {
        "archetype": "dashboard_kpi_4",
        "blocks": [
            {"block_type": "title", "content": "核心结论"},
        ],
    }
    out = solve_slide_layout(slide)
    assert out["status"] == "underflow"
    assert "add_visual_anchor" in out["underflow_actions"]
    assert out["recommended_variant"] == "airy"
