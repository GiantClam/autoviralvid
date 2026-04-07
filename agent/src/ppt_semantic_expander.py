"""Semantic support points expansion module."""

from __future__ import annotations

from typing import List, Sequence

from src._ppt_storyline_core import (
    expand_semantic_support_points as _expand_semantic_support_points_impl,
)


def expand_semantic_support_points(
    *,
    core_message: str,
    related_points: Sequence[str] | None = None,
) -> List[str]:
    """Expand compact evidence points into semantically supportive bullets."""
    return _expand_semantic_support_points_impl(
        core_message=core_message,
        related_points=related_points,
    )
