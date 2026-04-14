import pytest

from src.ppt_service_v2 import (
    _apply_visual_orchestration,
    _ensure_content_contract,
    _hydrate_image_assets,
)


def test_ensure_content_contract_adds_required_blocks():
    slides = [{"slide_type": "content", "title": "", "blocks": []}]

    fixed = _ensure_content_contract(slides, profile="default")

    assert len(fixed) == 1
    slide = fixed[0]
    assert slide["title"]
    block_types = [str(b.get("block_type") or "") for b in slide.get("blocks") or []]
    assert "title" in block_types
    assert any(t != "title" for t in block_types)


def test_apply_visual_orchestration_returns_copy():
    payload = {"title": "Deck", "slides": [{"slide_id": "s1"}]}

    out = _apply_visual_orchestration(payload)

    assert out == payload
    assert out is not payload


@pytest.mark.asyncio
async def test_hydrate_image_assets_marks_not_hydrated_by_default():
    payload = {"title": "Deck", "slides": []}

    out = await _hydrate_image_assets(payload)

    assert out.get("image_asset_hydrated") is False
