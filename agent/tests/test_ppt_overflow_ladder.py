from src.ppt_layout_solver import solve_slide_layout


def test_layout_solver_overflow_triggers_compress_and_density_downgrade_actions():
    long_text = "这是一个非常长的正文段落，用于模拟单页文本超出容量的情况。" * 18
    slide = {
        "archetype": "comparison_2col",
        "blocks": [
            {"block_type": "title", "content": "对比分析"},
            {"block_type": "body", "content": long_text},
            {"block_type": "body", "content": long_text},
            {"block_type": "body", "content": long_text},
            {"block_type": "body", "content": long_text},
            {"block_type": "body", "content": long_text},
        ],
    }

    out = solve_slide_layout(slide)
    assert out["status"] == "overflow"
    assert "compress_text" in out["overflow_actions"]
    assert "downgrade_layout_density" in out["overflow_actions"]
    assert out["recommended_variant"] == "dense"
