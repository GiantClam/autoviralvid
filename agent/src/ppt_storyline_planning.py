"""Backward-compatible storyline planning facade.

This module keeps the legacy import surface used by ``ppt_service`` while
delegating implementation to the extracted core modules.

Design rule for the DrawingML-first refactor:
- Do not use teaching/instructional scenario branching in the main pipeline.
- Keep signatures stable so old call sites continue to work.
"""

from __future__ import annotations

from typing import List, Sequence

from src._ppt_storyline_core import (
    build_research_storyline_notes as _build_research_storyline_notes_impl,
    expand_semantic_support_points as _expand_semantic_support_points_impl,
)
from src.schemas.ppt_outline import StickyNote


def is_instructional_context(_: str) -> bool:
    """Deprecated in the new pipeline: always disable instructional branching."""
    return False


def build_instructional_topic_points(
    topic: str,
    *,
    prefer_zh: bool = True,
) -> List[str]:
    """Compatibility helper used by fallback topic expansion paths.

    Generates deterministic generic topic points without scenario-specific
    classroom logic.
    """
    seed = str(topic or "").strip() or ("涓婚" if prefer_zh else "Topic")
    if prefer_zh:
        return [
            f"{seed}鐨勮儗鏅笌瀹氫箟",
            f"{seed}鐨勫叧閿満鍒朵笌缁撴瀯",
            f"{seed}的主要参与方与角色",
            f"{seed}鐨勪唬琛ㄦ渚嬩笌鏁版嵁璇佹嵁",
            f"{seed}闈复鐨勪簤璁闄╀笌绾︽潫",
            f"{seed}鐨勭粨璁轰笌鍚ず",
        ]
    return [
        f"Background and definition of {seed}",
        f"Key mechanisms and structure of {seed}",
        f"Main stakeholders and roles in {seed}",
        f"Representative cases and supporting evidence for {seed}",
        f"Risks, tradeoffs, and controversies around {seed}",
        f"Conclusions and implications of {seed}",
    ]


def build_research_storyline_notes(
    *,
    topic: str,
    total_pages: int,
    data_points: Sequence[str],
    page_anchors: dict[int, str] | None = None,
    instructional_context: bool | None = None,  # kept for compatibility
) -> List[StickyNote]:
    del instructional_context
    return _build_research_storyline_notes_impl(
        topic=topic,
        total_pages=total_pages,
        data_points=data_points,
        page_anchors=page_anchors,
    )


def expand_semantic_support_points(
    *,
    core_message: str,
    related_points: Sequence[str] | None = None,
    instructional_context: bool | None = None,  # kept for compatibility
) -> List[str]:
    del instructional_context
    return _expand_semantic_support_points_impl(
        core_message=core_message,
        related_points=related_points,
    )


