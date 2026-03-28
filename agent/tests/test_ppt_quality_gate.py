from src.ppt_quality_gate import validate_deck, validate_layout_diversity, validate_slide


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
