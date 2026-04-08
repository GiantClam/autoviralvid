import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_DEFAULT_OPENROUTER_FALLBACK_MODEL = os.getenv(
    "CONTENT_LLM_MODEL",
    "meta-llama/llama-3.3-70b-instruct",
)
_FAILOVER_STATUS_CODES = {401, 403, 404, 408, 409, 425, 429, 500, 502, 503, 504}


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        referer: Optional[str] = None,
        title: str = "SaleAgent",
    ) -> None:
        self.referer = referer or os.getenv("EMBEDDING_REFERER") or os.getenv("SITE_URL") or "https://saleagent.app"
        self.title = title

        # 娴狅絿鎮婇弨顖涘瘮閿涙矮绱崗鍫滃▏閻?OPENROUTER_PROXY閿涘苯鍙惧▎?HTTP_PROXY/HTTPS_PROXY
        proxy = os.getenv("OPENROUTER_PROXY")
        http_proxy = os.getenv("OPENROUTER_HTTP_PROXY") or os.getenv("HTTP_PROXY")
        https_proxy = os.getenv("OPENROUTER_HTTPS_PROXY") or os.getenv("HTTPS_PROXY")
        self.proxy: Optional[str] = proxy or https_proxy or http_proxy

        self._endpoints = self._build_endpoints(api_base=api_base, api_key=api_key)
        self.api_base = self._endpoints[0]["base"]
        self.api_key = self._endpoints[0]["key"]

    def _build_endpoints(self, *, api_base: Optional[str], api_key: Optional[str]) -> List[Dict[str, str]]:
        openrouter_base = self._normalize_base(
            os.getenv("OPENROUTER_API_BASE")
            or os.getenv("OPENROUTER_BASE_URL")
            or _DEFAULT_OPENROUTER_BASE
        )
        aiberm_base = self._normalize_base(os.getenv("AIBERM_API_BASE"))
        primary_base = self._normalize_base(
            api_base
            or os.getenv("AIBERM_API_BASE")
            or os.getenv("OPENROUTER_API_BASE")
            or os.getenv("OPENROUTER_BASE_URL")
            or _DEFAULT_OPENROUTER_BASE
        )
        openrouter_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY")
        aiberm_key = os.getenv("AIBERM_API_KEY")
        def _pick_key_for_base(base: str) -> Optional[str]:
            lowered = str(base or "").lower()
            if "aiberm" in lowered:
                return aiberm_key or openrouter_key
            if "openrouter.ai" in lowered:
                return openrouter_key or aiberm_key
            return openrouter_key or aiberm_key
        primary_key = api_key or _pick_key_for_base(primary_base)
        if not primary_key:
            raise OpenRouterError("missing OPENROUTER_API_KEY/LLM_API_KEY or AIBERM_API_KEY")
        explicit_fallback_base = self._normalize_base(os.getenv("OPENROUTER_FALLBACK_API_BASE"))
        fallback_base = ""
        if explicit_fallback_base and explicit_fallback_base != primary_base:
            fallback_base = explicit_fallback_base
        else:
            if "aiberm" in primary_base.lower():
                fallback_base = openrouter_base
            elif "openrouter.ai" in primary_base.lower():
                fallback_base = aiberm_base or openrouter_base
            elif aiberm_base and primary_base != aiberm_base:
                fallback_base = aiberm_base
            else:
                fallback_base = openrouter_base
        fallback_key = (
            os.getenv("OPENROUTER_FALLBACK_API_KEY")
            or _pick_key_for_base(fallback_base)
            or primary_key
        )
        endpoints: List[Dict[str, str]] = [{"name": "primary", "base": primary_base, "key": primary_key}]
        if fallback_key and fallback_base and fallback_base != primary_base:
            endpoints.append({"name": "provider_fallback", "base": fallback_base, "key": fallback_key})
        return endpoints
    def _headers(self, *, api_base: str, api_key: str) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter.ai" in api_base:
            headers["HTTP-Referer"] = self.referer
            headers["X-Title"] = self.title
        return headers

    @staticmethod
    def _normalize_base(raw: str) -> str:
        return str(raw or "").strip().rstrip("/")

    @staticmethod
    def _is_aiberm_base(api_base: str) -> bool:
        lowered = str(api_base or "").lower()
        return "aiberm" in lowered

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

    async def _retry_aiberm_via_stream(
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
            return None, f"{endpoint_name} stream fallback transport error: {exc}"

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
        model = str(requested_model or "").strip()
        if not model:
            return model
        author = model.split("/", 1)[0].strip().lower()
        banned_on_current_key = {"openai", "google", "anthropic"}
        if author not in banned_on_current_key:
            return model
        if "openrouter.ai" not in str(api_base or "").lower() and endpoint_name != "openrouter_fallback":
            return model
        fallback_model = str(_DEFAULT_OPENROUTER_FALLBACK_MODEL).strip()
        if not fallback_model:
            return model
        if fallback_model != model:
            logger.warning(
                "[OpenRouterClient] swap model for %s: %s -> %s",
                endpoint_name,
                model,
                fallback_model,
            )
        return fallback_model

    async def _post_chat_json(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        attempt_errors: List[str] = []
        async with httpx.AsyncClient(timeout=60, proxy=self.proxy) as client:
            for idx, endpoint in enumerate(self._endpoints):
                api_base = endpoint["base"]
                api_key = endpoint["key"]
                endpoint_name = endpoint.get("name") or f"endpoint-{idx + 1}"
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

                try:
                    response = await client.post(
                        f"{api_base}/chat/completions",
                        headers=self._headers(api_base=api_base, api_key=api_key),
                        json=effective_payload,
                    )
                except Exception as exc:
                    error_msg = f"{endpoint_name} transport error: {exc}"
                    attempt_errors.append(error_msg)
                    logger.warning("[OpenRouterClient] %s", error_msg)
                    if self._is_aiberm_base(api_base):
                        stream_data, stream_error = await self._retry_aiberm_via_stream(
                            client=client,
                            api_base=api_base,
                            api_key=api_key,
                            endpoint_name=endpoint_name,
                            payload=effective_payload,
                        )
                        if stream_data is not None:
                            logger.info(
                                "[OpenRouterClient] stream fallback succeeded on %s after transport error",
                                endpoint_name,
                            )
                            return stream_data
                        if stream_error:
                            attempt_errors.append(stream_error)
                            logger.warning("[OpenRouterClient] %s", stream_error)
                    if idx < len(self._endpoints) - 1:
                        logger.warning("[OpenRouterClient] switching to fallback endpoint after transport error")
                        continue
                    if len(attempt_errors) > 1:
                        raise OpenRouterError(
                            f"All LLM endpoints failed: {' | '.join(attempt_errors)}"
                        ) from exc
                    raise OpenRouterError(f"LLM request failed: {error_msg}") from exc

                logger.info("[OpenRouterClient] Response status(%s): %s", endpoint_name, response.status_code)
                if response.status_code != 200:
                    error_text = response.text[:1000]
                    error_msg = f"{endpoint_name} HTTP {response.status_code}: {error_text}"
                    attempt_errors.append(error_msg)
                    logger.error("[OpenRouterClient] %s", error_msg)
                    if idx < len(self._endpoints) - 1 and self._is_failover_status(response.status_code, error_text):
                        logger.warning(
                            "[OpenRouterClient] switching to fallback endpoint (%s -> %s)",
                            endpoint_name,
                            self._endpoints[idx + 1].get("name", "fallback"),
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
                    logger.error("[OpenRouterClient] %s", error_msg)
                    if idx < len(self._endpoints) - 1:
                        logger.warning("[OpenRouterClient] switching to fallback endpoint after invalid JSON")
                        continue
                    if len(attempt_errors) > 1:
                        raise OpenRouterError(f"All LLM endpoints failed: {' | '.join(attempt_errors)}") from exc
                    raise OpenRouterError(error_msg) from exc

                if not self._extract_text_from_response(data):
                    error_msg = f"{endpoint_name} empty content response"
                    attempt_errors.append(error_msg)
                    logger.warning("[OpenRouterClient] %s", error_msg)
                    if self._is_aiberm_base(api_base):
                        stream_data, stream_error = await self._retry_aiberm_via_stream(
                            client=client,
                            api_base=api_base,
                            api_key=api_key,
                            endpoint_name=endpoint_name,
                            payload=effective_payload,
                        )
                        if stream_data is not None:
                            logger.info(
                                "[OpenRouterClient] stream fallback succeeded on %s",
                                endpoint_name,
                            )
                            return stream_data
                        if stream_error:
                            attempt_errors.append(stream_error)
                            logger.warning("[OpenRouterClient] %s", stream_error)
                    if idx < len(self._endpoints) - 1:
                        logger.warning(
                            "[OpenRouterClient] switching to fallback endpoint (%s -> %s) after empty content",
                            endpoint_name,
                            self._endpoints[idx + 1].get("name", "fallback"),
                        )
                        continue
                    if len(attempt_errors) > 1:
                        raise OpenRouterError(f"All LLM endpoints failed: {' | '.join(attempt_errors)}")
                    raise OpenRouterError(error_msg)

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

    def pick_content(self, resp: Dict[str, Any]) -> Optional[str]:
        try:
            content = self._extract_text_from_response(resp)
            return content or None
        except Exception:
            return None


