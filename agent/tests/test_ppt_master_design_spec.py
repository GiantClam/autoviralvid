from src.ppt_master_design_spec import apply_render_paths, build_design_spec, choose_render_path


def test_choose_render_path_uses_svg_for_complex_layouts_after_structural_failure_marker():
    slide = {
        "slide_type": "content",
        "layout_grid": "workflow",
        "structural_expression_failure": True,
        "blocks": [],
    }
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
        "split_merge_exhausted": True,
    }
    assert choose_render_path(slide, svg_mode="on") == "svg"


def test_choose_render_path_uses_svg_for_semantic_complex_slide_type():
    slide = {
        "slide_type": "architecture",
        "layout_grid": "split_2",
        "structural_expression_failure": True,
        "blocks": [],
    }
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
        "split_merge_exhausted": True,
    }
    assert choose_render_path(slide, svg_mode="on") == "svg"


def test_choose_render_path_uses_svg_for_cover_summary():
    cover = {"slide_type": "cover", "layout_grid": "workflow", "blocks": []}
    summary = {"slide_type": "summary", "layout_grid": "timeline", "blocks": []}
    assert choose_render_path(cover, svg_mode="on") == "svg"
    assert choose_render_path(summary, svg_mode="on") == "svg"


def test_choose_render_path_ignores_svg_mode_off_in_svg_only_pipeline():
    slide = {"slide_type": "content", "layout_grid": "workflow", "blocks": []}
    assert choose_render_path(slide, svg_mode="off") == "svg"


def test_choose_render_path_routes_text_heavy_template_backed_pages_to_svg():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "content_density": "high",
        "template_family": "consulting_warm_light",
        "blocks": [
            {"block_type": "title", "content": "Q3 经营复盘"},
            {"block_type": "body", "content": "A" * 240},
            {"block_type": "list", "content": ";".join([f"要点{i}" for i in range(10)])},
            {"block_type": "chart", "data": {"chart_type": "bar"}},
        ],
    }
    assert choose_render_path(slide, svg_mode="on") == "svg"


def test_choose_render_path_routes_continuation_pages_to_svg():
    slide = {
        "slide_type": "content",
        "layout_grid": "timeline",
        "continuation_of": "s1",
        "continuation_index": 2,
        "continuation_total": 3,
        "is_continuation": True,
        "blocks": [{"block_type": "workflow", "content": "A -> B -> C"}],
    }
    assert choose_render_path(slide, svg_mode="on") == "svg"


def test_apply_render_paths_keeps_mixed_deck_template_consistency():
    slides = [
        {"slide_type": "cover", "layout_grid": "hero_1", "blocks": []},
        {
            "slide_type": "content",
            "layout_grid": "split_2",
            "content_density": "high",
            "template_family": "consulting_warm_light",
            "blocks": [
                {"block_type": "title", "content": "Q3 经营复盘"},
                {"block_type": "body", "content": "A" * 240},
                {"block_type": "list", "content": ";".join([f"要点{i}" for i in range(10)])},
            ],
        },
        {
            "slide_type": "architecture",
            "layout_grid": "architecture",
            "structural_expression_failure": True,
            "blocks": [{"block_type": "diagram", "content": "mesh"}],
        },
    ]

    applied = apply_render_paths(slides, svg_mode="on")

    assert [slide["render_path"] for slide in applied] == ["svg", "svg", "svg"]


def test_apply_render_paths_preserves_mixed_deck_consistency():
    slides = [
        {"slide_type": "cover", "layout_grid": "hero_1", "blocks": []},
        {
            "slide_type": "content",
            "layout_grid": "split_2",
            "content_density": "high",
            "template_family": "consulting_warm_light",
            "blocks": [{"block_type": "list", "content": ";".join([f"要点{i}" for i in range(8)])}],
        },
        {
            "slide_type": "architecture",
            "layout_grid": "architecture",
            "structural_expression_failure": True,
            "blocks": [{"block_type": "diagram", "content": "mesh"}],
        },
    ]

    out = apply_render_paths(slides, svg_mode="on")

    assert [slide["render_path"] for slide in out] == ["svg", "svg", "svg"]


def test_build_design_spec_render_policy_keeps_storyline_as_weak_modifier():
    spec = build_design_spec(template_family="consulting_warm_light")
    assert "storyline" not in spec["render_policy"]["svg_complex_layouts"]
