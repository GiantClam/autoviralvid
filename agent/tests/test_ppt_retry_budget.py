from src.ppt_service import _normalize_retry_scope, _resolve_retry_budget


def test_normalize_retry_scope_defaults_to_deck():
    assert _normalize_retry_scope("invalid") == "deck"
    assert _normalize_retry_scope(None) == "deck"
    assert _normalize_retry_scope("slide") == "slide"


def test_resolve_retry_budget_respects_phase_caps():
    assert _resolve_retry_budget(env_max_attempts=5, route_mode="fast", route_policy_max=4) == 1
    assert _resolve_retry_budget(env_max_attempts=5, route_mode="standard", route_policy_max=4) == 2
    assert _resolve_retry_budget(env_max_attempts=5, route_mode="refine", route_policy_max=4) == 3
    assert _resolve_retry_budget(env_max_attempts=1, route_mode="refine", route_policy_max=4) == 1
