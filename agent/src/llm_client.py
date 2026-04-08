"""LLM adapter used by PPT master service.

This module keeps a minimal API:
    - get_llm_client()
    - client.chat_completion(...)

It loads environment variables from the project `.env` files and delegates
requests to `OpenRouterClient`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from src.openrouter_client import OpenRouterClient, OpenRouterError

logger = logging.getLogger("llm_client")


def _load_project_env() -> None:
    """Load env vars from backend/frontend project files if present."""
    agent_root = Path(__file__).resolve().parents[1]
    repo_root = agent_root.parent

    # Backend env (primary)
    load_dotenv(agent_root / ".env", override=False)
    # Repo env (optional)
    load_dotenv(repo_root / ".env", override=False)
    # Frontend local env (secondary fallback)
    load_dotenv(repo_root / ".env.local", override=False)


def _resolve_model() -> str:
    for key in (
        "PPT_MASTER_LLM_MODEL",
        "PROMPT_LLM_MODEL",
        "CONTENT_LLM_MODEL",
        "AI_CHAT_MODEL",
    ):
        value = str(os.getenv(key, "")).strip()
        if value:
            return value
    return "openai/gpt-5-mini"


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class LLMClient:
    """Small wrapper around OpenRouter client with repo-level env defaults."""

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        default_max_tokens: Optional[int] = None,
    ) -> None:
        self.model = str(model or _resolve_model()).strip() or "openai/gpt-5-mini"
        self.default_max_tokens = int(
            default_max_tokens or _env_int("PPT_MASTER_LLM_MAX_TOKENS", 4096)
        )
        self._client = OpenRouterClient()

    async def chat_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return OpenAI-style payload: {'content': '<text>'}."""
        effective_max_tokens = int(max_tokens or self.default_max_tokens)
        try:
            content = await self._client.chat_completions(
                model=self.model,
                messages=messages,
                temperature=float(temperature),
                max_tokens=effective_max_tokens,
                response_format=response_format,
            )
        except OpenRouterError as exc:
            logger.error("LLM completion failed: %s", exc)
            raise RuntimeError(f"LLM completion failed: {exc}") from exc

        return {
            "content": content,
            "model": self.model,
            "max_tokens": effective_max_tokens,
        }


_client_singleton: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Return process-wide singleton client."""
    global _client_singleton
    if _client_singleton is None:
        _load_project_env()
        _client_singleton = LLMClient()
    return _client_singleton
