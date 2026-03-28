from src.ppt_planning import enforce_layout_diversity, recommend_layout
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

