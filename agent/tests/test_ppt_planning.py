from src.ppt_planning import (
    build_slide_content_strategy,
    enforce_density_rhythm,
    enforce_layout_diversity,
    enforce_template_family_cohesion,
    paginate_content_overflow,
    recommend_layout,
)
from src.schemas.ppt_outline import StickyNote


def _note(
    *,
    core_message: str = "growth trend",
    density: str = "medium",
    data_elements: list[str] | None = None,
) -> StickyNote:
    return StickyNote(
        page_number=2,
        core_message=core_message,
        layout_hint="split_2",
        content_density=density,  # type: ignore[arg-type]
        data_elements=data_elements or [],
        visual_anchor="text",
        key_points=["p1", "p2", "p3"],
        speaker_notes="notes",
    )


def test_recommend_layout_cover_and_summary_positions():
    note = _note()
    assert recommend_layout(note, 0, 8) == "cover"
    assert recommend_layout(note, 7, 8) == "summary"


def test_recommend_layout_prefers_data_dense_grid():
    note = _note(data_elements=["kpi", "chart", "table", "trend"])
    assert recommend_layout(note, 3, 10) == "bento_6"


def test_recommend_layout_detects_timeline_keywords():
    note = _note(core_message="Q1-Q4 timeline and roadmap")
    assert recommend_layout(note, 3, 10) == "timeline"


def test_enforce_layout_diversity_removes_adjacent_repeats():
    layouts = [
        "cover",
        "split_2",
        "split_2",
        "split_2",
        "grid_3",
        "summary",
    ]
    out = enforce_layout_diversity(layouts)
    for idx in range(1, len(out)):
        assert out[idx] != out[idx - 1]


def test_enforce_layout_diversity_caps_dominant_ratio():
    layouts = [
        "cover",
        "split_2",
        "split_2",
        "split_2",
        "split_2",
        "split_2",
        "split_2",
        "summary",
    ]
    out = enforce_layout_diversity(layouts, max_type_ratio=0.45)
    assert out.count("split_2") <= 3


def test_enforce_layout_diversity_requires_variety_for_long_deck():
    layouts = ["cover"] + ["split_2"] * 10 + ["summary"]
    out = enforce_layout_diversity(layouts, min_layout_variety_for_long=4)
    middle = out[1:-1]
    assert len(set(middle)) >= 4


def test_enforce_layout_diversity_limits_top2_combination():
    layouts = [
        "cover",
        "split_2",
        "grid_3",
        "split_2",
        "grid_3",
        "split_2",
        "grid_3",
        "split_2",
        "summary",
    ]
    out = enforce_layout_diversity(layouts, max_top2_ratio=0.65)
    middle = out[1:-1]
    counts = {}
    for item in middle:
        counts[item] = counts.get(item, 0) + 1
    top2 = sorted(counts.values(), reverse=True)[:2]
    assert sum(top2) <= int(len(out) * 0.65)


def test_enforce_layout_diversity_breaks_abab_loop():
    layouts = ["cover", "split_2", "grid_3", "split_2", "grid_3", "split_2", "grid_3", "summary"]
    out = enforce_layout_diversity(layouts, abab_max_run=4)
    middle = out[1:-1]
    assert middle != ["split_2", "grid_3", "split_2", "grid_3", "split_2", "grid_3"]


def test_enforce_density_rhythm_breaks_three_high_run():
    layouts = [
        "cover",
        "grid_4",
        "bento_5",
        "bento_6",
        "grid_4",
        "split_2",
        "summary",
    ]
    out = enforce_density_rhythm(layouts, max_consecutive_high=2, window_size=5)
    middle = out[1:-1]
    run = 0
    for item in middle:
        if item in {"grid_4", "bento_5", "bento_6"}:
            run += 1
            assert run <= 2
        else:
            run = 0


def test_enforce_density_rhythm_requires_low_or_breathing_every_five_pages():
    layouts = [
        "cover",
        "grid_3",
        "split_2",
        "grid_4",
        "bento_5",
        "timeline",
        "grid_3",
        "summary",
    ]
    out = enforce_density_rhythm(layouts, window_size=5)
    middle = out[1:-1]
    for start in range(0, len(middle) - 4):
        window = middle[start:start + 5]
        assert any(item in {"hero_1", "cover", "summary", "section", "divider"} for item in window)


def test_enforce_template_family_cohesion_breaks_abab_and_reduces_switches():
    families = [
        "hero_tech_cover",
        "architecture_dark_panel",
        "dashboard_dark",
        "architecture_dark_panel",
        "dashboard_dark",
        "architecture_dark_panel",
        "dashboard_dark",
        "hero_dark",
    ]
    locked = [True, False, False, False, False, False, False, True]
    out = enforce_template_family_cohesion(
        families,
        locked_mask=locked,
        max_switch_ratio=0.6,
        abab_max_run=4,
    )
    assert out[0] == "hero_tech_cover"
    assert out[-1] == "hero_dark"
    editable_values = [name for idx, name in enumerate(out) if not locked[idx]]
    switches = sum(1 for i in range(1, len(editable_values)) if editable_values[i] != editable_values[i - 1])
    assert switches / max(1, len(editable_values) - 1) <= 0.6


def test_paginate_content_overflow_splits_text_heavy_slide():
    slides = [
        {
            "slide_id": "s1",
            "slide_type": "content",
            "layout_grid": "split_2",
            "title": "测试分页",
            "blocks": [
                {"block_type": "title", "card_id": "title", "content": "测试分页"},
                {
                    "block_type": "list",
                    "card_id": "list_main",
                    "content": "；".join([f"要点{i}：这是一个比较长的句子用于触发分页策略" for i in range(1, 13)]),
                },
                {"block_type": "kpi", "card_id": "k1", "data": {"number": 95, "unit": "%"}},
            ],
        }
    ]
    out = paginate_content_overflow(
        slides,
        max_bullets_per_slide=4,
        max_chars_per_slide=120,
        max_continuation_pages=3,
    )
    assert len(out) >= 2
    assert out[0]["continuation_total"] == len(out)
    assert out[1]["is_continuation"] is True
    assert out[1]["slide_id"].startswith("s1-cont-")
    for page in out:
        blocks = page.get("blocks") or []
        list_blocks = [b for b in blocks if str(b.get("block_type") or "").lower() == "list"]
        assert list_blocks


def test_paginate_content_overflow_skips_cover():
    slides = [
        {
            "slide_id": "s-cover",
            "slide_type": "cover",
            "layout_grid": "hero_1",
            "title": "封面",
            "blocks": [{"block_type": "title", "content": "封面"}],
        }
    ]
    out = paginate_content_overflow(slides, max_bullets_per_slide=3, max_chars_per_slide=80)
    assert len(out) == 1
    assert out[0]["slide_id"] == "s-cover"


def test_paginate_content_overflow_is_idempotent_for_continuations():
    slides = [
        {
            "slide_id": "s1",
            "slide_type": "content",
            "layout_grid": "split_2",
            "title": "Long Content",
            "blocks": [
                {"block_type": "title", "card_id": "title", "content": "Long Content"},
                {
                    "block_type": "list",
                    "card_id": "list_main",
                    "content": ";".join([f"point {i} with enough words to split" for i in range(1, 13)]),
                },
                {"block_type": "chart", "card_id": "chart_1", "content": {"labels": ["A", "B"], "datasets": [{"data": [10, 20]}]}},
            ],
        }
    ]
    first = paginate_content_overflow(
        slides,
        max_bullets_per_slide=4,
        max_chars_per_slide=100,
        max_continuation_pages=3,
    )
    second = paginate_content_overflow(
        first,
        max_bullets_per_slide=4,
        max_chars_per_slide=100,
        max_continuation_pages=3,
    )
    assert len(second) == len(first)
    assert [item.get("slide_id") for item in second] == [item.get("slide_id") for item in first]


def test_build_slide_content_strategy_enforces_assertive_title_for_generic_message():
    note = StickyNote(
        page_number=3,
        core_message="市场分析",
        layout_hint="grid_3",
        content_density="high",
        data_elements=["kpi", "chart", "trend"],
        visual_anchor="chart",
        key_points=["目标市场规模达500亿", "年复合增长率超过20%", "客户获取成本下降18%"],
        speaker_notes="",
    )
    strategy = build_slide_content_strategy(note, is_zh=True, research_points=[])
    assert strategy.assertion != "市场分析"
    assert any(ch.isdigit() for ch in strategy.assertion)
    assert strategy.page_role == "evidence"
    assert strategy.render_path == "pptxgenjs"
    assert strategy.evidence


def test_build_slide_content_strategy_routes_timeline_to_svg():
    note = StickyNote(
        page_number=4,
        core_message="Execution timeline",
        layout_hint="timeline",
        content_density="medium",
        data_elements=["workflow", "timeline"],
        visual_anchor="workflow",
        key_points=["Q1: validate demand", "Q2: release MVP", "Q3: scale GTM"],
        speaker_notes="",
    )
    strategy = build_slide_content_strategy(note, is_zh=False, research_points=[])
    assert strategy.render_path == "svg"
    assert strategy.page_role == "transition"
    assert strategy.density_hint == "medium"
