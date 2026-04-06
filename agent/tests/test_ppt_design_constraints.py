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


def test_design_constraints_ignore_narration_only_title_echo_on_terminal_slide():
    payload = {
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
                "slide_type": "summary",
                "layout_grid": "hero_1",
                "title": "总结与启示",
                "narration": "总结与启示",
                "blocks": [
                    {"block_type": "title", "content": "总结与启示"},
                    {"block_type": "body", "content": "回顾课堂关键问题"},
                ],
            }
        ],
    }
    report = validate_render_payload_design(payload)
    slide_map = {row["slide_id"]: row["issues"] for row in report["slides"]}
    assert "terminal_title_echo" not in slide_map["s1"]


def test_design_constraints_detect_color_whitespace_and_font_violations():
    payload = {
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
                "slide_type": "content",
                "layout_grid": "split_2",
                "title": "约束检查",
                "elements": [
                    {
                        "type": "text",
                        "is_title": True,
                        "width": 9.5,
                        "height": 3.0,
                        "style": {"fontSize": 20, "color": "#FF0000", "backgroundColor": "#00FF00"},
                    },
                    {
                        "type": "text",
                        "width": 9.5,
                        "height": 2.6,
                        "style": {"fontSize": 16, "color": "#0000FF", "borderColor": "#FF00FF"},
                    },
                ],
            }
        ],
    }
    report = validate_render_payload_design(payload)
    slide_map = {row["slide_id"]: row["issues"] for row in report["slides"]}
    assert "three_color_violation" in slide_map["s1"]
    assert "insufficient_whitespace" in slide_map["s1"]
    assert "title_font_too_small" in slide_map["s1"]
    assert "body_font_too_small" in slide_map["s1"]
