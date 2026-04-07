from src.ppt_render_path_policy import (
    allow_visual_critic_svg_fallback,
    choose_render_path_by_policy,
    classify_render_path,
)


def test_policy_uses_svg_for_terminal_pages():
    slide = {"slide_type": "cover", "layout_grid": "workflow", "blocks": [{"block_type": "workflow"}]}
    assert choose_render_path_by_policy(slide, svg_mode="on") == "svg"


def test_policy_keeps_dense_text_signal_but_routes_svg():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "content_density": "high",
        "blocks": [
            {"block_type": "title", "content": "Quarterly Update"},
            {"block_type": "list", "content": ";".join([f"bullet {i}" for i in range(8)])},
        ],
    }
    decision = classify_render_path(slide, svg_mode="on")
    assert decision["render_path"] == "svg"
    assert "density_only" in decision["forbidden_triggers"]


def test_policy_marks_forbidden_triggers_for_technical_theme_only():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "content_density": "high",
        "template_family": "consulting_warm_light",
        "intent": "technical deep dive",
        "blocks": [
            {"block_type": "title", "content": "系统架构说明"},
            {"block_type": "body", "content": "A" * 200},
            {"block_type": "chart", "data": {"chart_type": "bar"}},
        ],
    }
    decision = classify_render_path(slide, svg_mode="on")
    assert decision["render_path"] == "svg"
    assert "density_only" in decision["forbidden_triggers"]
    assert "template_fallback_available" in decision["forbidden_triggers"]


def test_policy_keeps_split_continuation_signal_but_routes_svg():
    slide = {
        "slide_type": "content",
        "layout_grid": "workflow",
        "continuation_of": "s1",
        "continuation_index": 2,
        "continuation_total": 3,
        "is_continuation": True,
        "blocks": [{"block_type": "workflow"}],
    }
    decision = classify_render_path(slide, svg_mode="on")
    assert decision["render_path"] == "svg"
    assert decision["reason"] == "split_merge_applied_svg_only"


def test_policy_allows_svg_after_split_merge_only_with_explicit_exception_marker():
    slide = {
        "slide_type": "content",
        "layout_grid": "workflow",
        "continuation_of": "s1",
        "continuation_index": 2,
        "continuation_total": 2,
        "is_continuation": True,
        "structural_expression_failure": True,
        "blocks": [{"block_type": "workflow"}],
    }
    decision = classify_render_path(slide, svg_mode="on")
    assert decision["render_path"] == "svg"
    assert "explicit_exception_marker" in decision["allowed_exception_reasons"]


def test_policy_allows_svg_for_structural_exception_page():
    slide = {
        "slide_type": "content",
        "layout_grid": "workflow",
        "structural_expression_failure": True,
        "blocks": [{"block_type": "workflow"}],
    }
    decision = classify_render_path(slide, svg_mode="on")
    assert decision["render_path"] == "svg"
    assert any("layout:workflow" == reason for reason in decision["allowed_exception_reasons"])


def test_policy_does_not_require_technical_theme_for_svg():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "intent": "technical overview",
        "page_role": "analysis",
        "blocks": [
            {"block_type": "title", "content": "System Overview"},
            {"block_type": "body", "content": "A concise explanation of the current architecture."},
        ],
    }
    decision = classify_render_path(slide, svg_mode="on")
    assert decision["render_path"] == "svg"
    assert decision["allowed_exception_reasons"] == []


def test_policy_uses_svg_without_split_merge_gate():
    slide = {
        "slide_type": "content",
        "layout_grid": "workflow",
        "blocks": [{"block_type": "workflow"}],
    }
    decision = classify_render_path(slide, svg_mode="on")
    assert decision["render_path"] == "svg"
    assert decision["reason"] in {"layout:workflow", "svg_only_default_route"}


def test_policy_treats_storyline_as_weak_modifier_only():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "intent": "storyline technical journey",
        "blocks": [{"block_type": "body", "content": "Narrative flow summary"}],
    }
    decision = classify_render_path(slide, svg_mode="on")
    assert decision["render_path"] == "svg"


def test_policy_does_not_promote_svg_from_intent_tokens_even_when_split_merge_exhausted():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "split_merge_exhausted": True,
        "intent": "workflow architecture roadmap",
        "layout_intent": "storyline",
        "page_role": "technical_deep_dive",
        "blocks": [{"block_type": "body", "content": "Narrative-heavy summary"}],
    }
    decision = classify_render_path(slide, svg_mode="on")
    assert decision["render_path"] == "svg"


def test_policy_allows_explicit_single_slide_exception_after_split_merge():
    slide = {
        "slide_type": "content",
        "layout_grid": "timeline",
        "continuation_of": "s1",
        "continuation_index": 2,
        "continuation_total": 3,
        "is_continuation": True,
        "single_slide_intent_required": True,
        "blocks": [{"block_type": "workflow", "content": "A -> B -> C"}],
    }
    decision = classify_render_path(slide, svg_mode="on")
    assert decision["render_path"] == "svg"
    assert "explicit_exception_marker" in decision["allowed_exception_reasons"]
    assert "split_or_merge_already_applied" in decision["forbidden_triggers"]


def test_policy_allows_visual_critic_svg_fallback_for_dense_standard_page():
    slide = {
        "slide_type": "content",
        "layout_grid": "grid_4",
        "content_density": "high",
        "blocks": [{"block_type": "body", "content": ";".join([f"item {i}" for i in range(8)])}],
    }
    assert allow_visual_critic_svg_fallback(slide, ["card_overlap"]) is True
