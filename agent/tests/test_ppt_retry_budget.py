import pytest

from src.ppt_service_v2 import _normalize_retry_scope, _resolve_export_channel, _resolve_retry_budget


def test_normalize_retry_scope_defaults_to_deck():
    assert _normalize_retry_scope("invalid") == "deck"
    assert _normalize_retry_scope(None) == "deck"
    assert _normalize_retry_scope("slide") == "deck"


def test_resolve_retry_budget_respects_phase_caps():
    assert _resolve_retry_budget(env_max_attempts=5, route_mode="fast", route_policy_max=4) == 1
    assert _resolve_retry_budget(env_max_attempts=5, route_mode="standard", route_policy_max=4) == 2
    assert _resolve_retry_budget(env_max_attempts=5, route_mode="refine", route_policy_max=4) == 3
    assert _resolve_retry_budget(env_max_attempts=1, route_mode="refine", route_policy_max=4) == 1


def test_resolve_export_channel_rejects_remote(monkeypatch):
    monkeypatch.setenv("PPT_EXPORT_CHANNEL", "remote")
    with pytest.raises(ValueError, match="remote channel is disabled"):
        _resolve_export_channel("auto")

    monkeypatch.setenv("PPT_EXPORT_CHANNEL", "local")
    with pytest.raises(ValueError, match="remote channel is disabled"):
        _resolve_export_channel("remote")


