"""Shared palette normalization helpers backed by template catalog."""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.ppt_template_catalog import get_template_catalog


def _normalize_key(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())).strip("_")


def _catalog() -> dict[str, Any]:
    raw = get_template_catalog()
    return raw if isinstance(raw, dict) else {}


def _supported_set() -> set[str]:
    palettes = _catalog().get("palettes")
    if not isinstance(palettes, dict):
        return set()
    out: set[str] = set()
    for key in palettes.keys():
        normalized = _normalize_key(str(key or ""))
        if normalized:
            out.add(normalized)
    return out


def _alias_map() -> dict[str, str]:
    raw = _catalog().get("palette_aliases")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        source = _normalize_key(str(key or ""))
        target = _normalize_key(str(value or ""))
        if source and target:
            out[source] = target
    return out


def _default_palette() -> str:
    raw = _normalize_key(str(_catalog().get("default_palette_key") or ""))
    return raw or "business_authority"


def list_supported_palettes() -> list[str]:
    return sorted(_supported_set())


def suggest_palette_from_context(*parts: Iterable[str] | str) -> str:
    tokens: list[str] = []
    for part in parts:
        if isinstance(part, str):
            tokens.append(part)
            continue
        for item in part:
            tokens.append(str(item or ""))
    blob = " ".join(tokens).lower()
    palette_keywords = _catalog().get("palette_keywords")
    if isinstance(palette_keywords, dict):
        for pattern, palette in palette_keywords.items():
            if not pattern or not palette:
                continue
            try:
                if re.search(str(pattern), blob, flags=re.IGNORECASE):
                    normalized = _normalize_key(str(palette or ""))
                    if normalized:
                        return normalized
            except re.error:
                continue
    return _default_palette()


def canonicalize_palette_key(
    palette_key: str,
    *,
    context_text: str = "",
    fallback: str = "auto",
) -> str:
    normalized = _normalize_key(str(palette_key or ""))
    supported = _supported_set()
    aliases = _alias_map()
    default_palette = _default_palette()
    if normalized in {"", "auto"}:
        fallback_key = _normalize_key(fallback)
        if fallback_key in supported:
            return fallback_key
        return "auto"
    if normalized in supported:
        return normalized
    if normalized in aliases and aliases[normalized] in supported:
        return aliases[normalized]
    if context_text.strip():
        suggested = suggest_palette_from_context(context_text)
        if suggested in supported:
            return suggested
    fallback_key = _normalize_key(fallback)
    if fallback_key in supported:
        return fallback_key
    if default_palette in supported:
        return default_palette
    return "business_authority"
