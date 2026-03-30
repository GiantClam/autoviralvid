from src.ppt_template_catalog import quality_profile, route_policy, route_recommendation_policy


def test_quality_profile_exposes_orchestration_policy():
    default_profile = quality_profile("default")
    default_orchestration = default_profile.get("orchestration") or {}
    assert bool(default_orchestration.get("require_image_anchor")) is False

    strict_profile = quality_profile("high_density_consulting")
    strict_orchestration = strict_profile.get("orchestration") or {}
    assert bool(strict_orchestration.get("require_image_anchor")) is True
    assert bool((strict_orchestration.get("dense_layout_remap") or {}).get("enabled")) is True
    assert bool((strict_orchestration.get("family_convergence") or {}).get("enabled")) is True


def test_route_policy_and_recommendation_are_catalog_driven():
    refine = route_policy("refine")
    assert refine.get("mode") == "refine"
    assert int(refine.get("max_retry_attempts") or 0) >= 4
    assert bool(refine.get("run_post_render_visual_qa")) is True

    recommendation = route_recommendation_policy()
    assert int(recommendation.get("refine_if_pages_gt") or 0) >= 10
    assert "high_density_consulting" in set(recommendation.get("refine_quality_profiles") or [])
