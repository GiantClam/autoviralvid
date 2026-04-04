from src.ppt_layout_solver import solve_slide_layout


def test_layout_solver_balanced_slide_has_no_ladder_actions():
    slide = {
        "archetype": "thesis_assertion",
        "blocks": [
            {"block_type": "title", "content": "增长结论"},
            {"block_type": "body", "content": "核心渠道贡献了主要增长，转化效率持续提升，且关键客户续费率在过去两个季度持续抬升。"},
            {"block_type": "body", "content": "经营杠杆改善后，单位获客成本下降，同时线索到成交转化周期显著缩短，利润结构更健康。"},
            {"block_type": "image", "content": "hero-image"},
        ],
    }
    out = solve_slide_layout(slide)
    assert out["status"] == "ok"
    assert out["overflow_actions"] == []
    assert out["underflow_actions"] == []
    assert out["recommended_variant"] == "balanced"


def test_layout_solver_unknown_archetype_uses_default_spec():
    slide = {
        "archetype": "unknown_case",
        "blocks": [
            {"block_type": "title", "content": "标题"},
            {"block_type": "body", "content": "这是正文"},
        ],
    }
    out = solve_slide_layout(slide)
    assert out["archetype"] == "unknown_case"
    assert out["metrics"]["text_slots"] >= 1
    assert out["status"] in {"ok", "underflow", "overflow"}
