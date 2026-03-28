import pytest
from pydantic import ValidationError

from src.schemas.ppt_v7 import DialogueLine, PresentationData, SlideData


def _make_slide(page_number: int, slide_type: str) -> SlideData:
    return SlideData(
        page_number=page_number,
        slide_type=slide_type,  # type: ignore[arg-type]
        markdown=f"# Slide {page_number}\n<mark>{page_number * 10}%</mark>",
        script=[DialogueLine(role="host", text=f"Core metric is {page_number * 10}%")],
        bg_image_keyword="industrial business",
        actions=[],
    )


def test_presentation_schema_accepts_valid_layout():
    slides = [
        _make_slide(1, "cover"),
        _make_slide(2, "toc"),
        _make_slide(3, "grid_2"),
        _make_slide(4, "grid_3"),
        _make_slide(5, "divider"),
        _make_slide(6, "quote_stat"),
        _make_slide(7, "timeline"),
        _make_slide(8, "summary"),
    ]
    data = PresentationData(title="Demo Presentation", design_system="tech_blue", slides=slides)
    assert len(data.slides) == 8


def test_markdown_requires_mark_tag():
    with pytest.raises(ValidationError):
        SlideData(
            page_number=1,
            slide_type="cover",
            markdown="# No highlight",
            script=[DialogueLine(role="host", text="Narration text")],
            actions=[],
        )


def test_dialogue_rejects_banned_prefix():
    with pytest.raises(ValidationError):
        DialogueLine(role="host", text="这一页我们先看增长数据")


def test_presentation_rejects_adjacent_same_type():
    slides = [
        _make_slide(1, "cover"),
        _make_slide(2, "toc"),
        _make_slide(3, "grid_2"),
        _make_slide(4, "grid_2"),
        _make_slide(5, "summary"),
    ]
    with pytest.raises(ValidationError):
        PresentationData(title="Adjacent Duplicate", design_system="tech_blue", slides=slides)


def test_markdown_visible_text_limit_is_configurable(monkeypatch):
    long_mark = "<mark>" + ("growth" * 25) + "</mark>"
    markdown = f"# Test\n{long_mark}"

    monkeypatch.setenv("PPT_V7_SCREEN_TEXT_MAX_CHARS", "220")
    SlideData(
        page_number=1,
        slide_type="cover",
        markdown=markdown,
        script=[DialogueLine(role="host", text="Core metric keeps growing")],
        actions=[],
    )

    monkeypatch.setenv("PPT_V7_SCREEN_TEXT_MAX_CHARS", "40")
    with pytest.raises(ValidationError):
        SlideData(
            page_number=1,
            slide_type="cover",
            markdown=markdown,
            script=[DialogueLine(role="host", text="Core metric keeps growing")],
            actions=[],
        )
