from src.ppt_service_v2 import _resolve_quality_profile_id


def test_resolve_quality_profile_id_respects_explicit_value():
    assert (
        _resolve_quality_profile_id(
            "training_deck",
            topic="anything",
            purpose="anything",
            audience="anyone",
            total_pages=10,
        )
        == "training_deck"
    )


def test_resolve_quality_profile_id_auto_picks_training_for_classroom_keywords():
    assert (
        _resolve_quality_profile_id(
            "auto",
            topic="security curriculum",
            purpose="classroom training",
            audience="students",
            total_pages=10,
        )
        == "training_deck"
    )
