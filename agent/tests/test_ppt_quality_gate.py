from src.ppt_quality_gate import (
    score_deck_quality,
    validate_deck,
    validate_layout_diversity,
    validate_slide,
    validate_visual_audit,
)


def test_detect_blank_or_garbled_slide():
    result = validate_slide({"title": "???", "elements": []})
    assert result.ok is False


def test_detect_placeholder_pollution():
    result = validate_slide(
        {
            "slide_id": "s1",
            "title": "Roadmap",
            "elements": [{"type": "text", "content": "TODO: fill this block"}],
        }
    )
    assert result.ok is False
    assert any(issue.code == "placeholder_pollution" for issue in result.issues)


def test_valid_deck_passes():
    result = validate_deck(
        [
            {
                "slide_id": "s1",
                "title": "Intro",
                "elements": [{"type": "text", "content": "Value proposition"}],
            }
        ]
    )
    assert result.ok is True


def test_layout_diversity_default_ratio_and_adjacent_rules():
    spec = {"slides": [{"slide_type": "content"} for _ in range(6)]}
    result = validate_layout_diversity(spec)
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "layout_homogeneous" in codes
    assert "layout_adjacent_repeat" in codes


def test_layout_diversity_uses_layout_grid_when_slide_type_is_content():
    spec = {
        "slides": [
            {"slide_type": "content", "layout_grid": "split_2"},
            {"slide_type": "content", "layout_grid": "grid_3"},
            {"slide_type": "content", "layout_grid": "timeline"},
            {"slide_type": "content", "layout_grid": "asymmetric_2"},
            {"slide_type": "content", "layout_grid": "bento_6"},
            {"slide_type": "summary", "layout_grid": "summary"},
        ]
    }
    result = validate_layout_diversity(spec)
    assert result.ok is True


def test_layout_diversity_adjacent_repeat_limit_is_1_by_default():
    spec = {
        "slides": [
            {"slide_type": "content"},
            {"slide_type": "content"},
            {"slide_type": "comparison"},
            {"slide_type": "timeline"},
            {"slide_type": "data"},
            {"slide_type": "summary"},
        ]
    }
    result = validate_layout_diversity(spec)
    assert result.ok is False
    assert any(issue.code == "layout_adjacent_repeat" for issue in result.issues)


def test_layout_diversity_requires_variety_for_long_deck():
    spec = {
        "slides": [
            {"slide_type": "content"},
            {"slide_type": "comparison"},
            {"slide_type": "timeline"},
            {"slide_type": "content"},
            {"slide_type": "comparison"},
            {"slide_type": "timeline"},
            {"slide_type": "content"},
            {"slide_type": "comparison"},
            {"slide_type": "timeline"},
            {"slide_type": "content"},
        ]
    }
    result = validate_layout_diversity(spec)
    assert result.ok is False
    assert any(issue.code == "layout_variety_low" for issue in result.issues)


def test_layout_diversity_top2_combination_is_limited():
    spec = {
        "slides": [
            {"slide_type": "content", "layout_grid": "split_2"},
            {"slide_type": "content", "layout_grid": "grid_3"},
            {"slide_type": "content", "layout_grid": "split_2"},
            {"slide_type": "content", "layout_grid": "grid_3"},
            {"slide_type": "content", "layout_grid": "split_2"},
            {"slide_type": "content", "layout_grid": "grid_3"},
            {"slide_type": "content", "layout_grid": "split_2"},
            {"slide_type": "summary", "layout_grid": "summary"},
        ]
    }
    result = validate_layout_diversity(spec)
    assert result.ok is False
    assert any(issue.code == "layout_top2_homogeneous" for issue in result.issues)


def test_layout_diversity_abab_loop_is_rejected():
    spec = {
        "slides": [
            {"slide_type": "content", "layout_grid": "split_2"},
            {"slide_type": "content", "layout_grid": "grid_3"},
            {"slide_type": "content", "layout_grid": "split_2"},
            {"slide_type": "content", "layout_grid": "grid_3"},
            {"slide_type": "content", "layout_grid": "split_2"},
            {"slide_type": "content", "layout_grid": "grid_3"},
        ]
    }
    result = validate_layout_diversity(spec)
    assert result.ok is False
    assert any(issue.code == "layout_abab_repeat" for issue in result.issues)


def test_layout_diversity_detects_density_consecutive_high_run():
    spec = {
        "slides": [
            {"slide_type": "cover", "layout_grid": "hero_1"},
            {"slide_type": "content", "layout_grid": "grid_4"},
            {"slide_type": "content", "layout_grid": "bento_5"},
            {"slide_type": "content", "layout_grid": "bento_6"},
            {"slide_type": "content", "layout_grid": "split_2"},
            {"slide_type": "summary", "layout_grid": "hero_1"},
        ]
    }
    result = validate_layout_diversity(
        spec,
        profile={
            "density_max_consecutive_high": 2,
            "density_window_size": 5,
            "density_require_low_or_breathing_per_window": 1,
        },
        min_slide_count=2,
        max_type_ratio=1.0,
        max_top2_ratio=1.0,
        max_adjacent_repeat=8,
        abab_max_run=99,
        min_layout_variety=1,
        template_family_min_slide_count=99,
    )
    assert result.ok is False
    assert any(issue.code == "layout_density_consecutive_high" for issue in result.issues)


def test_layout_diversity_detects_density_window_missing_breathing():
    spec = {
        "slides": [
            {"slide_type": "cover", "layout_grid": "hero_1"},
            {"slide_type": "content", "layout_grid": "split_2"},
            {"slide_type": "content", "layout_grid": "grid_3"},
            {"slide_type": "content", "layout_grid": "timeline"},
            {"slide_type": "content", "layout_grid": "grid_4"},
            {"slide_type": "content", "layout_grid": "bento_5"},
            {"slide_type": "summary", "layout_grid": "hero_1"},
        ]
    }
    result = validate_layout_diversity(
        spec,
        profile={
            "density_max_consecutive_high": 2,
            "density_window_size": 5,
            "density_require_low_or_breathing_per_window": 1,
        },
        min_slide_count=2,
        max_type_ratio=1.0,
        max_top2_ratio=1.0,
        max_adjacent_repeat=8,
        abab_max_run=99,
        min_layout_variety=1,
        template_family_min_slide_count=99,
    )
    assert result.ok is False
    assert any(issue.code == "layout_density_window_missing_breathing" for issue in result.issues)


def test_layout_diversity_detects_template_family_switch_overflow():
    spec = {
        "slides": [
            {"slide_type": "cover", "template_family": "hero_tech_cover"},
            {"slide_type": "content", "layout_grid": "split_2", "template_family": "architecture_dark_panel"},
            {"slide_type": "content", "layout_grid": "grid_3", "template_family": "neural_blueprint_light"},
            {"slide_type": "content", "layout_grid": "timeline", "template_family": "dashboard_dark"},
            {"slide_type": "content", "layout_grid": "grid_4", "template_family": "ops_lifecycle_light"},
            {"slide_type": "content", "layout_grid": "split_2", "template_family": "ecosystem_orange_dark"},
            {"slide_type": "summary", "template_family": "hero_dark"},
        ]
    }
    result = validate_layout_diversity(spec, min_slide_count=4, template_family_min_slide_count=4)
    assert result.ok is False
    assert any(issue.code == "template_family_switch_frequent" for issue in result.issues)


def test_layout_diversity_detects_template_family_abab():
    spec = {
        "slides": [
            {"slide_type": "cover", "template_family": "hero_tech_cover"},
            {"slide_type": "content", "layout_grid": "split_2", "template_family": "architecture_dark_panel"},
            {"slide_type": "content", "layout_grid": "grid_3", "template_family": "dashboard_dark"},
            {"slide_type": "content", "layout_grid": "split_2", "template_family": "architecture_dark_panel"},
            {"slide_type": "content", "layout_grid": "grid_3", "template_family": "dashboard_dark"},
            {"slide_type": "content", "layout_grid": "split_2", "template_family": "architecture_dark_panel"},
            {"slide_type": "content", "layout_grid": "grid_3", "template_family": "dashboard_dark"},
        ]
    }
    result = validate_layout_diversity(spec, min_slide_count=4, template_family_min_slide_count=4)
    assert result.ok is False
    assert any(issue.code == "template_family_abab_repeat" for issue in result.issues)


def test_weighted_quality_score_reports_dimensions():
    slides = [
        {
            "slide_id": "s1",
            "slide_type": "content",
            "layout_grid": "split_2",
            "template_family": "architecture_dark_panel",
            "title": "Growth",
            "blocks": [
                {"block_type": "title", "content": "Growth"},
                {"block_type": "body", "content": "Revenue +21%", "emphasis": ["21%"], "style": {"fontSize": 20}},
                {"block_type": "list", "content": "A;B;C", "style": {"fontSize": 14}},
                {"block_type": "image", "content": {"url": "https://example.com/a.png"}},
            ],
        },
        {
            "slide_id": "s2",
            "slide_type": "content",
            "layout_grid": "grid_3",
            "template_family": "architecture_dark_panel",
            "title": "Ops",
            "blocks": [
                {"block_type": "title", "content": "Ops"},
                {"block_type": "body", "content": "SLA 99.9%", "emphasis": ["99.9%"], "style": {"fontSize": 20}},
                {"block_type": "list", "content": "D;E;F", "style": {"fontSize": 14}},
                {"block_type": "chart", "data": {"labels": ["Q1", "Q2"], "datasets": [{"data": [1, 2]}]}},
            ],
        },
    ]
    result = score_deck_quality(
        slides=slides,
        render_spec={"slides": slides},
        profile="default",
        visual_audit={"blank_slide_ratio": 0.0, "low_contrast_ratio": 0.0, "mean_luminance": 120},
    )
    assert result.score > 0
    assert "structure" in result.dimensions
    assert "layout" in result.dimensions
    assert "family" in result.dimensions
    assert "visual" in result.dimensions
    assert "consistency" in result.dimensions


def test_layout_diversity_terminal_type_checks_are_optional():
    spec = {
        "slides": [
            {"slide_id": "s1", "slide_type": "content"},
            {"slide_id": "s2", "slide_type": "comparison"},
            {"slide_id": "s3", "slide_type": "summary"},
        ]
    }
    result = validate_layout_diversity(
        spec,
        min_slide_count=2,
        enforce_terminal_slide_types=True,
    )
    assert result.ok is False
    assert any(issue.code == "layout_terminal_cover_missing" for issue in result.issues)


def test_chart_placeholder_data_is_rejected():
    result = validate_slide(
        {
            "slide_id": "s-chart",
            "title": "Chart Slide",
            "elements": [
                {
                    "type": "chart",
                    "chart_data": {
                        "labels": ["指标A", "指标B", "指标C"],
                        "datasets": [{"label": "S1", "data": [0, 0, 0]}],
                    },
                }
            ],
        }
    )
    assert result.ok is False
    assert any(issue.code == "placeholder_chart_data" for issue in result.issues)


def test_kpi_placeholder_data_is_rejected():
    result = validate_slide(
        {
            "slide_id": "s-kpi",
            "title": "KPI Slide",
            "blocks": [
                {"block_type": "title", "content": "Metrics"},
                {"block_type": "kpi", "data": {"number": "???", "unit": "%", "trend": 3}},
            ],
        }
    )
    assert result.ok is False
    assert any(issue.code == "placeholder_kpi_data" for issue in result.issues)


def test_content_slide_requires_min_blocks_and_typography_hierarchy():
    result = validate_slide(
        {
            "slide_id": "s-content",
            "slide_type": "content",
            "title": "Content Slide",
            "blocks": [
                {"block_type": "title", "content": "Title", "style": {"fontSize": 24}},
                {"block_type": "body", "content": "Only one block", "style": {"fontSize": 24}},
            ],
        }
    )
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "low_content_density" in codes
    assert "flat_typography" in codes


def test_typography_hierarchy_passes_with_distinct_sizes():
    result = validate_slide(
        {
            "slide_id": "s-typo",
            "slide_type": "content",
            "title": "Good Typography",
            "blocks": [
                {"block_type": "title", "content": "Title", "style": {"fontSize": 28}},
                {"block_type": "body", "content": "Body 1", "style": {"fontSize": 16}, "emphasis": ["Body 1"]},
                {"block_type": "list", "content": "Body 2", "style": {"fontSize": 14}},
            ],
        }
    )
    assert all(issue.code != "flat_typography" for issue in result.issues)


def test_image_missing_is_rejected():
    result = validate_slide(
        {
            "slide_id": "s-img",
            "slide_type": "content",
            "layout_grid": "split_2",
            "blocks": [
                {"block_type": "title", "content": "Visual"},
                {"block_type": "image", "content": {"title": "Missing URL"}},
                {"block_type": "list", "content": "A;B;C"},
            ],
        }
    )
    assert result.ok is False
    assert any(issue.code == "image_missing" for issue in result.issues)


def test_blank_area_ratio_is_rejected_for_sparse_slide():
    result = validate_slide(
        {
            "slide_id": "s-blank",
            "slide_type": "content",
            "layout_grid": "bento_6",
            "blocks": [
                {"block_type": "title", "content": "Sparse"},
                {"block_type": "body", "content": "Only one block"},
            ],
        }
    )
    assert result.ok is False
    assert any(issue.code == "blank_area_high" for issue in result.issues)


def test_duplicate_non_title_text_is_rejected():
    result = validate_slide(
        {
            "slide_id": "s-dup",
            "slide_type": "content",
            "title": "Duplicate",
            "blocks": [
                {"block_type": "title", "content": "Duplicate"},
                {"block_type": "body", "content": "same text", "emphasis": ["same"]},
                {"block_type": "list", "content": "same text"},
            ],
        }
    )
    assert result.ok is False
    assert any(issue.code == "duplicate_text" for issue in result.issues)


def test_weak_emphasis_is_rejected_for_content_slide():
    result = validate_slide(
        {
            "slide_id": "s-weak",
            "slide_type": "content",
            "title": "No Emphasis",
            "blocks": [
                {"block_type": "title", "content": "No Emphasis", "style": {"fontSize": 24}},
                {"block_type": "body", "content": "alpha beta gamma", "style": {"fontSize": 16}},
                {"block_type": "list", "content": "delta;epsilon;zeta", "style": {"fontSize": 14}},
            ],
        }
    )
    assert result.ok is False
    assert any(issue.code == "weak_emphasis" for issue in result.issues)


def test_title_echo_is_rejected_for_content_slide():
    result = validate_slide(
        {
            "slide_id": "s-echo",
            "slide_type": "content",
            "title": "同一标题",
            "blocks": [
                {"block_type": "title", "content": "同一标题", "style": {"fontSize": 24}},
                {"block_type": "body", "content": "同一标题", "style": {"fontSize": 16}, "emphasis": ["同一"]},
                {"block_type": "list", "content": "证据A;证据B", "style": {"fontSize": 14}},
            ],
        }
    )
    assert result.ok is False
    assert any(issue.code == "title_echo" for issue in result.issues)


def test_high_density_quality_profile_requires_more_content_blocks():
    result = validate_slide(
        {
            "slide_id": "s-hd",
            "slide_type": "content",
            "title": "High density",
            "blocks": [
                {"block_type": "title", "content": "High density", "style": {"fontSize": 26}},
                {"block_type": "body", "content": "Point A", "style": {"fontSize": 16}, "emphasis": ["A"]},
                {"block_type": "list", "content": "Point B;Point C", "style": {"fontSize": 14}},
            ],
        },
        profile="high_density_consulting",
    )
    assert result.ok is False
    assert any(issue.code == "low_content_density" for issue in result.issues)


def test_high_density_profile_requires_image_anchor_block():
    result = validate_slide(
        {
            "slide_id": "s-hd-image",
            "slide_type": "content",
            "title": "High density image anchor",
            "layout_grid": "grid_4",
            "blocks": [
                {"block_type": "title", "content": "High density image anchor", "style": {"fontSize": 26}},
                {"block_type": "body", "content": "Point A", "style": {"fontSize": 16}, "emphasis": ["A"]},
                {"block_type": "list", "content": "Point B;Point C", "style": {"fontSize": 14}},
                {"block_type": "chart", "data": {"labels": ["A", "B"], "datasets": [{"data": [1, 2]}]}},
            ],
        },
        profile="high_density_consulting",
    )
    assert result.ok is False
    assert any(issue.code == "image_missing" for issue in result.issues)


def test_lenient_quality_profile_allows_weak_emphasis_and_duplicate():
    result = validate_slide(
        {
            "slide_id": "s-lenient",
            "slide_type": "content",
            "title": "Lenient",
            "layout_grid": "split_2",
            "blocks": [
                {"block_type": "title", "content": "Lenient", "style": {"fontSize": 24}},
                {"block_type": "body", "content": "same text", "style": {"fontSize": 24}},
                {"block_type": "list", "content": "same text", "style": {"fontSize": 24}},
            ],
        },
        profile="lenient_draft",
    )
    assert result.ok is True


def test_visual_audit_gate_detects_overlap_and_image_irrelevance():
    slides = [
        {"slide_id": "s1", "slide_type": "content", "title": "A"},
        {"slide_id": "s2", "slide_type": "content", "title": "B"},
    ]
    visual_audit = {
        "slide_count": 2,
        "blank_slide_ratio": 0.0,
        "low_contrast_ratio": 0.0,
        "blank_area_ratio": 0.0,
        "style_drift_ratio": 0.0,
        "issue_ratios": {
            "text_overlap": 0.85,
            "irrelevant_image": 0.5,
        },
    }
    result = validate_visual_audit(visual_audit=visual_audit, slides=slides, profile="high_density_consulting")
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "visual_text_overlap_ratio_high" in codes
    assert "visual_irrelevant_image_ratio_high" in codes


def test_visual_audit_gate_requires_payload_by_default():
    slides = [{"slide_id": "s1", "slide_type": "content", "title": "A"}]
    result = validate_visual_audit(visual_audit=None, slides=slides, profile="default")
    assert result.ok is False
    assert any(issue.code == "visual_audit_missing" for issue in result.issues)


def test_visual_audit_gate_returns_slide_level_retry_targets():
    slides = [
        {"slide_id": "s1", "slide_type": "content", "title": "A"},
        {"slide_id": "s2", "slide_type": "content", "title": "B"},
    ]
    visual_audit = {
        "slide_count": 2,
        "blank_slide_ratio": 0.0,
        "low_contrast_ratio": 0.6,
        "blank_area_ratio": 0.0,
        "style_drift_ratio": 0.0,
        "issue_ratios": {"text_overlap": 0.6},
        "slides": [
            {"slide": 1, "local_issues": [], "multimodal_issues": []},
            {"slide": 2, "local_issues": ["low_contrast"], "multimodal_issues": ["text_overlap"], "contrast": 8.0},
        ],
    }
    result = validate_visual_audit(visual_audit=visual_audit, slides=slides, profile="high_density_consulting")
    assert result.ok is False
    assert any(issue.retry_scope == "slide" for issue in result.issues)
    assert any("s2" in (issue.retry_target_ids or []) for issue in result.issues)


def test_visual_audit_layout_monotony_is_enforced_with_strict_threshold():
    slides = [
        {"slide_id": "s1", "slide_type": "cover", "layout_grid": "hero_1", "title": "Cover"},
        {"slide_id": "s2", "slide_type": "content", "layout_grid": "grid_3", "title": "A"},
        {"slide_id": "s3", "slide_type": "content", "layout_grid": "grid_4", "title": "B"},
        {"slide_id": "s4", "slide_type": "content", "layout_grid": "bento_5", "title": "C"},
        {"slide_id": "s5", "slide_type": "content", "layout_grid": "timeline", "title": "D"},
        {"slide_id": "s6", "slide_type": "content", "layout_grid": "bento_6", "title": "E"},
        {"slide_id": "s7", "slide_type": "content", "layout_grid": "grid_3", "title": "F"},
        {"slide_id": "s8", "slide_type": "summary", "layout_grid": "hero_1", "title": "Summary"},
    ]
    visual_audit = {
        "slide_count": 8,
        "blank_slide_ratio": 0.0,
        "low_contrast_ratio": 0.0,
        "blank_area_ratio": 0.0,
        "style_drift_ratio": 0.0,
        "issue_ratios": {
            "layout_monotony": 0.55,
        },
    }
    result = validate_visual_audit(
        visual_audit=visual_audit,
        slides=slides,
        profile={"visual_layout_monotony_max_ratio": 0.45},
    )
    assert any(issue.code == "visual_layout_monotony_ratio_high" for issue in result.issues)


def test_visual_audit_layout_monotony_not_relaxed_by_layout_gate_signal():
    slides = [
        {"slide_id": "s1", "slide_type": "content", "title": "A"},
        {"slide_id": "s2", "slide_type": "content", "title": "B"},
    ]
    visual_audit = {
        "slide_count": 2,
        "blank_slide_ratio": 0.0,
        "low_contrast_ratio": 0.0,
        "blank_area_ratio": 0.0,
        "style_drift_ratio": 0.0,
        "issue_ratios": {
            "layout_monotony": 0.6,
        },
    }
    result = validate_visual_audit(
        visual_audit=visual_audit,
        slides=slides,
        profile={"visual_layout_monotony_max_ratio": 0.45},
        layout_diversity_ok=True,
    )
    assert any(issue.code == "visual_layout_monotony_ratio_high" for issue in result.issues)


def test_visual_audit_whitespace_needs_local_corroboration():
    slides = [
        {"slide_id": "s1", "slide_type": "content", "layout_grid": "grid_3", "title": "A"},
        {"slide_id": "s2", "slide_type": "content", "layout_grid": "grid_4", "title": "B"},
        {"slide_id": "s3", "slide_type": "content", "layout_grid": "bento_5", "title": "C"},
        {"slide_id": "s4", "slide_type": "content", "layout_grid": "timeline", "title": "D"},
    ]
    visual_audit = {
        "slide_count": 4,
        "blank_slide_ratio": 0.0,
        "low_contrast_ratio": 0.0,
        "blank_area_ratio": 0.18,
        "style_drift_ratio": 0.0,
        "issue_ratios": {
            "excessive_whitespace": 0.6,
        },
        "local_issue_ratios": {
            "excessive_whitespace": 0.05,
        },
        "multimodal_issue_ratios": {
            "excessive_whitespace": 0.6,
        },
    }
    result = validate_visual_audit(visual_audit=visual_audit, slides=slides, profile="high_density_consulting")
    assert all(issue.code != "visual_whitespace_ratio_high" for issue in result.issues)


def test_weighted_quality_score_penalizes_visual_issue_pressure():
    slides = [
        {
            "slide_id": "s1",
            "slide_type": "content",
            "layout_grid": "grid_3",
            "template_family": "dashboard_dark",
            "title": "A",
            "blocks": [
                {"block_type": "title", "content": "A"},
                {"block_type": "body", "content": "A1", "emphasis": ["1"]},
                {"block_type": "list", "content": "A2"},
                {"block_type": "image", "content": {"url": "https://example.com/a.png"}},
            ],
        }
    ]
    baseline = score_deck_quality(
        slides=slides,
        render_spec={"slides": slides},
        profile="default",
        visual_audit={
            "blank_slide_ratio": 0.0,
            "low_contrast_ratio": 0.0,
            "blank_area_ratio": 0.0,
            "style_drift_ratio": 0.0,
            "mean_luminance": 120,
            "issue_ratios": {},
        },
    )
    degraded = score_deck_quality(
        slides=slides,
        render_spec={"slides": slides},
        profile="default",
        visual_audit={
            "blank_slide_ratio": 0.0,
            "low_contrast_ratio": 0.0,
            "blank_area_ratio": 0.2,
            "style_drift_ratio": 0.5,
            "mean_luminance": 120,
            "issue_ratios": {
                "text_overlap": 1.0,
                "occlusion": 1.0,
                "irrelevant_image": 1.0,
            },
        },
    )
    assert degraded.score < baseline.score


def test_weighted_quality_score_can_enforce_visual_audit_presence():
    slides = [
        {
            "slide_id": "s1",
            "slide_type": "content",
            "layout_grid": "split_2",
            "template_family": "architecture_dark_panel",
            "title": "A",
            "blocks": [
                {"block_type": "title", "content": "A"},
                {"block_type": "body", "content": "A1", "emphasis": ["1"]},
                {"block_type": "list", "content": "A2"},
                {"block_type": "image", "content": {"url": "https://example.com/a.png"}},
            ],
        }
    ]
    result = score_deck_quality(
        slides=slides,
        render_spec={"slides": slides},
        profile="default",
        enforce_visual_audit_presence=True,
        visual_audit=None,
    )
    assert result.passed is False
    assert result.issue_counts.get("visual_audit_missing") == 1
    assert result.diagnostics.get("visual_audit_missing_blocker") is True


def test_status_report_requires_executive_summary_with_four_items():
    slides = [
        {
            "slide_id": "cover",
            "slide_type": "cover",
            "quality_profile": "status_report",
            "title": "Q3 利润率回升 4 个点",
            "blocks": [
                {"block_type": "title", "content": "Q3 利润率回升 4 个点"},
                {"block_type": "subtitle", "content": "经营汇报"},
            ],
        },
        {
            "slide_id": "summary",
            "slide_type": "summary",
            "quality_profile": "status_report",
            "title": "执行摘要",
            "blocks": [
                {"block_type": "title", "content": "执行摘要"},
                {"block_type": "body", "content": "现状快照"},
                {"block_type": "body", "content": "核心问题"},
                {"block_type": "body", "content": "建议方案"}
            ],
        },
    ]
    result = validate_deck(slides, profile="status_report")
    assert result.ok is False
    assert any(issue.code == "scene_status_report_exec_summary_incomplete" for issue in result.issues)



def test_investor_pitch_requires_core_modules_coverage():
    slides = [
        {
            "slide_id": "s1",
            "slide_type": "cover",
            "quality_profile": "investor_pitch",
            "title": "AI 招聘助手",
            "blocks": [{"block_type": "title", "content": "AI 招聘助手"}],
        },
        {
            "slide_id": "s2",
            "slide_type": "content",
            "quality_profile": "investor_pitch",
            "title": "Problem",
            "blocks": [
                {"block_type": "title", "content": "Problem"},
                {"block_type": "body", "content": "招聘效率低"},
                {"block_type": "image", "content": {"url": "https://example.com/a.png"}},
            ],
        },
    ]
    result = validate_deck(slides, profile="investor_pitch")
    assert result.ok is False
    assert any(issue.code == "scene_investor_pitch_modules_missing" for issue in result.issues)



def test_training_deck_requires_learning_goals_and_knowledge_map():
    slides = [
        {
            "slide_id": "cover",
            "slide_type": "cover",
            "quality_profile": "training_deck",
            "title": "Python 入门",
            "blocks": [
                {"block_type": "title", "content": "Python 入门"},
                {"block_type": "subtitle", "content": "第一课"},
            ],
        },
        {
            "slide_id": "content-1",
            "slide_type": "content",
            "quality_profile": "training_deck",
            "title": "变量",
            "blocks": [
                {"block_type": "title", "content": "变量"},
                {"block_type": "body", "content": "变量是可复用的命名容器", "emphasis": ["变量"]},
                {"block_type": "list", "content": "a = 1"},
            ],
        },
    ]
    result = validate_deck(slides, profile="training_deck")
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "scene_training_deck_learning_goals_missing" in codes
    assert "scene_training_deck_knowledge_map_missing" in codes



def test_status_report_generic_title_reduces_score_without_hard_fail():
    baseline = [
        {
            "slide_id": "cover",
            "slide_type": "cover",
            "quality_profile": "status_report",
            "title": "Q3 利润率回升 4 个点",
            "blocks": [
                {"block_type": "title", "content": "Q3 利润率回升 4 个点"},
                {"block_type": "subtitle", "content": "经营汇报"},
            ],
        },
        {
            "slide_id": "summary",
            "slide_type": "summary",
            "quality_profile": "status_report",
            "title": "执行摘要",
            "blocks": [
                {"block_type": "title", "content": "执行摘要"},
                {"block_type": "body", "content": "现状快照"},
                {"block_type": "body", "content": "核心问题"},
                {"block_type": "body", "content": "建议方案"},
                {"block_type": "body", "content": "所需决策"},
            ],
        },
        {
            "slide_id": "content-1",
            "slide_type": "content",
            "quality_profile": "status_report",
            "layout_grid": "split_2",
            "title": "Q3 销售同比增长 23%，主要来自华北区",
            "blocks": [
                {"block_type": "title", "content": "Q3 销售同比增长 23%，主要来自华北区"},
                {"block_type": "body", "content": "华北区渠道扩张拉动收入", "emphasis": ["23%"]},
                {"block_type": "list", "content": "vs 去年 +23%"},
                {"block_type": "image", "content": {"url": "https://example.com/chart.png"}},
            ],
        },
    ]
    degraded = [dict(item) for item in baseline]
    degraded[2] = {
        **baseline[2],
        "title": "销售分析",
        "blocks": [
            {"block_type": "title", "content": "销售分析"},
            {"block_type": "body", "content": "华北区渠道扩张拉动收入", "emphasis": ["23%"]},
            {"block_type": "list", "content": "vs 去年 +23%"},
            {"block_type": "image", "content": {"url": "https://example.com/chart.png"}},
        ],
    }
    assert validate_deck(degraded, profile="status_report").ok is True
    good_score = score_deck_quality(slides=baseline, render_spec={"slides": baseline}, profile="status_report")
    degraded_score = score_deck_quality(slides=degraded, render_spec={"slides": degraded}, profile="status_report")
    assert degraded_score.score < good_score.score
    assert degraded_score.diagnostics.get("scene_rule_advisories", {}).get("scene_status_report_title_generic") == 1
