import pytest

from src.openrouter_client import OpenRouterClient, OpenRouterError
from src import openrouter_client as openrouter_module


class _FakeResponse:
    def __init__(self, status_code: int, *, text: str = "", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


class _StubAsyncClient:
    responses = []
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers, json):
        self.__class__.calls.append({"url": url, "headers": headers, "json": json})
        if not self.__class__.responses:
            raise RuntimeError("no stub response configured")
        response = self.__class__.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _StreamResponse:
    def __init__(self, status_code: int, lines):
        self.status_code = status_code
        self._lines = list(lines)
        self.text = ""

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _StreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _StubAsyncClientWithStream(_StubAsyncClient):
    stream_responses = []

    def stream(self, method, url, headers, json):
        self.__class__.calls.append(
            {"method": method, "url": url, "headers": headers, "json": json, "stream": True}
        )
        if not self.__class__.stream_responses:
            raise RuntimeError("no stream response configured")
        response = self.__class__.stream_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return _StreamContext(response)


@pytest.mark.asyncio
async def test_fallback_to_openrouter_when_primary_aiberm_fails(monkeypatch):
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")
    monkeypatch.setenv("OPENROUTER_FALLBACK_API_BASE", "https://openrouter.ai/api/v1")

    _StubAsyncClient.calls = []
    _StubAsyncClient.responses = [
        _FakeResponse(503, text="upstream timeout"),
        _FakeResponse(
            200,
            json_data={"choices": [{"message": {"content": "fallback-ok"}}]},
        ),
    ]
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", _StubAsyncClient)

    client = OpenRouterClient()
    result = await client.chat_completions(
        model="openai/gpt-5",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert result == "fallback-ok"
    assert len(_StubAsyncClient.calls) == 2
    assert _StubAsyncClient.calls[0]["url"] == "https://aiberm.example/v1/chat/completions"
    assert _StubAsyncClient.calls[1]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert _StubAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer sk-aiberm"
    assert _StubAsyncClient.calls[1]["headers"]["Authorization"] == "Bearer sk-openrouter"
    assert "HTTP-Referer" not in _StubAsyncClient.calls[0]["headers"]
    assert _StubAsyncClient.calls[1]["headers"]["HTTP-Referer"]


@pytest.mark.asyncio
async def test_fallback_to_aiberm_when_primary_openrouter_fails(monkeypatch):
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")
    # Keep explicit fallback same as primary to ensure code still picks the opposite provider.
    monkeypatch.setenv("OPENROUTER_FALLBACK_API_BASE", "https://openrouter.ai/api/v1")

    _StubAsyncClient.calls = []
    _StubAsyncClient.responses = [
        _FakeResponse(503, text="upstream timeout"),
        _FakeResponse(
            200,
            json_data={"choices": [{"message": {"content": "fallback-aiberm-ok"}}]},
        ),
    ]
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", _StubAsyncClient)

    client = OpenRouterClient(api_base="https://openrouter.ai/api/v1")
    result = await client.chat_completions(
        model="openai/gpt-5",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert result == "fallback-aiberm-ok"
    assert len(_StubAsyncClient.calls) == 2
    assert _StubAsyncClient.calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert _StubAsyncClient.calls[1]["url"] == "https://aiberm.example/v1/chat/completions"
    assert _StubAsyncClient.calls[1]["headers"]["Authorization"] == "Bearer sk-aiberm"


@pytest.mark.asyncio
async def test_raise_combined_error_when_primary_and_fallback_both_fail(monkeypatch):
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")
    monkeypatch.setenv("OPENROUTER_FALLBACK_API_BASE", "https://openrouter.ai/api/v1")

    _StubAsyncClient.calls = []
    _StubAsyncClient.responses = [
        _FakeResponse(503, text="bad gateway"),
        _FakeResponse(403, text='{"error":"denied"}'),
    ]
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", _StubAsyncClient)

    client = OpenRouterClient()
    with pytest.raises(OpenRouterError) as exc_info:
        await client.chat_completions(
            model="openai/gpt-5",
            messages=[{"role": "user", "content": "hello"}],
        )

    message = str(exc_info.value)
    assert "All LLM endpoints failed" in message
    assert "primary HTTP 503" in message
    assert "provider_fallback HTTP 403" in message


@pytest.mark.asyncio
async def test_openrouter_fallback_swaps_banned_author_model(monkeypatch):
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")
    monkeypatch.setenv("OPENROUTER_FALLBACK_API_BASE", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("CONTENT_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct")

    _StubAsyncClient.calls = []
    _StubAsyncClient.responses = [
        _FakeResponse(503, text="upstream timeout"),
        _FakeResponse(
            200,
            json_data={"choices": [{"message": {"content": "ok"}}]},
        ),
    ]
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", _StubAsyncClient)

    client = OpenRouterClient()
    result = await client.chat_completions(
        model="openai/gpt-5.3-codex",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert result == "ok"
    assert len(_StubAsyncClient.calls) == 2
    assert _StubAsyncClient.calls[0]["json"]["model"] == "openai/gpt-5.3-codex"
    assert _StubAsyncClient.calls[1]["json"]["model"] == "meta-llama/llama-3.3-70b-instruct"


@pytest.mark.asyncio
async def test_fallback_when_primary_returns_empty_content(monkeypatch):
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")
    monkeypatch.setenv("OPENROUTER_FALLBACK_API_BASE", "https://openrouter.ai/api/v1")

    _StubAsyncClient.calls = []
    _StubAsyncClient.responses = [
        _FakeResponse(
            200,
            json_data={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "reasoning_content": None,
                        }
                    }
                ]
            },
        ),
        _FakeResponse(
            200,
            json_data={"choices": [{"message": {"content": "fallback-from-empty-ok"}}]},
        ),
    ]
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", _StubAsyncClient)

    client = OpenRouterClient()
    result = await client.chat_completions(
        model="openai/gpt-5.3-codex",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert result == "fallback-from-empty-ok"
    assert len(_StubAsyncClient.calls) == 2
    assert _StubAsyncClient.calls[0]["url"] == "https://aiberm.example/v1/chat/completions"
    assert _StubAsyncClient.calls[1]["url"] == "https://openrouter.ai/api/v1/chat/completions"


@pytest.mark.asyncio
async def test_stream_fallback_on_aiberm_empty_content(monkeypatch):
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")
    monkeypatch.setenv("OPENROUTER_FALLBACK_API_BASE", "https://openrouter.ai/api/v1")

    _StubAsyncClientWithStream.calls = []
    _StubAsyncClientWithStream.responses = [
        _FakeResponse(
            200,
            json_data={
                "choices": [
                    {"message": {"content": None, "reasoning_content": None}},
                ]
            },
        ),
    ]
    _StubAsyncClientWithStream.stream_responses = [
        _StreamResponse(
            200,
            lines=[
                'data: {"id":"chatcmpl-x","choices":[{"delta":{"content":"hello"}}]}',
                'data: {"id":"chatcmpl-x","choices":[{"delta":{"content":" world"}}]}',
                "data: [DONE]",
            ],
        )
    ]
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", _StubAsyncClientWithStream)

    client = OpenRouterClient()
    result = await client.chat_completions(
        model="openai/gpt-5.3-codex",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert result == "hello world"
    assert len(_StubAsyncClientWithStream.calls) == 2
    assert _StubAsyncClientWithStream.calls[0]["url"] == "https://aiberm.example/v1/chat/completions"
    assert _StubAsyncClientWithStream.calls[1]["url"] == "https://aiberm.example/v1/chat/completions"
    assert _StubAsyncClientWithStream.calls[1]["stream"] is True
    assert _StubAsyncClientWithStream.calls[1]["json"]["stream"] is True


@pytest.mark.asyncio
async def test_stream_fallback_on_aiberm_transport_error(monkeypatch):
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")
    monkeypatch.setenv("OPENROUTER_FALLBACK_API_BASE", "https://openrouter.ai/api/v1")

    _StubAsyncClientWithStream.calls = []
    _StubAsyncClientWithStream.responses = [
        RuntimeError("Server disconnected without sending a response."),
    ]
    _StubAsyncClientWithStream.stream_responses = [
        _StreamResponse(
            200,
            lines=[
                'data: {"id":"chatcmpl-y","choices":[{"delta":{"content":"{\\\"ok\\\":true}"}}]}',
                "data: [DONE]",
            ],
        )
    ]
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", _StubAsyncClientWithStream)

    client = OpenRouterClient()
    result = await client.chat_completions(
        model="openai/gpt-5.3-codex",
        messages=[{"role": "user", "content": "hello"}],
        response_format={"type": "json_object"},
    )

    assert result == '{"ok":true}'
    assert len(_StubAsyncClientWithStream.calls) == 2
    assert _StubAsyncClientWithStream.calls[0]["url"] == "https://aiberm.example/v1/chat/completions"
    assert _StubAsyncClientWithStream.calls[1]["url"] == "https://aiberm.example/v1/chat/completions"
    assert _StubAsyncClientWithStream.calls[1]["stream"] is True


@pytest.mark.asyncio
async def test_raise_when_all_endpoints_return_empty_content(monkeypatch):
    monkeypatch.setenv("AIBERM_API_BASE", "https://aiberm.example/v1")
    monkeypatch.setenv("AIBERM_API_KEY", "sk-aiberm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter")
    monkeypatch.setenv("OPENROUTER_FALLBACK_API_BASE", "https://openrouter.ai/api/v1")

    _StubAsyncClient.calls = []
    _StubAsyncClient.responses = [
        _FakeResponse(200, json_data={"choices": [{"message": {"content": None}}]}),
        _FakeResponse(200, json_data={"choices": [{"message": {"content": None}}]}),
    ]
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", _StubAsyncClient)

    client = OpenRouterClient()
    with pytest.raises(OpenRouterError) as exc_info:
        await client.chat_completions(
            model="openai/gpt-5.3-codex",
            messages=[{"role": "user", "content": "hello"}],
        )

    message = str(exc_info.value)
    assert "All LLM endpoints failed" in message
    assert "empty content" in message
