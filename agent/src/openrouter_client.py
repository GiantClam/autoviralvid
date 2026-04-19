import json
import logging
import asyncio
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

_FAILOVER_STATUS_CODES = {401, 403, 404, 408, 409, 425, 429, 500, 502, 503, 504}
_PROVIDER_CYCLE: Tuple[str, str] = ("aiberm", "crazyroute")
_AIBERM_LIKE_MODEL_ALIASES: Dict[str, str] = {
    # Gateways expose OpenAI models as unscoped ids.
    "openai/gpt-5.3-codex": "gpt-5.3-codex",
    "gpt-5.3-codex": "gpt-5.3-codex",
}
_DEFAULT_GLOBAL_MODEL_ALIASES: Dict[str, str] = dict(_AIBERM_LIKE_MODEL_ALIASES)
_DEFAULT_PROVIDER_MODEL_ALIASES: Dict[str, Dict[str, str]] = {
    # AIBERM-like gateways expose models as unscoped ids.
    "aiberm": dict(_AIBERM_LIKE_MODEL_ALIASES),
    "crazyroute": dict(_AIBERM_LIKE_MODEL_ALIASES),
}


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    _runtime_state: Dict[str, Any] = {
        "last_success_provider": None,
        "round_robin_cursor": 0,
        "providers": {},
    }

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        referer: Optional[str] = None,
        title: str = "SaleAgent",
    ) -> None:
        self.referer = referer or os.getenv("EMBEDDING_REFERER") or os.getenv("SITE_URL") or "https://saleagent.app"
        self.title = title

        # Use generic proxy env first; keep legacy OPENROUTER_* as compatibility fallback.
        proxy = os.getenv("LLM_PROXY") or os.getenv("OPENROUTER_PROXY")
        http_proxy = (
            os.getenv("LLM_HTTP_PROXY")
            or os.getenv("OPENROUTER_HTTP_PROXY")
            or os.getenv("HTTP_PROXY")
        )
        https_proxy = (
            os.getenv("LLM_HTTPS_PROXY")
            or os.getenv("OPENROUTER_HTTPS_PROXY")
            or os.getenv("HTTPS_PROXY")
        )
        self.proxy: Optional[str] = proxy or https_proxy or http_proxy

        self._failure_threshold = max(
            1, int(str(os.getenv("LLM_PROVIDER_FAILURE_THRESHOLD", "2")).strip() or "2")
        )
        self._cooldown_seconds = max(
            1, int(str(os.getenv("LLM_PROVIDER_COOLDOWN_SECONDS", "90")).strip() or "90")
        )
        self._transport_max_attempts = max(
            1, int(str(os.getenv("LLM_TRANSPORT_MAX_ATTEMPTS", "2")).strip() or "2")
        )
        self._transport_retry_backoff_seconds = max(
            0.0,
            float(str(os.getenv("LLM_TRANSPORT_RETRY_BACKOFF_SECONDS", "0.8")).strip() or "0.8"),
        )
        self._http_connect_timeout_seconds = max(
            2.0,
            float(str(os.getenv("LLM_HTTP_CONNECT_TIMEOUT_SECONDS", "20")).strip() or "20"),
        )
        self._http_read_timeout_seconds = max(
            10.0,
            float(str(os.getenv("LLM_HTTP_READ_TIMEOUT_SECONDS", "240")).strip() or "240"),
        )
        self._http_write_timeout_seconds = max(
            5.0,
            float(str(os.getenv("LLM_HTTP_WRITE_TIMEOUT_SECONDS", "60")).strip() or "60"),
        )
        self._http_pool_timeout_seconds = max(
            5.0,
            float(str(os.getenv("LLM_HTTP_POOL_TIMEOUT_SECONDS", "60")).strip() or "60"),
        )

        self._endpoints = self._build_endpoints(api_base=api_base, api_key=api_key)
        self._endpoint_by_provider: Dict[str, Dict[str, str]] = {
            endpoint["provider"]: endpoint
            for endpoint in self._endpoints
            if endpoint.get("provider") in _PROVIDER_CYCLE
        }
        self._extra_endpoints: List[Dict[str, str]] = [
            endpoint for endpoint in self._endpoints if endpoint.get("provider") not in _PROVIDER_CYCLE
        ]
        self.api_base = self._endpoints[0]["base"]
        self.api_key = self._endpoints[0]["key"]
        self._global_model_aliases = dict(_DEFAULT_GLOBAL_MODEL_ALIASES)
        self._global_model_aliases.update(self._load_aliases_from_env("LLM_MODEL_ALIAS_MAP_JSON"))
        self._provider_model_aliases = self._build_provider_alias_maps()
        self._ensure_provider_runtime_slots()

    @classmethod
    def _reset_runtime_state_for_tests(cls) -> None:
        cls._runtime_state = {
            "last_success_provider": None,
            "round_robin_cursor": 0,
            "providers": {},
        }

    @staticmethod
    def _format_exception(exc: Exception) -> str:
        text = str(exc).strip()
        if text:
            return f"{exc.__class__.__name__}: {text}"
        return f"{exc.__class__.__name__}: {exc!r}"

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    @staticmethod
    def _is_provider_cycle_member(provider: str) -> bool:
        return provider in _PROVIDER_CYCLE

    def _ensure_provider_runtime_slots(self) -> None:
        providers_state = self.__class__._runtime_state.setdefault("providers", {})
        for provider in _PROVIDER_CYCLE:
            providers_state.setdefault(
                provider,
                {
                    "state": "closed",  # closed | open
                    "consecutive_failures": 0,
                    "cooldown_until": 0.0,
                    "probe_pending": False,
                },
            )

    def _provider_runtime(self, provider: str) -> Dict[str, Any]:
        self._ensure_provider_runtime_slots()
        providers_state = self.__class__._runtime_state["providers"]
        return providers_state[provider]

    def _mark_provider_success(self, provider: str) -> None:
        if not self._is_provider_cycle_member(provider):
            return
        state = self._provider_runtime(provider)
        state["state"] = "closed"
        state["consecutive_failures"] = 0
        state["cooldown_until"] = 0.0
        state["probe_pending"] = False
        self.__class__._runtime_state["last_success_provider"] = provider
        logger.info("[OpenRouterClient] provider %s marked healthy (last-success updated)", provider)

    def _mark_provider_failure(self, provider: str, detail: str = "") -> None:
        if not self._is_provider_cycle_member(provider):
            return
        state = self._provider_runtime(provider)
        now = self._now()
        if state.get("state") == "open":
            state["cooldown_until"] = now + float(self._cooldown_seconds)
            state["consecutive_failures"] = max(
                int(state.get("consecutive_failures", 0)),
                self._failure_threshold,
            )
            state["probe_pending"] = True
            logger.warning(
                "[OpenRouterClient] provider %s probe failed, extend cooldown %.1fs detail=%s",
                provider,
                float(self._cooldown_seconds),
                detail,
            )
            return

        failures = int(state.get("consecutive_failures", 0)) + 1
        state["consecutive_failures"] = failures
        if failures >= self._failure_threshold:
            state["state"] = "open"
            state["cooldown_until"] = now + float(self._cooldown_seconds)
            state["probe_pending"] = True
            logger.warning(
                "[OpenRouterClient] provider %s circuit opened after %s failures, cooldown %.1fs detail=%s",
                provider,
                failures,
                float(self._cooldown_seconds),
                detail,
            )
        else:
            logger.warning(
                "[OpenRouterClient] provider %s failure %s/%s detail=%s",
                provider,
                failures,
                self._failure_threshold,
                detail,
            )

    def _provider_in_cooldown(self, provider: str, now: Optional[float] = None) -> bool:
        if not self._is_provider_cycle_member(provider):
            return False
        state = self._provider_runtime(provider)
        if state.get("state") != "open":
            return False
        check_ts = self._now() if now is None else now
        return check_ts < float(state.get("cooldown_until", 0.0))

    def _provider_probe_ready(self, provider: str, now: Optional[float] = None) -> bool:
        if not self._is_provider_cycle_member(provider):
            return False
        state = self._provider_runtime(provider)
        if state.get("state") != "open":
            return False
        check_ts = self._now() if now is None else now
        return check_ts >= float(state.get("cooldown_until", 0.0)) and bool(
            state.get("probe_pending", False)
        )

    def _ordered_endpoints_for_request(self) -> List[Dict[str, Any]]:
        now = self._now()
        cursor = int(self.__class__._runtime_state.get("round_robin_cursor", 0)) % len(_PROVIDER_CYCLE)
        cycle = list(_PROVIDER_CYCLE[cursor:]) + list(_PROVIDER_CYCLE[:cursor])
        self.__class__._runtime_state["round_robin_cursor"] = (cursor + 1) % len(_PROVIDER_CYCLE)

        healthy: Dict[str, Dict[str, str]] = {}
        probe_ready: Dict[str, Dict[str, str]] = {}
        for provider in cycle:
            endpoint = self._endpoint_by_provider.get(provider)
            if not endpoint:
                continue
            if self._provider_in_cooldown(provider, now=now):
                continue
            if self._provider_probe_ready(provider, now=now):
                probe_ready[provider] = endpoint
                continue
            healthy[provider] = endpoint

        ordered: List[Dict[str, Any]] = []
        used: set[str] = set()
        for provider in cycle:
            endpoint = probe_ready.get(provider)
            if not endpoint:
                continue
            row = dict(endpoint)
            row["attempt_mode"] = "recovery_probe"
            ordered.append(row)
            used.add(provider)
            state = self._provider_runtime(provider)
            state["probe_pending"] = False
            break

        last_success = self.__class__._runtime_state.get("last_success_provider")
        if (
            isinstance(last_success, str)
            and last_success in healthy
            and last_success not in used
        ):
            endpoint = dict(healthy[last_success])
            endpoint["attempt_mode"] = "last_success"
            ordered.append(endpoint)
            used.add(last_success)

        for provider in cycle:
            if provider in used:
                continue
            endpoint = healthy.get(provider)
            if not endpoint:
                continue
            row = dict(endpoint)
            row["attempt_mode"] = "round_robin"
            ordered.append(row)
            used.add(provider)

        if not ordered:
            # All providers are cooling down. Force one probe to avoid total outage.
            for provider in cycle:
                endpoint = self._endpoint_by_provider.get(provider)
                if not endpoint:
                    continue
                row = dict(endpoint)
                row["attempt_mode"] = "forced_probe"
                ordered.append(row)
                break

        for endpoint in self._extra_endpoints:
            row = dict(endpoint)
            row["attempt_mode"] = "extra_fallback"
            ordered.append(row)

        return ordered

    @staticmethod
    def _load_aliases_from_env(env_name: str) -> Dict[str, str]:
        raw = str(os.getenv(env_name, "")).strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            logger.warning("[OpenRouterClient] Invalid %s JSON, ignoring", env_name)
            return {}
        if not isinstance(parsed, dict):
            logger.warning("[OpenRouterClient] %s must be a JSON object, ignoring", env_name)
            return {}
        out: Dict[str, str] = {}
        for key, value in parsed.items():
            src = str(key or "").strip()
            dst = str(value or "").strip()
            if src and dst:
                out[src] = dst
        return out

    def _build_provider_alias_maps(self) -> Dict[str, Dict[str, str]]:
        merged: Dict[str, Dict[str, str]] = {
            provider: dict(mapping)
            for provider, mapping in _DEFAULT_PROVIDER_MODEL_ALIASES.items()
        }
        env_overrides = {
            "aiberm": self._load_aliases_from_env("AIBERM_MODEL_ALIAS_MAP_JSON"),
            "crazyroute": self._load_aliases_from_env("CRAZYROUTE_MODEL_ALIAS_MAP_JSON"),
        }
        for provider, overrides in env_overrides.items():
            if overrides:
                merged.setdefault(provider, {}).update(overrides)
        return merged

    @staticmethod
    def _resolve_alias(model: str, mapping: Dict[str, str]) -> str:
        if not mapping:
            return model
        direct = mapping.get(model)
        if direct:
            return direct
        lowered = model.lower()
        for source, target in mapping.items():
            if str(source).lower() == lowered:
                return target
        return model

    @staticmethod
    def _provider_from_base(api_base: str) -> str:
        lowered = OpenRouterClient._normalize_base(api_base).lower()
        if "api.openai.com" in lowered:
            return "openai"
        aiberm_base = OpenRouterClient._normalize_base(os.getenv("AIBERM_API_BASE"))
        crazyroute_base = OpenRouterClient._normalize_base(
            os.getenv("CRAZYROUTE_API_BASE") or os.getenv("CRAZYROUTER_API_BASE")
        )
        if "aiberm" in lowered or (aiberm_base and lowered == aiberm_base.lower()):
            return "aiberm"
        if (
            "crazyroute" in lowered
            or "crazyrouter" in lowered
            or (crazyroute_base and lowered == crazyroute_base.lower())
        ):
            return "crazyroute"
        return "default"

    def _remap_model_for_endpoint(
        self,
        *,
        requested_model: str,
        api_base: str,
        endpoint_name: str,
    ) -> str:
        model = str(requested_model or "").strip()
        if not model:
            return model
        provider = self._provider_from_base(api_base)
        mapped = self._resolve_alias(model, self._global_model_aliases)
        mapped = self._resolve_alias(
            mapped,
            self._provider_model_aliases.get(provider, {}),
        )
        if mapped != model:
            logger.info(
                "[OpenRouterClient] remap model for %s (%s): %s -> %s",
                endpoint_name,
                provider,
                model,
                mapped,
            )
        return mapped

    def _build_endpoints(self, *, api_base: Optional[str], api_key: Optional[str]) -> List[Dict[str, str]]:
        aiberm_base = self._normalize_base(os.getenv("AIBERM_API_BASE"))
        crazyroute_base = self._normalize_base(
            os.getenv("CRAZYROUTE_API_BASE") or os.getenv("CRAZYROUTER_API_BASE")
        )
        primary_base = self._normalize_base(
            api_base
            or os.getenv("AIBERM_API_BASE")
            or os.getenv("CRAZYROUTE_API_BASE")
            or os.getenv("CRAZYROUTER_API_BASE")
        )
        aiberm_key = os.getenv("AIBERM_API_KEY")
        crazyroute_key = os.getenv("CRAZYROUTE_API_KEY") or os.getenv("CRAZYROUTER_API_KEY")

        def _pick_key_for_provider(provider: str) -> Optional[str]:
            if provider == "aiberm":
                return aiberm_key
            if provider == "crazyroute":
                return crazyroute_key
            return None

        default_any_key = aiberm_key or crazyroute_key
        if not (api_key or default_any_key):
            raise OpenRouterError(
                "missing AIBERM_API_KEY or CRAZYROUTE_API_KEY"
            )

        provider_bases: Dict[str, str] = {
            "aiberm": aiberm_base,
            "crazyroute": crazyroute_base,
        }
        provider_keys: Dict[str, Optional[str]] = {
            provider: _pick_key_for_provider(provider)
            for provider in _PROVIDER_CYCLE
        }

        primary_provider = self._provider_from_base(primary_base)
        extra_endpoints: List[Dict[str, str]] = []
        if primary_provider in _PROVIDER_CYCLE:
            provider_bases[primary_provider] = primary_base
            if api_key:
                provider_keys[primary_provider] = api_key
        elif primary_base:
            extra_endpoints.append(
                {
                    "name": "primary_custom",
                    "provider": "default",
                    "base": primary_base,
                    "key": api_key or default_any_key or "",
                }
            )

        endpoints: List[Dict[str, str]] = []
        for provider in _PROVIDER_CYCLE:
            base = self._normalize_base(provider_bases.get(provider, ""))
            key = (provider_keys.get(provider) or default_any_key or "").strip()
            if not base or not key:
                continue
            endpoints.append(
                {
                    "name": provider,
                    "provider": provider,
                    "base": base,
                    "key": key,
                }
            )

        seen_bases = {endpoint["base"] for endpoint in endpoints}
        for endpoint in extra_endpoints:
            base = self._normalize_base(endpoint.get("base", ""))
            key = str(endpoint.get("key", "") or "").strip()
            if not base or not key or base in seen_bases:
                continue
            seen_bases.add(base)
            endpoints.append(
                {
                    "name": endpoint.get("name", "extra_fallback"),
                    "provider": endpoint.get("provider", "default"),
                    "base": base,
                    "key": key,
                }
            )

        if not endpoints:
            raise OpenRouterError(
                "No LLM endpoints configured. Set AIBERM_API_BASE/KEY or CRAZYROUTE_API_BASE/KEY."
            )
        return endpoints

    def _headers(self, *, api_base: str, api_key: str) -> Dict[str, str]:
        _ = api_base
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _normalize_base(raw: str) -> str:
        return str(raw or "").strip().rstrip("/")

    @staticmethod
    def _is_aiberm_like_base(api_base: str) -> bool:
        return OpenRouterClient._provider_from_base(api_base) in {"aiberm", "crazyroute"}

    def _extract_text_from_stream_delta(self, chunk: Dict[str, Any]) -> str:
        try:
            choice = (chunk.get("choices") or [None])[0] or {}
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str):
                return content
            reasoning_content = delta.get("reasoning_content")
            if isinstance(reasoning_content, str):
                return reasoning_content
            text = self._extract_text_from_content(content)
            if text:
                return text
            text = self._extract_text_from_content(reasoning_content)
            if text:
                return text
        except Exception:
            return ""
        return ""

    async def _retry_provider_via_stream(
        self,
        *,
        client: Any,
        api_base: str,
        api_key: str,
        endpoint_name: str,
        payload: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        stream_payload = dict(payload)
        stream_payload["stream"] = True

        stream_fn = getattr(client, "stream", None)
        if stream_fn is None:
            return None, f"{endpoint_name} stream fallback unavailable: client has no stream()"

        try:
            async with stream_fn(
                "POST",
                f"{api_base}/chat/completions",
                headers=self._headers(api_base=api_base, api_key=api_key),
                json=stream_payload,
            ) as response:
                if response.status_code != 200:
                    return (
                        None,
                        f"{endpoint_name} stream fallback HTTP {response.status_code}: {response.text[:1000]}",
                    )
                chunks: List[str] = []
                model_name = str(payload.get("model") or "")
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    text_line = str(line).strip()
                    if not text_line.startswith("data:"):
                        continue
                    data = text_line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except Exception:
                        continue
                    model_name = str(chunk.get("model") or model_name or "")
                    text_piece = self._extract_text_from_stream_delta(chunk)
                    if text_piece:
                        chunks.append(text_piece)
                merged_text = "".join(chunks).strip()
                if not merged_text:
                    return None, f"{endpoint_name} stream fallback empty content"
                return (
                    {
                        "object": "chat.completion",
                        "model": model_name,
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": merged_text},
                                "finish_reason": "stop",
                            }
                        ],
                    },
                    None,
                )
        except Exception as exc:
            return None, (
                f"{endpoint_name} stream fallback transport error: "
                f"{self._format_exception(exc)}"
            )

    @staticmethod
    def _is_failover_status(status_code: int, error_text: str) -> bool:
        if status_code in _FAILOVER_STATUS_CODES or status_code >= 500:
            return True
        lowered = str(error_text or "").lower()
        return any(
            token in lowered
            for token in (
                "timeout",
                "temporarily unavailable",
                "upstream",
                "gateway",
                "network",
                "connection reset",
            )
        )

    @staticmethod
    def _is_non_retryable_request_error(status_code: int, error_text: str) -> bool:
        if status_code not in {400, 422}:
            return False
        lowered = str(error_text or "").lower()
        # model_not_found should still allow provider-level failover.
        if "model_not_found" in lowered or "unsupported model" in lowered:
            return False
        return any(
            token in lowered
            for token in (
                "invalid_request_error",
                "context_length_exceeded",
                "maximum context length",
                "too many tokens",
                "validation error",
                "unprocessable entity",
                "json schema",
                "response_format",
                "invalid messages",
            )
        )

    @staticmethod
    def _extract_text_from_content(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, dict):
            for key in ("text", "content", "output_text"):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return ""
        if isinstance(content, list):
            parts: List[str] = []
            for part in content:
                if isinstance(part, str):
                    if part.strip():
                        parts.append(part.strip())
                    continue
                if not isinstance(part, dict):
                    continue
                text_value = part.get("text") or part.get("content") or part.get("output_text")
                if isinstance(text_value, str) and text_value.strip():
                    parts.append(text_value.strip())
            return "\n".join([p for p in parts if p]).strip()
        return ""

    def _extract_text_from_response(self, data: Dict[str, Any]) -> str:
        try:
            choice = (data.get("choices") or [None])[0] or {}
            msg = choice.get("message") or {}

            text = self._extract_text_from_content(msg.get("content"))
            if text:
                return text

            for key in ("reasoning", "reasoning_content", "output_text"):
                text = self._extract_text_from_content(msg.get(key))
                if text:
                    return text

            reasoning_details = msg.get("reasoning_details")
            if isinstance(reasoning_details, list):
                for detail in reasoning_details:
                    text = self._extract_text_from_content(detail)
                    if text:
                        return text

            text = self._extract_text_from_content(choice.get("text"))
            if text:
                return text
            text = self._extract_text_from_content(data.get("output_text"))
            if text:
                return text
        except Exception as exc:
            logger.warning("[OpenRouterClient] failed to extract text from response: %s", exc)
        return ""

    def _resolve_model_for_endpoint(
        self,
        *,
        requested_model: str,
        api_base: str,
        endpoint_name: str,
    ) -> str:
        return self._remap_model_for_endpoint(
            requested_model=requested_model,
            api_base=api_base,
            endpoint_name=endpoint_name,
        )

    async def _post_chat_json(
        self,
        request_payload: Dict[str, Any],
        *,
        transport_max_attempts: Optional[int] = None,
        timeout_overrides: Optional[Dict[str, float]] = None,
        allow_stream_fallback: bool = True,
    ) -> Dict[str, Any]:
        attempt_errors: List[str] = []
        request_endpoints = self._ordered_endpoints_for_request()
        timeout_overrides = timeout_overrides or {}
        timeout_config = httpx.Timeout(
            connect=float(timeout_overrides.get("connect", self._http_connect_timeout_seconds)),
            read=float(timeout_overrides.get("read", self._http_read_timeout_seconds)),
            write=float(timeout_overrides.get("write", self._http_write_timeout_seconds)),
            pool=float(timeout_overrides.get("pool", self._http_pool_timeout_seconds)),
        )
        max_attempts = max(1, int(transport_max_attempts or self._transport_max_attempts))
        async with httpx.AsyncClient(timeout=timeout_config, proxy=self.proxy) as client:
            for idx, endpoint in enumerate(request_endpoints):
                api_base = endpoint["base"]
                api_key = endpoint["key"]
                provider = endpoint.get("provider") or self._provider_from_base(api_base)
                attempt_mode = endpoint.get("attempt_mode") or "fallback"
                endpoint_name = f"{provider}:{attempt_mode}" if provider else (endpoint.get("name") or f"endpoint-{idx + 1}")
                effective_payload = dict(request_payload)
                effective_payload["model"] = self._resolve_model_for_endpoint(
                    requested_model=str(request_payload.get("model") or ""),
                    api_base=api_base,
                    endpoint_name=endpoint_name,
                )
                logger.info("[OpenRouterClient] Request: POST %s/chat/completions (%s)", api_base, endpoint_name)
                logger.debug(
                    "[OpenRouterClient] Request payload: %s",
                    json.dumps(effective_payload, ensure_ascii=False, indent=2),
                )

                response: Optional[httpx.Response] = None
                transport_exc: Optional[Exception] = None
                for transport_attempt in range(1, max_attempts + 1):
                    try:
                        response = await client.post(
                            f"{api_base}/chat/completions",
                            headers=self._headers(api_base=api_base, api_key=api_key),
                            json=effective_payload,
                        )
                        transport_exc = None
                        break
                    except Exception as exc:
                        transport_exc = exc
                        retryable = transport_attempt < max_attempts
                        detail = self._format_exception(exc)
                        if retryable:
                            delay = float(self._transport_retry_backoff_seconds) * transport_attempt
                            logger.warning(
                                "[OpenRouterClient] %s transport attempt %s/%s failed (%s), retrying in %.1fs",
                                endpoint_name,
                                transport_attempt,
                                max_attempts,
                                detail,
                                delay,
                            )
                            if delay > 0:
                                await asyncio.sleep(delay)
                            continue
                        break

                if transport_exc is not None:
                    error_msg = (
                        f"{endpoint_name} transport error: "
                        f"{self._format_exception(transport_exc)}"
                    )
                    attempt_errors.append(error_msg)
                    logger.warning("[OpenRouterClient] %s", error_msg)
                    if allow_stream_fallback and self._is_aiberm_like_base(api_base):
                        stream_data, stream_error = await self._retry_provider_via_stream(
                            client=client,
                            api_base=api_base,
                            api_key=api_key,
                            endpoint_name=endpoint_name,
                            payload=effective_payload,
                        )
                        if stream_data is not None:
                            self._mark_provider_success(str(provider))
                            logger.info(
                                "[OpenRouterClient] stream fallback succeeded on %s after transport error",
                                endpoint_name,
                            )
                            return stream_data
                        if stream_error:
                            attempt_errors.append(stream_error)
                            logger.warning("[OpenRouterClient] %s", stream_error)
                    self._mark_provider_failure(str(provider), detail=error_msg)
                    if idx < len(request_endpoints) - 1:
                        logger.warning("[OpenRouterClient] switching to fallback endpoint after transport error")
                        continue
                    if len(attempt_errors) > 1:
                        raise OpenRouterError(
                            f"All LLM endpoints failed: {' | '.join(attempt_errors)}"
                        ) from transport_exc
                    raise OpenRouterError(f"LLM request failed: {error_msg}") from transport_exc

                assert response is not None

                logger.info("[OpenRouterClient] Response status(%s): %s", endpoint_name, response.status_code)
                if response.status_code != 200:
                    error_text = response.text[:1000]
                    error_msg = f"{endpoint_name} HTTP {response.status_code}: {error_text}"
                    attempt_errors.append(error_msg)
                    self._mark_provider_failure(str(provider), detail=error_msg)
                    logger.error("[OpenRouterClient] %s", error_msg)
                    if self._is_non_retryable_request_error(response.status_code, error_text):
                        raise OpenRouterError(error_msg)
                    if idx < len(request_endpoints) - 1 and self._is_failover_status(response.status_code, error_text):
                        logger.warning(
                            "[OpenRouterClient] switching to fallback endpoint (%s -> %s)",
                            endpoint_name,
                            request_endpoints[idx + 1].get("name", "fallback"),
                        )
                        continue
                    if len(attempt_errors) > 1:
                        raise OpenRouterError(f"All LLM endpoints failed: {' | '.join(attempt_errors)}")
                    raise OpenRouterError(error_msg)

                try:
                    data = response.json()
                except Exception as exc:
                    raw_text = response.text[:2000]
                    error_msg = f"{endpoint_name} invalid JSON response: {exc}; raw={raw_text}"
                    attempt_errors.append(error_msg)
                    self._mark_provider_failure(str(provider), detail=error_msg)
                    logger.error("[OpenRouterClient] %s", error_msg)
                    if idx < len(request_endpoints) - 1:
                        logger.warning("[OpenRouterClient] switching to fallback endpoint after invalid JSON")
                        continue
                    if len(attempt_errors) > 1:
                        raise OpenRouterError(f"All LLM endpoints failed: {' | '.join(attempt_errors)}") from exc
                    raise OpenRouterError(error_msg) from exc

                if not self._extract_text_from_response(data):
                    error_msg = f"{endpoint_name} empty content response"
                    attempt_errors.append(error_msg)
                    logger.warning("[OpenRouterClient] %s", error_msg)
                    if allow_stream_fallback and self._is_aiberm_like_base(api_base):
                        stream_data, stream_error = await self._retry_provider_via_stream(
                            client=client,
                            api_base=api_base,
                            api_key=api_key,
                            endpoint_name=endpoint_name,
                            payload=effective_payload,
                        )
                        if stream_data is not None:
                            self._mark_provider_success(str(provider))
                            logger.info(
                                "[OpenRouterClient] stream fallback succeeded on %s",
                                endpoint_name,
                            )
                            return stream_data
                        if stream_error:
                            attempt_errors.append(stream_error)
                            logger.warning("[OpenRouterClient] %s", stream_error)
                    self._mark_provider_failure(str(provider), detail=error_msg)
                    if idx < len(request_endpoints) - 1:
                        logger.warning(
                            "[OpenRouterClient] switching to fallback endpoint (%s -> %s) after empty content",
                            endpoint_name,
                            request_endpoints[idx + 1].get("name", "fallback"),
                        )
                        continue
                    if len(attempt_errors) > 1:
                        raise OpenRouterError(f"All LLM endpoints failed: {' | '.join(attempt_errors)}")
                    raise OpenRouterError(error_msg)

                self._mark_provider_success(str(provider))
                return data

        raise OpenRouterError(f"All LLM endpoints failed: {' | '.join(attempt_errors)}")

    async def chat_completions(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 512,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        request_payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            request_payload["response_format"] = response_format

        logger.info(
            "[OpenRouterClient] Model=%s Temperature=%s MaxTokens=%s",
            model,
            temperature,
            max_tokens,
        )
        data = await self._post_chat_json(request_payload)

        try:
            response_str = json.dumps(data, ensure_ascii=False, indent=2)
            logger.info("[OpenRouterClient] Full response data: %s", response_str[:2000])
        except Exception:
            logger.warning("[OpenRouterClient] Failed to serialize response for logging")

        try:
            choice = (data.get("choices") or [None])[0] or {}
            logger.info(
                "[OpenRouterClient] Parsed choice keys: %s",
                list(choice.keys()) if isinstance(choice, dict) else "not a dict",
            )

            msg = choice.get("message") or {}
            refusal = msg.get("refusal")
            if refusal:
                logger.warning("[OpenRouterClient] Model refused to generate content: %s", refusal)

            content = self._extract_text_from_response(data)
            if content:
                logger.info("[OpenRouterClient] Returning extracted content (len=%s)", len(content))
                return content

            logger.warning("[OpenRouterClient] No valid content found in response")
            logger.warning(
                "[OpenRouterClient] data.keys=%s",
                list(data.keys()) if isinstance(data, dict) else "not a dict",
            )

            if refusal:
                raise OpenRouterError(f"Model refused the request: {refusal}")

            if choice.get("finish_reason") == "length":
                logger.warning("[OpenRouterClient] Response was truncated (finish_reason=length)")
            raise OpenRouterError("LLM returned empty content")
        except OpenRouterError:
            raise
        except Exception as exc:
            logger.error("[OpenRouterClient] Exception while parsing response: %s", exc)
            logger.error(
                "[OpenRouterClient] Full response data: %s",
                json.dumps(data, ensure_ascii=False, default=str)[:2000],
            )
            raise OpenRouterError(f"invalid response: {data}") from exc

    async def chat(
        self,
        *,
        model: str,
        system: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        msgs = list(messages or [])
        if system:
            msgs = [{"role": "system", "content": system}] + msgs
        request_payload: Dict[str, Any] = {"model": model, "messages": msgs}
        if temperature is not None:
            request_payload["temperature"] = float(temperature)
        if max_tokens is not None:
            request_payload["max_tokens"] = int(max_tokens)
        if response_format:
            request_payload["response_format"] = response_format
        return await self._post_chat_json(request_payload)

    async def preflight_chat(
        self,
        *,
        model: str,
        prompt: str,
        timeout_seconds: float = 18.0,
    ) -> str:
        timeout_cap = max(6.0, min(float(timeout_seconds or 18.0), 45.0))
        req_payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Health probe. Reply with exactly OK."},
                {"role": "user", "content": str(prompt or "").strip()[:220]},
            ],
            "temperature": 0.0,
            "max_tokens": 12,
        }
        data = await self._post_chat_json(
            req_payload,
            transport_max_attempts=1,
            timeout_overrides={
                "connect": min(8.0, timeout_cap),
                "read": timeout_cap,
                "write": min(8.0, timeout_cap),
                "pool": min(8.0, timeout_cap),
            },
            allow_stream_fallback=False,
        )
        content = self._extract_text_from_response(data)
        if not content:
            raise OpenRouterError("preflight_empty_content")
        return content

    def pick_content(self, resp: Dict[str, Any]) -> Optional[str]:
        try:
            content = self._extract_text_from_response(resp)
            return content or None
        except Exception:
            return None
