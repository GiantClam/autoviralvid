from __future__ import annotations

from types import SimpleNamespace

from src.ppt_export_retry_utils import (
    collect_issue_retry_target_slides,
    degrade_render_paths_for_retry,
)


def test_degrade_render_paths_for_retry_updates_non_svg_paths():
    slides = [
        {"slide_id": "s1", "render_path": "png"},
        {"slide_id": "s2", "render_path": "svg"},
        {"id": "s3", "render_path": "bitmap"},
    ]
    out = degrade_render_paths_for_retry(
        seed_slides=slides,
        failure_code="schema_invalid",
        scope="deck",
        scoped_slide_ids=[],
    )

    assert out["applied"] is True
    assert out["failure_code"] == "schema_invalid"
    assert out["changed_slide_ids"] == ["s1", "s3"]
    assert slides[0]["render_path"] == "svg"
    assert slides[1]["render_path"] == "svg"
    assert slides[2]["render_path"] == "svg"


def test_collect_issue_retry_target_slides_dedupes_and_skips_deck():
    issues = [
        SimpleNamespace(slide_id="s1", retry_target_ids=["s2", "deck", "s3"]),
        SimpleNamespace(slide_id="s2", retry_target_ids=["s2", "s4"]),
        SimpleNamespace(slide_id="deck", retry_target_ids=[]),
    ]
    out = collect_issue_retry_target_slides(issues)
    assert out == ["s2", "s3", "s1", "s4"]

