"""Outline storyline builder module."""

from __future__ import annotations

from typing import Dict, List, Sequence

from src.schemas.ppt_outline import StickyNote
from src._ppt_storyline_core import (
    build_research_storyline_notes as _build_research_storyline_notes_impl,
)


def build_research_storyline_notes(
    *,
    topic: str,
    total_pages: int,
    data_points: Sequence[str],
    page_anchors: Dict[int, str] | None = None,
) -> List[StickyNote]:
    """Build outline-level storyline notes for research-driven decks."""
    return _build_research_storyline_notes_impl(
        topic=topic,
        total_pages=total_pages,
        data_points=data_points,
        page_anchors=page_anchors,
    )
