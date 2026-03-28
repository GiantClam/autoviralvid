"""Deterministic merge for slide/block scoped retry patches."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


def _slide_key(slide: Dict[str, Any]) -> str:
    for field in ("slide_id", "id", "page_number"):
        value = slide.get(field)
        if value is None:
            continue
        key = str(value).strip()
        if key:
            return key
    return ""


def _block_key(block: Dict[str, Any]) -> str:
    for field in ("block_id", "id"):
        value = block.get(field)
        if value is None:
            continue
        key = str(value).strip()
        if key:
            return key
    return ""


def _merge_blocks(
    base_blocks: List[Dict[str, Any]],
    patch_blocks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out = [deepcopy(item) for item in base_blocks]
    index = {_block_key(block): i for i, block in enumerate(out) if _block_key(block)}
    for patch in patch_blocks:
        patch_key = _block_key(patch)
        if patch_key and patch_key in index:
            out[index[patch_key]] = deepcopy(patch)
        else:
            out.append(deepcopy(patch))
    return out


def merge_slides(
    base: List[Dict[str, Any]],
    patch: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Merge patch slides into base slides.

    Rules:
    - Replace by stable slide key (`slide_id` -> `id` -> `page_number`).
    - Preserve base order.
    - If both sides have `elements`, merge elements by stable block key.
    """
    out = [deepcopy(item) for item in base]
    base_index = {_slide_key(slide): i for i, slide in enumerate(out) if _slide_key(slide)}

    for patch_slide in patch:
        key = _slide_key(patch_slide)
        if key and key in base_index:
            idx = base_index[key]
            merged = deepcopy(out[idx])
            for k, v in patch_slide.items():
                if k == "elements" and isinstance(v, list) and isinstance(merged.get("elements"), list):
                    merged["elements"] = _merge_blocks(merged.get("elements") or [], v)
                else:
                    merged[k] = deepcopy(v)
            out[idx] = merged
            continue

        out.append(deepcopy(patch_slide))

    return out


def merge_render_spec(
    base_render_spec: Dict[str, Any],
    patch_render_spec: Dict[str, Any],
) -> Dict[str, Any]:
    out = deepcopy(base_render_spec or {})
    patch = deepcopy(patch_render_spec or {})

    base_slides = out.get("slides")
    patch_slides = patch.get("slides")
    if isinstance(base_slides, list) and isinstance(patch_slides, list):
        out["slides"] = merge_slides(base_slides, patch_slides)
    elif "slides" in patch:
        out["slides"] = patch["slides"]

    for key, value in patch.items():
        if key == "slides":
            continue
        out[key] = value
    return out

