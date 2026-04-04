from __future__ import annotations

from src.ppt_archetype_selector import load_archetype_catalog, select_slide_archetype


def test_archetype_selector_returns_top3_and_confidence():
    slide = {
        "slide_type": "content",
        "layout_grid": "timeline",
        "semantic_type": "workflow",
        "blocks": [
            {"block_type": "title", "content": "Plan"},
            {"block_type": "workflow", "content": "Step 1 -> Step 2"},
        ],
    }
    out = select_slide_archetype(slide, top_k=3, rerank_window=6)
    assert isinstance(out, dict)
    assert isinstance(out.get("selected"), str) and out["selected"]
    assert 0.0 <= float(out.get("confidence") or 0.0) <= 1.0
    candidates = out.get("candidates")
    assert isinstance(candidates, list) and len(candidates) >= 1
    assert len(candidates) <= 3
    assert candidates[0].get("archetype") == out.get("selected")


def test_archetype_selector_respects_explicit_archetype_priority():
    slide = {
        "slide_type": "content",
        "layout_grid": "split_2",
        "archetype": "risk_mitigation",
        "blocks": [
            {"block_type": "title", "content": "Risks"},
            {"block_type": "body", "content": "Main risks and actions"},
        ],
    }
    out = select_slide_archetype(slide, top_k=3, rerank_window=6)
    assert str(out.get("selected") or "").strip().lower() == "risk_mitigation"


def test_archetype_catalog_has_expected_keys():
    catalog = load_archetype_catalog()
    assert isinstance(catalog.get("version"), str)
    assert isinstance(catalog.get("archetypes"), list) and len(catalog["archetypes"]) >= 3
    assert isinstance(catalog.get("role_defaults"), dict)
