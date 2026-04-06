"""Canonical scene rulebook for PPT writing guidance and audit integration."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

_SUPPORTED_SCENE_PROFILES = {"status_report", "investor_pitch", "training_deck"}
_WEIGHT_ORDER = (("must", "Must", 2), ("key", "Key", 2), ("bonus", "Bonus", 1))


def _rulebook_path() -> Path:
    return Path(__file__).resolve().parent / "configs" / "ppt_scene_rulebook.json"


def normalize_scene_rule_profile(value: Any) -> str:
    key = str(value or "").strip().lower()
    return key if key in _SUPPORTED_SCENE_PROFILES else ""


@lru_cache(maxsize=1)
def get_scene_rulebook() -> Dict[str, Any]:
    path = _rulebook_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def scene_rule(profile: Any) -> Dict[str, Any]:
    normalized = normalize_scene_rule_profile(profile)
    catalog = get_scene_rulebook()
    value = catalog.get(normalized)
    return value if isinstance(value, dict) else {}


def scene_prompt_directives(profile: Any, *, slide_type: str = "") -> List[str]:
    rule = scene_rule(profile)
    if not rule:
        return []
    prompt_guidance = rule.get("prompt_guidance") if isinstance(rule.get("prompt_guidance"), dict) else {}
    shared = prompt_guidance.get("shared") if isinstance(prompt_guidance.get("shared"), dict) else {}
    slide_bucket = prompt_guidance.get(str(slide_type or "").strip().lower())
    slide_bucket = slide_bucket if isinstance(slide_bucket, dict) else {}
    label = str(rule.get("label") or normalize_scene_rule_profile(profile) or "场景规则").strip()

    out: List[str] = []
    seen: set[str] = set()
    for key, weight_label, limit in _WEIGHT_ORDER:
        values: List[str] = []
        shared_values = shared.get(key) if isinstance(shared.get(key), list) else []
        slide_values = slide_bucket.get(key) if isinstance(slide_bucket.get(key), list) else []
        for item in [*shared_values, *slide_values]:
            text = str(item or "").strip()
            if not text:
                continue
            values.append(text)
        for text in values[:limit]:
            marker = f"[{label}|{weight_label}] {text}"
            if marker.lower() in seen:
                continue
            seen.add(marker.lower())
            out.append(marker)
    return out


def scene_hard_fail_rules(profile: Any) -> List[Dict[str, Any]]:
    rule = scene_rule(profile)
    rows = rule.get("hard_fail_rules") if isinstance(rule.get("hard_fail_rules"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def scene_advisory_rules(profile: Any) -> List[Dict[str, Any]]:
    rule = scene_rule(profile)
    rows = rule.get("advisory_rules") if isinstance(rule.get("advisory_rules"), list) else []
    return [row for row in rows if isinstance(row, dict)]
