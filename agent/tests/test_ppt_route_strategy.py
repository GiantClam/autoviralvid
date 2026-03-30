from src.ppt_route_strategy import normalize_route_mode, recommend_route_mode, resolve_route_policy


def test_route_strategy_normalizes_unknown_to_standard(monkeypatch):
    monkeypatch.setenv("PPT_ROUTE_MODE", "standard")
    assert normalize_route_mode("unknown") == "standard"


def test_route_strategy_keeps_auto(monkeypatch):
    monkeypatch.setenv("PPT_ROUTE_MODE", "refine")
    assert normalize_route_mode("auto") == "auto"


def test_resolve_route_policy_fast():
    policy = resolve_route_policy("fast")
    assert policy.mode == "fast"
    assert policy.max_retry_attempts == 1
    assert policy.run_post_render_visual_qa is False


def test_recommend_route_mode_by_complexity():
    assert recommend_route_mode(slide_count=4, constraint_count=0, quality_profile="default") == "fast"
    assert recommend_route_mode(slide_count=12, constraint_count=1, quality_profile="default") == "standard"
    assert recommend_route_mode(slide_count=20, constraint_count=0, quality_profile="default") == "refine"


def test_resolve_route_policy_auto_uses_recommendation(monkeypatch):
    monkeypatch.setenv("PPT_ROUTE_MODE", "auto")
    policy = resolve_route_policy("auto", slide_count=4, constraint_count=0, quality_profile="default")
    assert policy.mode == "fast"


def test_route_strategy_uses_catalog_recommendation(monkeypatch):
    monkeypatch.setattr(
        "src.ppt_route_strategy.shared_route_recommendation_policy",
        lambda: {
            "refine_if_pages_gt": 6,
            "refine_if_constraints_gte": 2,
            "refine_quality_profiles": ["strict_profile"],
            "fast_if_pages_lte": 2,
            "fast_if_constraints_eq": 0,
            "fast_quality_profiles": ["default"],
            "fast_visual_densities": ["balanced"],
        },
    )
    assert recommend_route_mode(slide_count=7, constraint_count=0, quality_profile="default") == "refine"
    assert recommend_route_mode(slide_count=2, constraint_count=0, quality_profile="default") == "fast"


def test_route_strategy_uses_catalog_policy_payload(monkeypatch):
    monkeypatch.setattr(
        "src.ppt_route_strategy.shared_route_policy",
        lambda mode: {
            "mode": mode,
            "max_retry_attempts": 5 if mode == "refine" else 2,
            "partial_retry_enabled": mode != "fast",
            "run_post_render_visual_qa": True,
            "require_weighted_quality_score": True,
            "force_rasterization": True,
            "quality_threshold_offset": 3.0 if mode == "refine" else 0.0,
            "warn_threshold_offset": 1.0,
        },
    )
    policy = resolve_route_policy("refine")
    assert policy.mode == "refine"
    assert policy.max_retry_attempts == 5
    assert policy.quality_threshold_offset == 3.0
