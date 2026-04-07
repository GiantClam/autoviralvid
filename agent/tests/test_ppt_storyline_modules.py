from __future__ import annotations

from src._ppt_storyline_core import (
    build_research_storyline_notes as legacy_build_research_storyline_notes,
)
from src._ppt_storyline_core import (
    expand_semantic_support_points as legacy_expand_semantic_support_points,
)
from src.ppt_outline_builder import build_research_storyline_notes
from src.ppt_semantic_expander import expand_semantic_support_points


def test_outline_builder_matches_legacy_behavior():
    kwargs = {
        "topic": "AI marketing automation",
        "total_pages": 8,
        "data_points": ["definition", "mechanism", "case study"],
    }
    actual = build_research_storyline_notes(**kwargs)
    expected = legacy_build_research_storyline_notes(**kwargs)
    assert [n.model_dump() for n in actual] == [n.model_dump() for n in expected]


def test_semantic_expander_matches_legacy_behavior():
    kwargs = {
        "core_message": "Legislative process impact path",
        "related_points": ["Domestic law and diplomacy", "International treaty linkage"],
    }
    actual = expand_semantic_support_points(**kwargs)
    expected = legacy_expand_semantic_support_points(**kwargs)
    assert actual == expected


def test_storyline_modules_are_directly_available():
    assert callable(build_research_storyline_notes)
    assert callable(expand_semantic_support_points)
