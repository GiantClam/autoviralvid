import src.ppt_service as ppt_service


def test_collect_visual_owner_conflicts_detects_mismatch():
    slides = [
        {
            "slide_id": "s1",
            "template_family": "hero_dark",
            "layout_grid": "split_2",
            "render_path": "pptxgenjs",
        }
    ]
    decision = {
        "version": "v1",
        "deck": {"template_family": "ops_lifecycle_light"},
        "slides": [{"slide_id": "s1", "layout_grid": "timeline", "render_path": "svg"}],
    }
    conflicts = ppt_service._collect_visual_owner_conflicts(slides, decision)
    assert conflicts
    assert any("s1:layout_grid:split_2->timeline" in item for item in conflicts)
    assert any("s1:render_path:pptxgenjs->svg" in item for item in conflicts)


def test_collect_visual_owner_conflicts_ignores_auto_values():
    slides = [{"slide_id": "s1", "template_family": "auto", "layout_grid": "", "render_path": "auto"}]
    decision = {
        "version": "v1",
        "deck": {"template_family": "ops_lifecycle_light"},
        "slides": [{"slide_id": "s1", "layout_grid": "timeline", "render_path": "pptxgenjs"}],
    }
    conflicts = ppt_service._collect_visual_owner_conflicts(slides, decision)
    assert conflicts == []
