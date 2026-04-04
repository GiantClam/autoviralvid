"""Shared visual identity helpers for PPT theme recipe, style, and tone."""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.ppt_template_catalog import get_template_catalog


_VALID_STYLES = {"sharp", "soft", "rounded", "pill"}
_THEME_RECIPE_ALIASES = {
    "classroom": "classroom_soft",
    "education": "classroom_soft",
    "consulting": "consulting_clean",
    "executive_brief": "consulting_clean",
    "premium_light": "consulting_clean",
    "editorial": "editorial_magazine",
    "magazine": "editorial_magazine",
    "tech": "tech_cinematic",
    "energetic": "energetic_campaign",
    "campaign": "energetic_campaign",
}
_THEME_RECIPE_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"education|classroom|teaching|training|lesson|school|curriculum|教学|课堂|教育|培训|课程", re.I), "classroom_soft"),
    (re.compile(r"editorial|magazine|story|feature|reportage|杂志|报道|专栏|故事", re.I), "editorial_magazine"),
    (re.compile(r"tech|ai|cloud|cyber|platform|科技|人工智能|云|数字化", re.I), "tech_cinematic"),
    (re.compile(r"campaign|marketing|brand|launch|活动|营销|品牌|发布", re.I), "energetic_campaign"),
]


def _normalize_key(value: Any) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())).strip("_")


def _catalog() -> dict[str, Any]:
    raw = get_template_catalog()
    return raw if isinstance(raw, dict) else {}


def _theme_recipes() -> dict[str, Any]:
    raw = _catalog().get("theme_recipes")
    return raw if isinstance(raw, dict) else {}


def default_theme_recipe() -> str:
    candidate = _normalize_key(_catalog().get("default_theme_recipe") or "consulting_clean")
    return candidate or "consulting_clean"


def normalize_tone(value: Any, fallback: str = "auto") -> str:
    normalized = _normalize_key(value)
    if normalized in {"light", "dark"}:
        return normalized
    normalized_fallback = _normalize_key(fallback)
    if normalized_fallback in {"light", "dark"}:
        return normalized_fallback
    return "auto"


def canonicalize_theme_recipe(value: Any, *, fallback: str = "auto") -> str:
    recipes = _theme_recipes()
    normalized = _normalize_key(value)
    if normalized in {"", "auto"}:
        fallback_key = _normalize_key(fallback)
        if fallback_key not in {"", "auto"}:
            return canonicalize_theme_recipe(fallback_key, fallback="consulting_clean")
        return "auto"
    if normalized in recipes:
        return normalized
    alias = _normalize_key(_THEME_RECIPE_ALIASES.get(normalized) or "")
    if alias in recipes:
        return alias
    fallback_key = _normalize_key(fallback)
    if fallback_key not in {"", "auto"}:
        return canonicalize_theme_recipe(fallback_key, fallback="consulting_clean")
    default_key = default_theme_recipe()
    return default_key if default_key in recipes else "consulting_clean"


def get_theme_recipe(value: Any, *, fallback: str = "consulting_clean") -> dict[str, Any]:
    recipes = _theme_recipes()
    key = canonicalize_theme_recipe(value, fallback=fallback)
    resolved = default_theme_recipe() if key == "auto" else key
    raw = recipes.get(resolved) if isinstance(recipes.get(resolved), dict) else {}
    return {
        "id": resolved,
        "style_variant": str(raw.get("style_variant") or "soft").strip().lower() or "soft",
        "backdrop": str(raw.get("backdrop") or "minimal-grid").strip().lower() or "minimal-grid",
        "tone": normalize_tone(raw.get("tone"), fallback="auto"),
        "surface_profile": str(raw.get("surface_profile") or "clean").strip().lower() or "clean",
    }


def resolve_style_variant(style_variant: Any, *, theme_recipe: Any = "auto", fallback: str = "soft") -> str:
    explicit = _normalize_key(style_variant)
    if explicit in _VALID_STYLES:
        return explicit
    recipe = get_theme_recipe(theme_recipe)
    recipe_style = _normalize_key(recipe.get("style_variant") or "")
    if recipe_style in _VALID_STYLES:
        return recipe_style
    normalized_fallback = _normalize_key(fallback)
    if normalized_fallback in _VALID_STYLES:
        return normalized_fallback
    return "soft"


def style_variant_for_theme_recipe(theme_recipe: Any, *, fallback: str = "soft") -> str:
    recipe = get_theme_recipe(theme_recipe)
    recipe_style = _normalize_key(recipe.get("style_variant") or "")
    if recipe_style in _VALID_STYLES:
        return recipe_style
    normalized_fallback = _normalize_key(fallback)
    if normalized_fallback in _VALID_STYLES:
        return normalized_fallback
    return "soft"


def resolve_tone(value: Any, *, theme_recipe: Any = "auto", fallback: str = "auto") -> str:
    explicit = normalize_tone(value, fallback="auto")
    if explicit in {"light", "dark"}:
        return explicit
    recipe = get_theme_recipe(theme_recipe)
    recipe_tone = normalize_tone(recipe.get("tone"), fallback="auto")
    if recipe_tone in {"light", "dark"}:
        return recipe_tone
    return normalize_tone(fallback, fallback="auto")


def suggest_theme_recipe_from_context(*parts: Iterable[str] | str) -> str:
    tokens: list[str] = []
    for part in parts:
        if isinstance(part, str):
            tokens.append(part)
            continue
        for item in part:
            tokens.append(str(item or ""))
    blob = " ".join(tokens).strip()
    for pattern, recipe in _THEME_RECIPE_HINTS:
        if pattern.search(blob):
            return canonicalize_theme_recipe(recipe, fallback=default_theme_recipe())
    return canonicalize_theme_recipe(default_theme_recipe(), fallback="consulting_clean")
