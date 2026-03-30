import json
import logging
import os
from typing import Any, Dict, List, Optional

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

        # 代理支持：优先使用 OPENROUTER_PROXY，其次 HTTP_PROXY/HTTPS_PROXY
        proxy = os.getenv("OPENROUTER_PROXY")
        http_proxy = os.getenv("OPENROUTER_HTTP_PROXY") or os.getenv("HTTP_PROXY")
        https_proxy = os.getenv("OPENROUTER_HTTPS_PROXY") or os.getenv("HTTPS_PROXY")
        self.proxy: Optional[str] = proxy or https_proxy or http_proxy

        self._endpoints = self._build_endpoints(api_base=api_base, api_key=api_key)
        self.api_base = self._endpoints[0]["base"]
        self.api_key = self._endpoints[0]["key"]

    def _build_endpoints(self, *, api_base: Optional[str], api_key: Optional[str]) -> List[Dict[str, str]]:
        fallback_openrouter_base = self._normalize_base(
            os.getenv("OPENROUTER_FALLBACK_API_BASE") or _DEFAULT_OPENROUTER_BASE
        )
        primary_base = self._normalize_base(
            api_base
            or os.getenv("AIBERM_API_BASE")
            or os.getenv("OPENROUTER_API_BASE")
            or os.getenv("OPENROUTER_BASE_URL")
            or fallback_openrouter_base
        )

        openrouter_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY")
        aiberm_key = os.getenv("AIBERM_API_KEY")
        if api_key:
            primary_key = api_key
        elif "aiberm" in primary_base.lower():
            primary_key = aiberm_key or openrouter_key
        else:
            primary_key = openrouter_key or aiberm_key

        if not primary_key:
            raise OpenRouterError("缺少 OPENROUTER_API_KEY（或兼容的 LLM_API_KEY/AIBERM_API_KEY）")

        fallback_base = self._normalize_base(
            os.getenv("OPENROUTER_FALLBACK_API_BASE") or _DEFAULT_OPENROUTER_BASE
        )
        fallback_key = os.getenv("OPENROUTER_FALLBACK_API_KEY") or openrouter_key or primary_key

        endpoints: List[Dict[str, str]] = [{"name": "primary", "base": primary_base, "key": primary_key}]
        if fallback_key and fallback_base and fallback_base != primary_base:
            endpoints.append({"name": "openrouter_fallback", "base": fallback_base, "key": fallback_key})
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
                    return response.json()
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
            content = msg.get("content")

            refusal = msg.get("refusal")
            if refusal:
                logger.warning("[OpenRouterClient] Model refused to generate content: %s", refusal)

            logger.info(
                "[OpenRouterClient] Content type: %s, value preview: %s",
                type(content),
                str(content)[:200] if content else "None",
            )

            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if isinstance(p, dict)]
                content = "".join(text_parts).strip()
                logger.debug("[OpenRouterClient] Content from list: %s", content[:200])

            if isinstance(content, str) and content.strip():
                logger.info("[OpenRouterClient] Returning content (len=%s)", len(content))
                return content.strip()

            reasoning = msg.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                logger.info("[OpenRouterClient] Found content in reasoning field (len=%s)", len(reasoning))
                return reasoning.strip()

            reasoning_details = msg.get("reasoning_details")
            if isinstance(reasoning_details, list) and len(reasoning_details) > 0:
                for detail in reasoning_details:
                    if isinstance(detail, dict):
                        if detail.get("type") == "reasoning.encrypted":
                            logger.warning(
                                "[OpenRouterClient] Found encrypted reasoning, cannot extract content directly"
                            )
                        elif detail.get("text"):
                            text = detail.get("text")
                            if isinstance(text, str) and text.strip():
                                logger.info(
                                    "[OpenRouterClient] Found content in reasoning_details (len=%s)",
                                    len(text),
                                )
                                return text.strip()

            text_field = choice.get("text")
            if isinstance(text_field, str) and text_field.strip():
                logger.info("[OpenRouterClient] Returning text field (len=%s)", len(text_field))
                return text_field.strip()

            output_text = data.get("output_text")
            if isinstance(output_text, str) and output_text.strip():
                logger.info("[OpenRouterClient] Returning output_text (len=%s)", len(output_text))
                return output_text.strip()

            logger.warning("[OpenRouterClient] No valid content found in response")
            logger.warning(
                "[OpenRouterClient] data.keys=%s",
                list(data.keys()) if isinstance(data, dict) else "not a dict",
            )

            if refusal:
                raise OpenRouterError(f"模型拒绝生成内容: {refusal}")

            if choice.get("finish_reason") == "length":
                logger.warning("[OpenRouterClient] Response was truncated (finish_reason=length)")
            return ""
        except OpenRouterError:
            raise
        except Exception as exc:
            logger.error("[OpenRouterClient] Exception while parsing response: %s", exc)
            logger.error(
                "[OpenRouterClient] Full response data: %s",
                json.dumps(data, ensure_ascii=False, default=str)[:2000],
            )
            raise OpenRouterError(f"无效响应：{data}") from exc

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
            choices = resp.get("choices") or []
            msg = (choices[0] or {}).get("message", {}) if choices else {}
            content = msg.get("content")
            if isinstance(content, list):
                return "".join([str(x.get("text") or "") for x in content])
            return content
        except Exception:
            return None


