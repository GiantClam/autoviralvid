from src.ppt_service_v2 import (
    _normalize_retry_scope,
    _resolve_retry_budget,
)


def test_normalize_retry_scope_always_deck():
    assert _normalize_retry_scope("slide") == "deck"
    assert _normalize_retry_scope("deck") == "deck"
    assert _normalize_retry_scope(None) == "deck"


def test_resolve_retry_budget_respects_route_caps():
    assert _resolve_retry_budget(env_max_attempts=5, route_mode="fast", route_policy_max=9) == 1
    assert _resolve_retry_budget(env_max_attempts=5, route_mode="standard", route_policy_max=9) == 2
    assert _resolve_retry_budget(env_max_attempts=5, route_mode="refine", route_policy_max=9) == 3
    assert _resolve_retry_budget(env_max_attempts=1, route_mode="refine", route_policy_max=9) == 1
