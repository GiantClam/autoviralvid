from src.ppt_scene_rulebook import (
    get_scene_rulebook,
    normalize_scene_rule_profile,
    scene_advisory_rules,
    scene_hard_fail_rules,
    scene_prompt_directives,
)


def test_scene_rulebook_supports_three_target_profiles():
    catalog = get_scene_rulebook()
    assert {"status_report", "investor_pitch", "training_deck"}.issubset(set(catalog.keys()))
    assert normalize_scene_rule_profile("status_report") == "status_report"
    assert normalize_scene_rule_profile("unknown") == ""



def test_scene_rulebook_exposes_machine_checkable_hard_fail_rules():
    for profile in ("status_report", "investor_pitch", "training_deck"):
        hard_rules = scene_hard_fail_rules(profile)
        assert hard_rules
        assert all(bool(rule.get("machine_checkable")) for rule in hard_rules)
        assert scene_advisory_rules(profile)



def test_scene_rulebook_formats_weighted_prompt_directives():
    directives = scene_prompt_directives("training_deck", slide_type="cover")
    assert directives
    assert any("[课程讲义|Must]" in item for item in directives)
