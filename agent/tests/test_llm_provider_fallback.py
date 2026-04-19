from __future__ import annotations

from typing import Any, List

import pytest

import src.openrouter_client as llm_module
from src.openrouter_client import OpenRouterClient, OpenRouterError


class _FakeResponse:
    def __init__(self, status_code: int, *, json_data: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self) -> dict:
        return self._json_data


class _StubAsyncClient:
    responses: List[Any] = []
    calls: List[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        _ = args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, *, headers: dict, json: dict):
        self.__class__.calls.append({"url": url, "headers": headers, "json": json})
        if not self.__class__.responses:
            raise AssertionError("No fake response configured")
        row = self.__class__.responses.pop(0)
        if isinstance(row, Exception):
            raise row
        return row


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    OpenRouterClient._reset_runtime_state_for_tests()
    _StubAsyncClient.responses = []
    _StubAsyncClient.calls = []


def _clear_provider_env(monkeypatch):
    for key in (
        "AIBERM_API_BASE",
        "AIBERM_API_KEY",
        "CRAZYROUTE_API_BASE",
        "CRAZYROUTE_API_KEY",
        "CRAZYROUTER_API_BASE",
        "CRAZYROUTER_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_provider_order_prefers_aiberm_then_crazyroute(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("CRAZYROUTE_API_BASE", "https://crazyroute.example/v1")
    monkeypatch.setenv("CRAZYROUTE_API_KEY", "sk-crazy")

    client = OpenRouterClient()
    names = [row.get("name") for row in client._endpoints]
    assert names[:2] == ["aiberm", "crazyroute"]
    assert "openai" not in names


@pytest.mark.asyncio
async def test_chat_fallback_to_second_gateway_when_primary_fails(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("CRAZYROUTE_API_BASE", "https://crazyroute.example/v1")
    monkeypatch.setenv("CRAZYROUTE_API_KEY", "sk-crazy")

    _StubAsyncClient.responses = [
        _FakeResponse(503, text="aiberm timeout"),
        _FakeResponse(
            200,
            json_data={"choices": [{"message": {"content": "crazyroute-ok"}}]},
        ),
    ]
    _StubAsyncClient.calls = []
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _StubAsyncClient)

    client = OpenRouterClient()
    result = await client.chat_completions(
        model="openai/gpt-5.3-codex",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=64,
    )

    assert result == "crazyroute-ok"
    urls = [row["url"] for row in _StubAsyncClient.calls]
    assert urls == [
        "https://aiberm.example/v1/chat/completions",
        "https://crazyroute.example/v1/chat/completions",
    ]
    sent_models = [row.get("json", {}).get("model") for row in _StubAsyncClient.calls]
    assert sent_models == ["gpt-5.3-codex", "gpt-5.3-codex"]


def test_model_alias_remap_to_unscoped_for_crazyroute(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("CRAZYROUTE_API_BASE", "https://crazyroute.example/v1")
    monkeypatch.setenv("CRAZYROUTE_API_KEY", "sk-crazy")

    client = OpenRouterClient()
    remapped = client._remap_model_for_endpoint(
        requested_model="openai/gpt-5.3-codex",
        api_base="https://crazyroute.example/v1",
        endpoint_name="crazyroute:test",
    )
    assert remapped == "gpt-5.3-codex"


def test_model_alias_remap_to_unscoped_for_crazyrouter_host(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("CRAZYROUTER_API_BASE", "https://crazyrouter.example/v1")
    monkeypatch.setenv("CRAZYROUTER_API_KEY", "sk-crazy")

    client = OpenRouterClient()
    remapped = client._remap_model_for_endpoint(
        requested_model="openai/gpt-5.3-codex",
        api_base="https://crazyrouter.example/v1",
        endpoint_name="crazyroute:test",
    )
    assert remapped == "gpt-5.3-codex"


@pytest.mark.asyncio
async def test_chat_retries_transport_error_before_fallback(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("LLM_TRANSPORT_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("LLM_TRANSPORT_RETRY_BACKOFF_SECONDS", "0")

    _StubAsyncClient.responses = [
        RuntimeError("EOF occurred in violation of protocol (_ssl.c:2427)"),
        _FakeResponse(200, json_data={"choices": [{"message": {"content": "aiberm-ok"}}]}),
    ]
    _StubAsyncClient.calls = []
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _StubAsyncClient)

    client = OpenRouterClient()
    result = await client.chat_completions(
        model="openai/gpt-5.3-codex",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=64,
    )

    assert result == "aiberm-ok"
    urls = [row["url"] for row in _StubAsyncClient.calls]
    assert urls == [
        "https://aiberm.example/v1/chat/completions",
        "https://aiberm.example/v1/chat/completions",
    ]


@pytest.mark.asyncio
async def test_chat_fail_fast_on_non_retryable_request_error(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("CRAZYROUTE_API_BASE", "https://crazyroute.example/v1")
    monkeypatch.setenv("CRAZYROUTE_API_KEY", "sk-crazy")

    _StubAsyncClient.responses = [
        _FakeResponse(422, text='{"error":{"message":"context_length_exceeded"}}'),
    ]
    _StubAsyncClient.calls = []
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _StubAsyncClient)

    client = OpenRouterClient()
    with pytest.raises(OpenRouterError):
        await client.chat_completions(
            model="openai/gpt-5.3-codex",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.2,
            max_tokens=64,
        )

    assert len(_StubAsyncClient.calls) == 1
    assert _StubAsyncClient.calls[0]["url"] == "https://aiberm.example/v1/chat/completions"


@pytest.mark.asyncio
async def test_preflight_chat_uses_single_transport_attempt_per_provider(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("CRAZYROUTE_API_BASE", "https://crazyroute.example/v1")
    monkeypatch.setenv("CRAZYROUTE_API_KEY", "sk-crazy")

    _StubAsyncClient.responses = [
        RuntimeError("transient write failed"),
        _FakeResponse(200, json_data={"choices": [{"message": {"content": "OK"}}]}),
    ]
    _StubAsyncClient.calls = []
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _StubAsyncClient)

    client = OpenRouterClient()
    result = await client.preflight_chat(
        model="openai/gpt-5.3-codex",
        prompt="health check",
        timeout_seconds=8.0,
    )

    assert result.strip().upper() == "OK"
    assert [row["url"] for row in _StubAsyncClient.calls] == [
        "https://aiberm.example/v1/chat/completions",
        "https://crazyroute.example/v1/chat/completions",
    ]


def test_openai_only_config_is_rejected(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.openai.com/v1")

    with pytest.raises(OpenRouterError):
        OpenRouterClient()
