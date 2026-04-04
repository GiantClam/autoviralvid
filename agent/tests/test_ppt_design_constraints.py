from src.ppt_design_constraints import validate_render_payload_design


def test_design_constraints_detect_terminal_title_echo_and_generic_copy():
    payload = {
        "style_variant": "rounded",
        "palette_key": "pure_tech_blue",
        "theme_recipe": "classroom_soft",
        "tone": "light",
        "design_decision_v1": {
            "deck": {
                "style_variant": "rounded",
                "palette_key": "pure_tech_blue",
                "theme_recipe": "classroom_soft",
                "tone": "light",
            },
            "slides": [],
        },
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "title": "课堂标题",
                "narration": "课堂标题",
                "blocks": [
                    {"block_type": "title", "content": "课堂标题"},
                    {"block_type": "body", "content": "课堂标题"},
                ],
            },
            {
                "slide_id": "s2",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "影响路径",
                "blocks": [
                    {"block_type": "title", "content": "影响路径"},
                    {"block_type": "body", "content": "先说明影响路径的定义、边界与适用范围"},
                ],
            },
        ],
    }
    report = validate_render_payload_design(payload)
    assert report["passed"] is False
    slide_map = {row["slide_id"]: row["issues"] for row in report["slides"]}
    assert "terminal_title_echo" in slide_map["s1"]
    assert "generic_support_copy" in slide_map["s2"]


def test_design_constraints_pass_for_clean_payload():
    payload = {
        "style_variant": "rounded",
        "palette_key": "pure_tech_blue",
        "theme_recipe": "classroom_soft",
        "tone": "light",
        "design_decision_v1": {
            "deck": {
                "style_variant": "rounded",
                "palette_key": "pure_tech_blue",
                "theme_recipe": "classroom_soft",
                "tone": "light",
            },
            "slides": [],
        },
        "slides": [
            {
                "slide_id": "s1",
                "slide_type": "cover",
                "layout_grid": "hero_1",
                "title": "课堂标题",
                "narration": "高中课堂 · 展示课件",
                "blocks": [
                    {"block_type": "title", "content": "课堂标题"},
                    {"block_type": "subtitle", "content": "高中课堂 · 展示课件"},
                ],
            },
            {
                "slide_id": "s2",
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "影响路径",
                "blocks": [
                    {"block_type": "title", "content": "影响路径"},
                    {"block_type": "body", "content": "外部影响：规则变化如何进一步传导到国际关系格局"},
                ],
            },
        ],
    }
    report = validate_render_payload_design(payload)
    assert report["passed"] is True
