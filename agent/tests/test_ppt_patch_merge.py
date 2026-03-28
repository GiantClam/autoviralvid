from src.ppt_patch_merge import merge_render_spec, merge_slides


def test_only_failed_slide_is_replaced():
    base = [{"slide_id": "s1", "title": "A"}, {"slide_id": "s2", "title": "B"}]
    patch = [{"slide_id": "s2", "title": "B2"}]
    out = merge_slides(base, patch)
    assert out[0]["title"] == "A"
    assert out[1]["title"] == "B2"


def test_merge_render_spec_keeps_other_slides():
    base = {"mode": "m1", "slides": [{"slide_id": "s1", "title": "X"}]}
    patch = {"mode": "m1", "slides": [{"slide_id": "s2", "title": "Y"}]}
    merged = merge_render_spec(base, patch)
    assert len(merged["slides"]) == 2
    assert merged["slides"][0]["slide_id"] == "s1"
    assert merged["slides"][1]["slide_id"] == "s2"

