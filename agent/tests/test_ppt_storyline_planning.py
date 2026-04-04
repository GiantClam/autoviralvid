from __future__ import annotations

from src.ppt_storyline_planning import expand_semantic_support_points


def test_instructional_semantic_support_points_avoid_title_echo_and_boilerplate():
    points = expand_semantic_support_points(
        core_message="立法过程在国际关系中的影响路径",
        related_points=["国内立法如何塑造外交格局", "国际条约与国内法", "案例分析"],
        instructional_context=True,
    )

    assert len(points) >= 3
    joined = " ".join(points)
    assert "先说明" not in joined
    assert "再交代" not in joined
    assert "最后解释" not in joined
    assert not any(point == "立法过程在国际关系中的影响路径" for point in points)
