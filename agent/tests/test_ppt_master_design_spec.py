from src.ppt_master_design_spec import choose_render_path


def test_choose_render_path_uses_svg_for_complex_layouts():
    slide = {"slide_type": "content", "layout_grid": "workflow", "blocks": []}
    assert choose_render_path(slide, svg_mode="on") == "svg"


def test_choose_render_path_uses_svg_for_complex_chart_subtypes():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "blocks": [
            {
                "block_type": "chart",
                "data": {"chart_type": "sankey"},
            }
        ],
    }
    assert choose_render_path(slide, svg_mode="on") == "svg"


def test_choose_render_path_uses_svg_for_semantic_complex_slide_type():
    slide = {"slide_type": "architecture", "layout_grid": "split_2", "blocks": []}
    assert choose_render_path(slide, svg_mode="on") == "svg"


def test_choose_render_path_uses_svg_for_data_visualization_semantics():
    slide = {
        "slide_type": "content",
        "content_subtype": "data_visualization",
        "layout_grid": "split_2",
        "blocks": [],
    }
    assert choose_render_path(slide, svg_mode="on") == "svg"


def test_choose_render_path_uses_svg_for_infographic_semantics():
    slide = {
        "slide_type": "content",
        "semantic_subtype": "infographic",
        "layout_grid": "split_2",
        "blocks": [],
    }
    assert choose_render_path(slide, svg_mode="on") == "svg"


def test_choose_render_path_uses_svg_for_extended_chart_subtype():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "blocks": [
            {
                "block_type": "chart",
                "data": {"chart_type": "wordcloud"},
            }
        ],
    }
    assert choose_render_path(slide, svg_mode="on") == "svg"


def test_choose_render_path_keeps_cover_summary_on_pptxgenjs():
    cover = {"slide_type": "cover", "layout_grid": "workflow", "blocks": []}
    summary = {"slide_type": "summary", "layout_grid": "timeline", "blocks": []}
    assert choose_render_path(cover, svg_mode="on") == "pptxgenjs"
    assert choose_render_path(summary, svg_mode="on") == "pptxgenjs"


def test_choose_render_path_respects_svg_mode_off():
    slide = {"slide_type": "content", "layout_grid": "workflow", "blocks": []}
    assert choose_render_path(slide, svg_mode="off") == "pptxgenjs"
