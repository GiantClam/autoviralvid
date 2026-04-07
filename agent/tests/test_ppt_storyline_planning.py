from __future__ import annotations

from src.ppt_semantic_expander import expand_semantic_support_points
from src.ppt_storyline_planning import is_instructional_context


def test_semantic_support_points_avoid_title_echo_and_boilerplate():
    title = "Legislative process impact path in international relations"
    points = expand_semantic_support_points(
        core_message=title,
        related_points=[
            "How domestic law influences diplomatic strategy",
            "Interaction between international treaties and domestic law",
            "Representative case analysis",
        ],
    )

    assert len(points) >= 3
    joined = " ".join(points)
    assert "Class interaction:" not in joined
    assert "Learning objective:" not in joined
    assert not any(point == title for point in points)


def test_instructional_context_detection_is_disabled():
    assert is_instructional_context("classroom lesson plan for high school") is False
    assert is_instructional_context("楂樹腑璇惧爞 鏁欏璇句欢") is False

