"""Installed skill executor for PPT planning/runtime patches.

The executor is called by ``src.ppt_subagent_executor`` (stdin/stdout JSON),
but it is also used directly by ``src.ppt_service`` in the main export path.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from src.ppt_master_skill_adapter import execute_ppt_master_skill
from src.ppt_scene_rulebook import (
    normalize_scene_rule_profile as normalize_scene_rule_profile,
    scene_prompt_directives,
)
from src.ppt_template_catalog import (
    default_template_for_layout as catalog_default_template_for_layout,
    list_template_ids as catalog_list_template_ids,
    resolve_template_for_slide as catalog_resolve_template_for_slide,
    template_capabilities as catalog_template_capabilities,
    template_profiles as catalog_template_profiles,
)
from src.ppt_visual_identity import (
    canonicalize_theme_recipe,
    resolve_style_variant,
    resolve_tone,
    suggest_theme_recipe_from_context,
)

_DEFAULT_LAYOUT_BY_SLIDE_TYPE: Dict[str, str] = {
    "cover": "hero_1",
    "toc": "hero_1",
    "divider": "hero_1",
    "section": "hero_1",
    "summary": "hero_1",
    "content": "split_2",
    "comparison": "split_2",
    "timeline": "timeline",
    "workflow": "timeline",
}

_AGENT_BY_SLIDE_TYPE: Dict[str, str] = {
    "cover": "cover-page-generator",
    "toc": "table-of-contents-generator",
    "divider": "section-divider-generator",
    "section": "section-divider-generator",
    "summary": "summary-page-generator",
    "content": "content-page-generator",
}

_PALETTE_HINTS: List[tuple[str, str]] = [
    ("finance", "business_authority"),
    ("investor", "business_authority"),
    ("fundraising", "business_authority"),
    ("marketing", "energetic"),
    ("brand", "energetic"),
    ("education", "education_charts"),
    ("training", "education_charts"),
    ("health", "modern_wellness"),
    ("medical", "modern_wellness"),
    ("retail", "vibrant_orange_mint"),
    ("sustain", "forest_eco"),
    ("green", "forest_eco"),
    ("architecture", "pure_tech_blue"),
    ("cloud", "pure_tech_blue"),
    ("ai", "pure_tech_blue"),
    ("tech", "pure_tech_blue"),
    ("科技", "pure_tech_blue"),
    ("架构", "pure_tech_blue"),
    ("流程", "education_charts"),
    ("培训", "education_charts"),
    ("教育", "education_charts"),
    ("医疗", "modern_wellness"),
    ("品牌", "energetic"),
    ("营销", "energetic"),
    ("融资", "business_authority"),
]

_STYLE_HINTS: List[tuple[str, str]] = [
    ("architecture", "sharp"),
    ("cloud", "sharp"),
    ("workflow", "sharp"),
    ("system", "sharp"),
    ("enterprise", "sharp"),
    ("tech", "sharp"),
    ("premium", "pill"),
    ("luxury", "pill"),
    ("brand", "rounded"),
    ("creative", "rounded"),
    ("training", "soft"),
    ("education", "soft"),
    ("consulting", "soft"),
    ("架构", "sharp"),
    ("系统", "sharp"),
    ("流程", "sharp"),
    ("品牌", "rounded"),
    ("教育", "soft"),
]

_SECTION_HINT_RE = re.compile(
    r"(section|chapter|part|agenda|toc|directory|phase)\b",
    flags=re.IGNORECASE,
)
_TIMELINE_HINT_RE = re.compile(
    r"(timeline|roadmap|workflow|process|journey|funnel|milestone)",
    flags=re.IGNORECASE,
)
_COMPARE_HINT_RE = re.compile(
    r"(compare|versus|vs\.?|before|after|benchmark)",
    flags=re.IGNORECASE,
)

_SOURCES = [
    "minimax:skills/pptx-generator",
    "minimax:plugins/pptx-plugin",
    "anthropic:skills/pptx",
    "ppt-master",
]

_GENERIC_COVER_TEMPLATE_OVERRIDES = {
    "",
    "auto",
    "dashboard_dark",
    "bento_2x2_dark",
    "bento_mosaic_dark",
    "split_media_dark",
}
_CONTENT_LAYOUT_ROTATION: List[str] = ["split_2", "grid_3", "grid_4", "asymmetric_2", "timeline"]
_CONTENT_LAYOUT_SET = set(_CONTENT_LAYOUT_ROTATION)
_CONTENT_LAYOUT_MAX_RATIO = 0.5
_CONTENT_LAYOUT_MAX_SPLIT_RATIO = 0.34
_CONTENT_TEMPLATE_MAX_RATIO = 0.5
_CONTENT_TEMPLATE_MAX_DASHBOARD_RATIO = 0.34

# Phase-3: field ownership policy for skill patch writes.
_SKILL_WRITE_POLICY: Dict[str, set[str]] = {
    "slide_type": {"ppt-orchestra-skill", "slide-making-skill", "ppt-master"},
    "layout_grid": {"ppt-orchestra-skill", "slide-making-skill", "ppt-master"},
    "render_path": {"ppt-orchestra-skill", "slide-making-skill", "pptx", "ppt-master"},
    "agent_type": {"ppt-orchestra-skill", "slide-making-skill", "ppt-master"},
    "style_variant": {"design-style-skill", "ppt-master"},
    "theme_recipe": {"design-style-skill", "ppt-master"},
    "tone": {"design-style-skill", "ppt-master"},
    "template_family": {"design-style-skill", "ppt-editing-skill", "ppt-master"},
    "skill_profile": {"design-style-skill", "ppt-editing-skill", "ppt-master"},
    "palette_key": {"color-font-skill", "ppt-master"},
    "title": {"content-strategy-skill", "ppt-master"},
    "chart_type": {"slide-making-skill", "ppt-master"},
    "chart_data": {"slide-making-skill", "ppt-master"},
    "xml_patch": {"ppt-editing-skill"},
}
_SKILL_WRITE_CONFLICT_KEYS = set(_SKILL_WRITE_POLICY.keys())
_PRIMARY_VISUAL_FIELDS = {"layout_grid", "template_family", "render_path"}


def _primary_visual_skill_names() -> set[str]:
    default_names: set[str] = set()
    for field in _PRIMARY_VISUAL_FIELDS:
        for owner in _SKILL_WRITE_POLICY.get(field, set()):
            skill = _normalize_skill_key(owner)
            if skill:
                default_names.add(skill)
    if not default_names:
        default_names = {"ppt-orchestra-skill", "ppt-master"}
    default_raw = ",".join(sorted(default_names))
    raw = _normalize_text(
        os.getenv("PPT_PRIMARY_VISUAL_SKILL", default_raw),
        default_raw,
    )
    names: set[str] = set()
    for item in raw.split(","):
        skill = _normalize_skill_key(item)
        if skill:
            names.add(skill)
    if not names:
        names.add("ppt-orchestra-skill")
    return names


def _normalize_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _normalize_skill_key(value: Any) -> str:
    text = _normalize_text(value, "").lower()
    text = "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def _dedupe_skills(raw_value: Any) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in _as_list(raw_value):
        skill = _normalize_skill_key(item)
        if not skill or skill in seen:
            continue
        seen.add(skill)
        out.append(skill)
    return out


def _dedupe_text_list(raw_values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in raw_values:
        text = _normalize_text(item, "")
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _env_flag(name: str, default: str = "false") -> bool:
    text = _normalize_text(os.getenv(name, default), default).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _as_bool(value: Any, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _normalize_execution_profile(value: Any) -> str:
    text = _normalize_text(value, "").strip().lower().replace("-", "_")
    if text in {"dev", "strict", "dev_strict"}:
        return "dev_strict"
    if text in {"prod", "safe", "prod_safe"}:
        return "prod_safe"
    return ""


def _resolve_scene_rule_profile(slide: Dict[str, Any], deck: Dict[str, Any], request: Dict[str, Any]) -> str:
    return (
        normalize_scene_rule_profile(request.get("quality_profile"))
        or normalize_scene_rule_profile(slide.get("quality_profile"))
        or normalize_scene_rule_profile(deck.get("quality_profile"))
        or ""
    )


def _parse_command_args(raw_value: str) -> List[str]:
    text = _normalize_text(raw_value, "")
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [_normalize_text(item, "") for item in parsed if _normalize_text(item, "")]
    except Exception:
        pass
    try:
        return [item for item in shlex.split(text, posix=False) if _normalize_text(item, "")]
    except Exception:
        return [item for item in text.split() if _normalize_text(item, "")]


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    text = _normalize_text(raw_text, "")
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    for line in reversed(text.splitlines()):
        row = line.strip()
        if not row.startswith("{"):
            continue
        try:
            parsed = json.loads(row)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _resolve_runtime_bin(bin_name: str, cwd: str) -> str:
    normalized = _normalize_text(bin_name, "")
    lower = normalized.lower()
    if lower not in {"python", "python3"}:
        return normalized
    base = Path(cwd or ".")
    candidates: List[Path] = []
    if os.name == "nt":
        candidates.extend(
            [
                base / ".venv" / "Scripts" / "python.exe",
                base / "venv" / "Scripts" / "python.exe",
            ]
        )
    else:
        candidates.extend(
            [
                base / ".venv" / "bin" / "python",
                base / "venv" / "bin" / "python",
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return normalized


def _compact_error_detail(raw_text: Any, *, max_chars: int = 420, tail_chars: int = 260) -> str:
    text = _normalize_text(raw_text, "")
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    keep_tail = max(80, min(tail_chars, max_chars - 40))
    keep_head = max(40, max_chars - keep_tail - 5)
    return f"{text[:keep_head]} ... {text[-keep_tail:]}"


def _stable_json_signature(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(value)


def _append_note(existing: Any, updates: List[str]) -> str:
    values = _dedupe_text_list(
        [
            _normalize_text(existing, ""),
            *[_normalize_text(item, "") for item in updates],
        ]
    )
    return "; ".join([item for item in values if item])


def _govern_patch_for_skill(
    *,
    skill: str,
    patch: Dict[str, Any],
    seen_writes: Dict[str, Dict[str, Any]],
    violations: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
    strict_primary_writer: bool = False,
    primary_visual_skills: set[str] | None = None,
) -> tuple[Dict[str, Any], List[str], bool]:
    skill_key = _normalize_skill_key(skill)
    sanitized: Dict[str, Any] = {}
    notes: List[str] = []
    has_violation = False

    for raw_key, raw_value in patch.items():
        key = _normalize_text(raw_key, "")
        if not key:
            continue

        if strict_primary_writer and key in _PRIMARY_VISUAL_FIELDS:
            owners = {item for item in (primary_visual_skills or set()) if item}
            if owners and skill_key not in owners:
                violations.append(
                    {
                        "skill": skill_key or "unknown",
                        "field": key,
                        "reason": "primary_visual_writer_only",
                        "allowed_skills": sorted(owners),
                    }
                )
                notes.append(f"skill_write_policy_violation:{key}")
                has_violation = True
                continue

        owners = _SKILL_WRITE_POLICY.get(key)
        if owners is not None and skill_key not in owners:
            violations.append(
                {
                    "skill": skill_key or "unknown",
                    "field": key,
                    "reason": "unauthorized_write",
                    "allowed_skills": sorted(owners),
                }
            )
            notes.append(f"skill_write_policy_violation:{key}")
            has_violation = True
            continue

        signature = _stable_json_signature(raw_value)
        prior = seen_writes.get(key)
        if (
            prior
            and key in _SKILL_WRITE_CONFLICT_KEYS
            and prior.get("signature") != signature
            and prior.get("skill") != skill_key
        ):
            conflicts.append(
                {
                    "field": key,
                    "first_skill": str(prior.get("skill") or ""),
                    "second_skill": skill_key or "unknown",
                    "first_value": prior.get("value"),
                    "second_value": raw_value,
                }
            )
            notes.append(f"skill_write_conflict_dropped:{key}")
            # Deterministic single-writer rule: keep first writer, drop later writes.
            continue

        if key not in seen_writes:
            seen_writes[key] = {
                "skill": skill_key or "unknown",
                "signature": signature,
                "value": raw_value,
            }
        sanitized[key] = raw_value

    return sanitized, notes, has_violation


def _invoke_direct_skill_runtime(
    *,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    requested_skills: List[str],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    if not _env_flag("PPT_DIRECT_SKILL_RUNTIME_ENABLED", "true"):
        return {"enabled": False, "reason": "direct_skill_runtime_disabled", "row": {}}

    bin_name = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_BIN", ""), "uv")

    args = _parse_command_args(os.getenv("PPT_DIRECT_SKILL_RUNTIME_ARGS", ""))
    if not args:
        args = ["run", "python", "-m", "src.ppt_direct_skill_runtime"]
    timeout_sec_raw = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_TIMEOUT_SEC", "25"), "25")
    try:
        timeout_sec = max(5, int(timeout_sec_raw))
    except Exception:
        timeout_sec = 25
    cwd = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_CWD", ""), "")
    if not cwd:
        cwd = str(Path(__file__).resolve().parents[1])
    resolved_bin_name = _resolve_runtime_bin(bin_name, cwd)
    payload = {
        "version": 1,
        "requested_skills": requested_skills,
        "slide": slide,
        "deck": deck,
        "state": state,
        "sources": list(_SOURCES),
    }

    try:
        proc = subprocess.run(
            [resolved_bin_name, *args],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_sec,
            check=False,
            cwd=cwd,
        )
    except Exception as exc:
        return {
            "enabled": True,
            "reason": f"direct_skill_runtime_failed:{_normalize_text(str(exc), 'invoke_failed')}",
            "parsed": {},
        }

    if int(proc.returncode) != 0:
        detail = _normalize_text(proc.stderr, "") or _normalize_text(proc.stdout, "") or f"exit_{proc.returncode}"
        compact_detail = _compact_error_detail(detail)
        return {
            "enabled": True,
            "reason": f"direct_skill_runtime_nonzero:exit_{proc.returncode}:{compact_detail}",
            "parsed": {},
        }

    parsed = _parse_json_object(_normalize_text(proc.stdout, ""))
    if not parsed:
        return {"enabled": True, "reason": "direct_skill_runtime_invalid_output", "parsed": {}}
    return {"enabled": True, "reason": "", "parsed": parsed}


def _normalize_runtime_row(raw_row: Dict[str, Any], default_skill: str = "") -> Dict[str, Any]:
    row = _as_dict(raw_row)
    skill = _normalize_skill_key(row.get("skill") or default_skill)
    patch = _as_dict(row.get("patch") or row.get("slide_patch"))
    outputs = _as_dict(row.get("outputs") or row.get("context"))
    status = _normalize_text(row.get("status"), "").lower()
    if status not in {"applied", "noop", "error"}:
        status = "applied" if patch or outputs else "noop"
    note = _normalize_text(row.get("note"), "")
    return {
        "skill": skill or _normalize_text(default_skill, ""),
        "status": status,
        "patch": patch,
        "outputs": outputs,
        "note": note or "direct_skill_runtime",
        "source": "direct_skill_runtime",
    }


def _slide_text_blob(slide: Dict[str, Any], deck: Dict[str, Any]) -> str:
    parts: List[str] = [
        _normalize_text(deck.get("title"), ""),
        _normalize_text(deck.get("topic"), ""),
        _normalize_text(slide.get("title"), ""),
        _normalize_text(slide.get("slide_type"), ""),
        _normalize_text(slide.get("layout_grid"), ""),
    ]
    for block in _as_list(slide.get("blocks"))[:10]:
        row = _as_dict(block)
        parts.append(_normalize_text(row.get("block_type") or row.get("type"), ""))
        content = row.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, dict):
            for key in ("title", "body", "text", "label", "caption", "description"):
                parts.append(_normalize_text(content.get(key), ""))
    return " ".join(part for part in parts if part).lower()


def _parse_used_content_layouts(deck: Dict[str, Any]) -> List[str]:
    raw = deck.get("used_content_layouts") if isinstance(deck.get("used_content_layouts"), list) else []
    out: List[str] = []
    for item in raw:
        text = _normalize_text(item, "").lower()
        if text in _CONTENT_LAYOUT_SET:
            out.append(text)
    return out


def _content_slide_index(slide: Dict[str, Any], deck: Dict[str, Any], used_layouts: List[str]) -> int:
    for key in ("content_slide_index", "content_index"):
        raw = deck.get(key)
        if raw is None:
            continue
        try:
            return max(0, int(raw))
        except Exception:
            continue
    page_number = int(slide.get("page_number") or 0)
    if page_number > 2:
        return max(0, page_number - 2)
    return len(used_layouts)


def _pick_content_layout(current: str, slide: Dict[str, Any], deck: Dict[str, Any]) -> str:
    locked = _as_bool(slide.get("layout_lock"), False)
    if locked and current:
        return current

    used_layouts = _parse_used_content_layouts(deck)
    idx = _content_slide_index(slide, deck, used_layouts)
    counts: Dict[str, int] = {}
    for item in used_layouts:
        counts[item] = counts.get(item, 0) + 1

    ordered_candidates: List[str] = []
    if current and current in _CONTENT_LAYOUT_SET:
        ordered_candidates.append(current)
    for step in range(len(_CONTENT_LAYOUT_ROTATION)):
        ordered_candidates.append(_CONTENT_LAYOUT_ROTATION[(idx + step) % len(_CONTENT_LAYOUT_ROTATION)])

    deduped: List[str] = []
    for candidate in ordered_candidates:
        if candidate not in _CONTENT_LAYOUT_SET:
            continue
        if candidate in deduped:
            continue
        deduped.append(candidate)

    def _violates_budget(candidate: str) -> bool:
        if used_layouts and candidate == used_layouts[-1]:
            return True
        ratio = counts.get(candidate, 0) / max(1, len(used_layouts))
        if ratio >= _CONTENT_LAYOUT_MAX_RATIO:
            return True
        if candidate == "split_2":
            split_ratio = counts.get("split_2", 0) / max(1, len(used_layouts))
            if split_ratio >= _CONTENT_LAYOUT_MAX_SPLIT_RATIO:
                return True
        return False

    for candidate in deduped:
        if not _violates_budget(candidate):
            return candidate
    for candidate in deduped:
        if not (used_layouts and candidate == used_layouts[-1]):
            return candidate
    return deduped[0] if deduped else "grid_3"


def _parse_template_whitelist(slide: Dict[str, Any]) -> List[str]:
    raw = (
        slide.get("template_family_whitelist")
        if slide.get("template_family_whitelist") is not None
        else slide.get("template_candidates")
    )
    if raw is None:
        raw = slide.get("template_whitelist")
    if isinstance(raw, str):
        values = [part.strip() for part in raw.split(",")]
    elif isinstance(raw, list):
        values = [str(item or "").strip() for item in raw]
    else:
        values = []
    valid = {str(item or "").strip().lower() for item in catalog_list_template_ids()}
    out: List[str] = []
    seen: set[str] = set()
    for item in values:
        key = _normalize_text(item, "").lower()
        if not key or key in seen:
            continue
        if valid and key not in valid:
            continue
        seen.add(key)
        out.append(key)
    return out


def _parse_used_template_families(deck: Dict[str, Any]) -> List[str]:
    raw = deck.get("used_template_families") if isinstance(deck.get("used_template_families"), list) else []
    valid = {str(item or "").strip().lower() for item in catalog_list_template_ids()}
    out: List[str] = []
    for item in raw:
        key = _normalize_text(item, "").lower()
        if not key:
            continue
        if valid and key not in valid:
            continue
        out.append(key)
    return out


def _slide_has_image_asset(slide: Dict[str, Any]) -> bool:
    blocks = slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
    for block in blocks:
        row = _as_dict(block)
        block_type = _normalize_text(row.get("block_type") or row.get("type"), "").lower()
        if block_type != "image":
            continue
        content = _as_dict(row.get("content"))
        data = _as_dict(row.get("data"))
        candidates = [
            content.get("url"),
            content.get("src"),
            content.get("imageUrl"),
            content.get("image_url"),
            data.get("url"),
            data.get("src"),
            data.get("imageUrl"),
            data.get("image_url"),
            row.get("url"),
            row.get("src"),
            row.get("imageUrl"),
            row.get("image_url"),
        ]
        if any(_normalize_text(item, "") for item in candidates):
            return True
    return False


def _resolve_template_plan(
    slide_type: str,
    _style_variant: str,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    preferred_tone: str = "",
) -> Dict[str, Any]:
    layout_grid = _normalize_text(
        slide.get("layout_grid") or slide.get("layout") or deck.get("layout_grid"),
        _DEFAULT_LAYOUT_BY_SLIDE_TYPE.get(slide_type, "split_2"),
    ).lower()
    locked = _as_bool(slide.get("template_lock"), False)
    explicit = _normalize_text(
        slide.get("template_family") or slide.get("template_id") or deck.get("template_family"),
        "",
    ).lower()
    normalized_preferred_tone = _normalize_text(preferred_tone, "").lower()
    if normalized_preferred_tone not in {"light", "dark"}:
        normalized_preferred_tone = ""
    style_default = _normalize_text(
        catalog_default_template_for_layout(layout_grid),
        "dashboard_dark",
    ).lower()
    all_templates = [str(item or "").strip().lower() for item in catalog_list_template_ids() if str(item or "").strip()]
    valid_templates = set(all_templates)
    whitelist = _parse_template_whitelist(slide)
    if locked and explicit and (not valid_templates or explicit in valid_templates):
        return {
            "selected": explicit,
            "candidates": [explicit],
            "whitelist": whitelist,
            "mode": "template_lock",
        }

    requested_template = ""
    if explicit and explicit != "auto" and (not valid_templates or explicit in valid_templates):
        requested_template = explicit

    resolved = _normalize_text(
        catalog_resolve_template_for_slide(
            slide=slide if isinstance(slide, dict) else {},
            slide_type=slide_type,
            layout_grid=layout_grid,
            requested_template=requested_template,
            desired_density=_normalize_text(slide.get("content_density"), "balanced"),
            preferred_tone=normalized_preferred_tone,
        ),
        "",
    ).lower()

    has_image_asset = _slide_has_image_asset(slide)
    if whitelist:
        candidate_pool = list(whitelist)
    else:
        candidate_pool: List[str] = []
        for template_id in all_templates:
            cap = catalog_template_capabilities(template_id)
            supported_types = {
                _normalize_text(item, "").lower()
                for item in (cap.get("supported_slide_types") if isinstance(cap.get("supported_slide_types"), list) else [])
            }
            supported_layouts = {
                _normalize_text(item, "").lower()
                for item in (cap.get("supported_layouts") if isinstance(cap.get("supported_layouts"), list) else [])
            }
            if supported_types and slide_type not in supported_types:
                continue
            if supported_layouts and layout_grid not in supported_layouts:
                continue
            if normalized_preferred_tone == "light" and template_id.endswith("_dark"):
                continue
            if normalized_preferred_tone == "dark" and template_id.endswith("_light"):
                continue
            if bool(cap.get("requires_image_asset")) and not has_image_asset:
                continue
            candidate_pool.append(template_id)
        if not candidate_pool and style_default:
            candidate_pool = [style_default]
        if not candidate_pool and all_templates:
            candidate_pool = list(all_templates)

    ordered: List[str] = []
    for candidate in [explicit, resolved]:
        key = _normalize_text(candidate, "").lower()
        if not key:
            continue
        if valid_templates and key not in valid_templates:
            continue
        if key in ordered:
            continue
        if candidate_pool and key not in candidate_pool:
            continue
        ordered.append(key)
    if slide_type == "cover" and (not explicit or explicit in _GENERIC_COVER_TEMPLATE_OVERRIDES):
        cover_preferred = _normalize_text(
            catalog_resolve_template_for_slide(
                slide=slide if isinstance(slide, dict) else {},
                slide_type="cover",
                layout_grid="hero_1",
                requested_template="",
                desired_density=_normalize_text(slide.get("content_density"), "balanced"),
                preferred_tone=normalized_preferred_tone,
            ),
            "hero_tech_cover",
        ).lower()
        if cover_preferred and cover_preferred not in ordered and (not candidate_pool or cover_preferred in candidate_pool):
            ordered.insert(0, cover_preferred)

    if slide_type == "content" and candidate_pool:
        used_templates = _parse_used_template_families(deck)
        idx = _content_slide_index(slide, deck, used_templates)
        for step in range(len(candidate_pool)):
            candidate = candidate_pool[(idx + step) % len(candidate_pool)]
            if candidate not in ordered:
                ordered.append(candidate)

        counts: Dict[str, int] = {}
        for item in used_templates:
            counts[item] = counts.get(item, 0) + 1

        def _violates_budget(candidate: str) -> bool:
            if used_templates and candidate == used_templates[-1]:
                return True
            ratio = counts.get(candidate, 0) / max(1, len(used_templates))
            if ratio >= _CONTENT_TEMPLATE_MAX_RATIO:
                return True
            if candidate == "dashboard_dark":
                dashboard_ratio = counts.get("dashboard_dark", 0) / max(1, len(used_templates))
                if dashboard_ratio >= _CONTENT_TEMPLATE_MAX_DASHBOARD_RATIO:
                    return True
            return False

        for candidate in ordered:
            if not _violates_budget(candidate):
                return {
                    "selected": candidate,
                    "candidates": ordered or candidate_pool,
                    "whitelist": whitelist,
                    "mode": "catalog_diversity",
                }
        for candidate in ordered:
            if not (used_templates and candidate == used_templates[-1]):
                return {
                    "selected": candidate,
                    "candidates": ordered or candidate_pool,
                    "whitelist": whitelist,
                    "mode": "catalog_diversity_relaxed",
                }

    selected = ordered[0] if ordered else (candidate_pool[0] if candidate_pool else (style_default or "dashboard_dark"))
    return {
        "selected": selected,
        "candidates": ordered or candidate_pool or ([selected] if selected else []),
        "whitelist": whitelist,
        "mode": "catalog_resolve",
    }


def _infer_slide_type(slide: Dict[str, Any], deck: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        slide.get("slide_type") or slide.get("page_type") or slide.get("subtype"),
        "",
    ).lower()
    if explicit in {"cover", "toc", "divider", "section", "summary", "content"}:
        return "divider" if explicit == "section" else explicit

    page_number = int(slide.get("page_number") or 0)
    total_slides = int(deck.get("total_slides") or 0)
    if page_number <= 1:
        return "cover"
    if total_slides > 0 and page_number >= total_slides:
        return "summary"
    if total_slides >= 6 and page_number == 2:
        return "toc"

    blob = _slide_text_blob(slide, deck)
    if _SECTION_HINT_RE.search(blob):
        return "divider"
    return "content"


def _infer_layout(slide_type: str, slide: Dict[str, Any], deck: Dict[str, Any]) -> str:
    current = _normalize_text(slide.get("layout_grid") or slide.get("layout"), "").lower()
    if slide_type == "content":
        return _pick_content_layout(current, slide, deck)
    if current:
        return current
    if slide_type in _DEFAULT_LAYOUT_BY_SLIDE_TYPE:
        return _DEFAULT_LAYOUT_BY_SLIDE_TYPE[slide_type]
    blob = _slide_text_blob(slide, deck)
    if _TIMELINE_HINT_RE.search(blob):
        return "timeline"
    if _COMPARE_HINT_RE.search(blob):
        return "split_2"
    return "split_2"


def _infer_render_path(slide_type: str, layout_grid: str, slide: Dict[str, Any], deck: Dict[str, Any]) -> str:
    current = _normalize_text(slide.get("render_path"), "").lower()
    if current == "svg":
        return "svg"
    return "svg"


def _choose_palette(deck: Dict[str, Any], slide: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        slide.get("palette_key") or deck.get("palette_key"),
        "",
    )
    if explicit and explicit.lower() != "auto":
        return explicit
    blob = _slide_text_blob(slide, deck)
    for hint, palette in _PALETTE_HINTS:
        if hint in blob:
            return palette
    return "platinum_white_gold"


def _choose_theme_recipe(deck: Dict[str, Any], slide: Dict[str, Any]) -> str:
    explicit = canonicalize_theme_recipe(
        slide.get("theme_recipe") or deck.get("theme_recipe") or "auto",
        fallback="auto",
    )
    if explicit != "auto":
        return explicit
    blob = _slide_text_blob(slide, deck)
    return suggest_theme_recipe_from_context(blob, slide.get("title") or "", deck.get("title") or "")


def _choose_tone(deck: Dict[str, Any], slide: Dict[str, Any], *, theme_recipe: str) -> str:
    return resolve_tone(
        slide.get("tone")
        or slide.get("theme_tone")
        or slide.get("preferred_tone")
        or deck.get("tone")
        or deck.get("theme_tone")
        or "auto",
        theme_recipe=theme_recipe,
        fallback="auto",
    )


def _choose_style(deck: Dict[str, Any], slide: Dict[str, Any]) -> str:
    recipe = _choose_theme_recipe(deck, slide)
    explicit = resolve_style_variant(
        slide.get("style_variant")
        or slide.get("style")
        or deck.get("style_variant")
        or deck.get("style")
        or "auto",
        theme_recipe=recipe,
        fallback="soft",
    )
    if explicit in {"sharp", "soft", "rounded", "pill"}:
        return explicit
    blob = _slide_text_blob(slide, deck)
    for hint, style in _STYLE_HINTS:
        if hint in blob:
            return style
    return resolve_style_variant("auto", theme_recipe=recipe, fallback="soft")


def _page_skill_directives(slide_type: str, layout_grid: str, render_path: str) -> List[str]:
    slide = _normalize_text(slide_type, "content").lower()
    layout = _normalize_text(layout_grid, "split_2").lower()
    path = _normalize_text(render_path, "svg").lower()
    directives: List[str] = [
        "Only one title area is allowed at the top of the slide.",
        "Never emit prefixes like 'Supporting point:' or 'Extra note:'.",
    ]
    if slide == "cover":
        directives.extend(
            [
                "Use one H1 title and one subtitle block only.",
                "Subtitle must be concise: <= 2 lines.",
                "Avoid oversized decorative rounded rectangles as dominant visual blocks.",
            ]
        )
    elif slide in {"summary", "toc", "divider"}:
        directives.extend(
            [
                "Use concise bullets (3-5) and keep each bullet short.",
                "Avoid mixed visual themes within the same slide.",
            ]
        )
    else:
        directives.extend(
            [
                "Bullet count should be <= 4 for dense layouts.",
                "Each bullet should stay within one short sentence.",
                "Prefer layout diversity across consecutive content slides.",
            ]
        )
        if layout in {"split_2", "asymmetric_2"}:
            directives.append("When using left-right layout, ensure text area is not overloaded.")
        if layout == "timeline":
            directives.append("Timeline slides should keep 3-5 milestones with balanced spacing.")
    if path == "svg":
        directives.append("SVG visuals must remain semantic and avoid decorative noise.")
    return directives

def _text_constraints(slide_type: str, layout_grid: str) -> Dict[str, Any]:
    slide = _normalize_text(slide_type, "content").lower()
    layout = _normalize_text(layout_grid, "split_2").lower()
    if slide == "cover":
        return {
            "subtitle_max_lines": 2,
            "subtitle_max_chars_cjk": 80,
            "subtitle_min_font_pt": 13,
            "min_title_font_pt": 30,
        }
    if slide in {"summary", "toc", "divider"}:
        return {
            "bullet_max_items": 5,
            "bullet_max_chars_cjk": 30,
            "min_body_font_pt": 11,
            "min_title_font_pt": 20,
            "bullet_auto_split": True,
        }
    if layout in {"split_2", "asymmetric_2"}:
        return {
            "bullet_max_items": 4,
            "bullet_max_chars_cjk": 26,
            "min_body_font_pt": 11,
            "min_title_font_pt": 20,
            "bullet_auto_split": True,
        }
    if layout == "timeline":
        return {
            "bullet_max_items": 5,
            "bullet_max_chars_cjk": 24,
            "min_body_font_pt": 11,
            "min_title_font_pt": 20,
            "bullet_auto_split": True,
        }
    return {
        "bullet_max_items": 5,
        "bullet_max_chars_cjk": 30,
        "min_body_font_pt": 11,
        "min_title_font_pt": 20,
        "bullet_auto_split": True,
    }
def _image_policy(slide_type: str, layout_grid: str) -> Dict[str, Any]:
    slide = _normalize_text(slide_type, "content").lower()
    layout = _normalize_text(layout_grid, "split_2").lower()
    return {
        "prefer_real_stock_images": slide == "content",
        "allow_abstract_svg_illustration": layout in {"timeline"} or slide in {"divider"},
        "cross_slide_duplicate_policy": "strict_url_and_subject_diversity",
    }


def _choose_skill_profile(slide_type: str, template_family: str) -> str:
    family = _normalize_text(template_family, "").lower()
    if slide_type == "cover":
        return "cover"
    if slide_type == "toc":
        return "toc"
    if slide_type in {"divider"}:
        return "section-divider"
    if slide_type == "summary":
        return "summary"
    if "architecture" in family or "blueprint" in family:
        return "architecture"
    if "dashboard" in family:
        return "data-story"
    if "consulting" in family:
        return "consulting"
    profile = _normalize_text(catalog_template_profiles(family).get("skill_profile"), "").lower()
    if profile and profile != "auto":
        return profile
    return "general-content"


def _agent_type_for_slide_type(slide_type: str) -> str:
    return _AGENT_BY_SLIDE_TYPE.get(slide_type, "content-page-generator")


def _recommended_skills(
    *,
    slide_type: str,
    render_path: str,
    requested_skills: List[str],
    deck: Dict[str, Any] | None = None,
    slide: Dict[str, Any] | None = None,
) -> List[str]:
    skills: List[str] = ["slide-making-skill", "design-style-skill", "ppt-orchestra-skill"]
    template_family = _normalize_text(deck.get("template_family") if isinstance(deck, dict) else "", "").lower()
    has_template_hints = bool(
        template_family and template_family not in {"auto"}
    )
    if isinstance(slide, dict):
        has_template_hints = has_template_hints or bool(
            _parse_template_whitelist(slide)
            or _normalize_text(slide.get("template_family") or slide.get("template_id"), "").lower() not in {"", "auto"}
        )
    if has_template_hints:
        skills.append("ppt-editing-skill")
    if slide_type in {"cover", "toc", "summary", "divider"}:
        skills.append("color-font-skill")
    if render_path == "svg":
        skills.append("pptx")
    skills.extend(requested_skills)
    return _dedupe_skills(skills)


def _build_skill_row(
    *,
    skill: str,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    requested_skills: List[str],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
    note = ""

    slide_type = _normalize_text(state.get("slide_type"), "content").lower()
    layout_grid = _normalize_text(state.get("layout_grid"), "split_2").lower()
    render_path = _normalize_text(state.get("render_path"), "svg").lower()
    style_variant = _normalize_text(state.get("style_variant"), "soft").lower()
    palette_key = _normalize_text(state.get("palette_key"), "platinum_white_gold")
    theme_recipe = _normalize_text(state.get("theme_recipe"), "consulting_clean").lower()
    tone = _normalize_text(state.get("tone"), "auto").lower()
    template_family = _normalize_text(state.get("template_family"), "")
    quality_profile = _normalize_text(state.get("quality_profile"), "").lower()
    scene_directives = scene_prompt_directives(quality_profile, slide_type=slide_type)

    if skill == "ppt-orchestra-skill":
        patch["slide_type"] = slide_type
        patch["layout_grid"] = layout_grid
        patch["render_path"] = render_path
        patch["agent_type"] = _agent_type_for_slide_type(slide_type)
        outputs["recommended_load_skills"] = _recommended_skills(
            slide_type=slide_type,
            render_path=render_path,
            requested_skills=requested_skills,
            deck=deck,
            slide=slide,
        )
        outputs["page_skill_directives"] = _page_skill_directives(slide_type, layout_grid, render_path) + scene_directives
        outputs["page_design_intent"] = (
            f"{slide_type} slide using {layout_grid} layout with {render_path} render path; "
            "prioritize readability, single-title hierarchy, and visual consistency."
        )
    elif skill == "slide-making-skill":
        patch["layout_grid"] = layout_grid
        patch["render_path"] = render_path
        patch["agent_type"] = _agent_type_for_slide_type(slide_type)
        outputs["theme_contract"] = {
            "keys": ["primary", "secondary", "accent", "light", "bg"],
            "layout_16x9": True,
        }
        outputs["text_constraints"] = _text_constraints(slide_type, layout_grid)
        outputs["image_policy"] = _image_policy(slide_type, layout_grid)
        if slide_type != "cover":
            outputs["page_badge_required"] = True
    elif skill == "design-style-skill":
        patch["style_variant"] = style_variant
        patch["theme_recipe"] = theme_recipe
        patch["tone"] = tone
        patch["template_family"] = template_family
        patch["skill_profile"] = _normalize_text(state.get("skill_profile"), "general-content")
        outputs["style_recipe"] = style_variant
        outputs["theme_recipe"] = theme_recipe
        outputs["tone"] = tone
        outputs["template_selection_mode"] = _normalize_text(state.get("template_selection_mode"), "catalog_resolve")
        outputs["template_candidates"] = [
            _normalize_text(item, "").lower()
            for item in _as_list(state.get("template_candidates"))
            if _normalize_text(item, "")
        ]
        outputs["template_family_whitelist"] = [
            _normalize_text(item, "").lower()
            for item in _as_list(state.get("template_family_whitelist"))
            if _normalize_text(item, "")
        ]
    elif skill == "color-font-skill":
        patch["palette_key"] = palette_key
        outputs["font_pair"] = {
            "en": "Arial",
            "zh": "Microsoft YaHei",
        }
    elif skill == "ppt-editing-skill":
        outputs["template_edit_pipeline"] = "unpack->xml-edit->clean->pack"
        outputs["template_edit_engine"] = "xml_with_python_pptx_fallback"
        outputs["placeholder_strategy"] = "markitdown+token-replace"
        patch["skill_profile"] = "template-edit"
    elif skill == "pptx":
        if render_path != "svg":
            patch["render_path"] = "svg"
        outputs["qa_pipeline"] = "markitdown+ooxml"
    elif skill == "ppt-master":
        adapter_result = execute_ppt_master_skill(slide=slide, deck=deck, state=state)
        patch.update(_as_dict(adapter_result.get("patch")))
        outputs.update(_as_dict(adapter_result.get("outputs")))
        note = _normalize_text(adapter_result.get("note"), "")
        status = _normalize_text(adapter_result.get("status"), "").lower()
        if status in {"applied", "noop", "error"}:
            return {
                "skill": skill,
                "status": status,
                "patch": patch,
                "outputs": outputs,
                "note": note or "ppt_master_adapter",
                "source": "builtin_fallback",
            }
    else:
        note = "unknown_skill_passthrough"

    status = "applied" if patch or outputs else "noop"
    if not note and status == "noop":
        note = "noop"
    return {
        "skill": skill,
        "status": status,
        "patch": patch,
        "outputs": outputs,
        "note": note,
        "source": "builtin_fallback",
    }


def execute_installed_skill_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    request = _as_dict(payload)
    requested_skills = _dedupe_skills(request.get("requested_skills"))
    slide = _as_dict(request.get("slide"))
    deck = _as_dict(request.get("deck"))
    if not deck:
        deck = _as_dict(request.get("context"))

    execution_profile = _normalize_execution_profile(
        request.get("execution_profile")
        or slide.get("execution_profile")
        or deck.get("execution_profile")
    )
    force_ppt_master_raw: Any = None
    if "force_ppt_master" in request:
        force_ppt_master_raw = request.get("force_ppt_master")
    elif "force_ppt_master" in slide:
        force_ppt_master_raw = slide.get("force_ppt_master")
    elif "force_ppt_master" in deck:
        force_ppt_master_raw = deck.get("force_ppt_master")
    scene_rule_profile = _resolve_scene_rule_profile(slide, deck, request)

    slide_type = _infer_slide_type(slide, deck)
    layout_grid = _infer_layout(slide_type, slide, deck)
    render_path = _infer_render_path(slide_type, layout_grid, slide, deck)
    theme_recipe = _choose_theme_recipe(deck, slide)
    tone = _choose_tone(deck, slide, theme_recipe=theme_recipe)
    style_variant = _choose_style(deck, slide)
    palette_key = _choose_palette(deck, slide)
    template_plan = _resolve_template_plan(slide_type, style_variant, slide, deck, preferred_tone=tone)
    template_family = _normalize_text(template_plan.get("selected"), "dashboard_dark").lower()
    skill_profile = _choose_skill_profile(slide_type, template_family)

    state: Dict[str, Any] = {
        "slide_type": slide_type,
        "layout_grid": layout_grid,
        "render_path": render_path,
        "style_variant": style_variant,
        "palette_key": palette_key,
        "theme_recipe": theme_recipe,
        "tone": tone,
        "template_family": template_family,
        "skill_profile": skill_profile,
        "template_candidates": _as_list(template_plan.get("candidates")),
        "template_family_whitelist": _as_list(template_plan.get("whitelist")),
        "template_selection_mode": _normalize_text(template_plan.get("mode"), "catalog_resolve"),
    }
    if scene_rule_profile:
        state["quality_profile"] = scene_rule_profile
    if execution_profile:
        state["execution_profile"] = execution_profile
    if force_ppt_master_raw is not None:
        state["force_ppt_master"] = force_ppt_master_raw

    require_direct_runtime = _env_flag("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "true")
    direct_runtime = _invoke_direct_skill_runtime(
        slide=slide,
        deck=deck,
        requested_skills=requested_skills,
        state=state,
    )
    direct_parsed = _as_dict(direct_runtime.get("parsed"))
    direct_context = _as_dict(direct_parsed.get("context"))
    direct_rows_raw = direct_parsed.get("results")
    direct_rows: List[Dict[str, Any]] = []
    if isinstance(direct_rows_raw, list):
        for row in direct_rows_raw:
            if not isinstance(row, dict):
                continue
            direct_rows.append(_normalize_runtime_row(row))
    elif direct_parsed:
        # Backward-compatible single-row runtime response.
        default_skill = requested_skills[0] if requested_skills else ""
        direct_rows.append(_normalize_runtime_row(direct_parsed, default_skill=default_skill))

    results: List[Dict[str, Any]] = []
    merged_patch: Dict[str, Any] = {}
    aggregated_load_skills: List[str] = []
    fulfilled_skills: set[str] = set()
    policy_violations: List[Dict[str, Any]] = []
    policy_conflicts: List[Dict[str, Any]] = []
    policy_seen_writes: Dict[str, Dict[str, Any]] = {}
    strict_policy = execution_profile == "dev_strict"
    primary_visual_skills = _primary_visual_skill_names()
    strict_primary_writer = strict_policy and _env_flag("PPT_PRIMARY_VISUAL_SINGLE_WRITER", "true")

    def _consume_row(raw_row: Dict[str, Any], *, record_fulfilled: bool = True) -> None:
        row = dict(raw_row if isinstance(raw_row, dict) else {})
        skill_key = _normalize_skill_key(row.get("skill"))
        if record_fulfilled and skill_key:
            fulfilled_skills.add(skill_key)

        row_patch = _as_dict(row.get("patch"))
        governed_patch, policy_notes, has_violation = _govern_patch_for_skill(
            skill=skill_key,
            patch=row_patch,
            seen_writes=policy_seen_writes,
            violations=policy_violations,
            conflicts=policy_conflicts,
            strict_primary_writer=strict_primary_writer,
            primary_visual_skills=primary_visual_skills,
        )
        row["patch"] = governed_patch

        status = _normalize_text(row.get("status"), "").lower()
        if status not in {"applied", "noop", "error"}:
            status = "applied" if governed_patch or _as_dict(row.get("outputs")) else "noop"
        if strict_policy and has_violation:
            status = "error"
        row["status"] = status

        if policy_notes:
            row["note"] = _append_note(row.get("note"), policy_notes)

        outputs = _as_dict(row.get("outputs"))
        if isinstance(outputs.get("recommended_load_skills"), list):
            aggregated_load_skills.extend(
                [str(item or "") for item in outputs.get("recommended_load_skills") or []]
            )

        if status != "error" and governed_patch:
            merged_patch.update(governed_patch)
            state.update(governed_patch)

        results.append(row)

    for row in direct_rows:
        _consume_row(row)

    direct_patch = _as_dict(direct_parsed.get("patch") or direct_parsed.get("slide_patch"))
    if direct_patch:
        default_direct_skill = requested_skills[0] if requested_skills else "ppt-orchestra-skill"
        governed_direct_patch, _, _ = _govern_patch_for_skill(
            skill=default_direct_skill,
            patch=direct_patch,
            seen_writes=policy_seen_writes,
            violations=policy_violations,
            conflicts=policy_conflicts,
            strict_primary_writer=strict_primary_writer,
            primary_visual_skills=primary_visual_skills,
        )
        if governed_direct_patch:
            merged_patch.update(governed_direct_patch)
            state.update(governed_direct_patch)
    if isinstance(direct_context.get("recommended_load_skills"), list):
        aggregated_load_skills.extend(
            [str(item or "") for item in direct_context.get("recommended_load_skills") or []]
        )

    unresolved_skills: List[str] = [
        skill for skill in requested_skills if _normalize_skill_key(skill) not in fulfilled_skills
    ]
    direct_reason = _normalize_text(direct_runtime.get("reason"), "")
    if require_direct_runtime and (direct_reason or unresolved_skills):
        for skill in unresolved_skills:
            _consume_row(
                {
                    "skill": skill,
                    "status": "error",
                    "patch": {},
                    "outputs": {},
                    "note": direct_reason or f"direct_skill_runtime_unresolved:{skill}",
                    "source": "direct_skill_runtime",
                },
                record_fulfilled=False,
            )
    else:
        for skill in unresolved_skills:
            row = _build_skill_row(
                skill=skill,
                slide=slide,
                deck=deck,
                requested_skills=requested_skills,
                state=state,
            )
            _consume_row(row, record_fulfilled=False)

    context = {
        "agent_type": _agent_type_for_slide_type(_normalize_text(state.get("slide_type"), "content").lower()),
        "style_variant": _normalize_text(state.get("style_variant"), "soft"),
        "palette_key": _normalize_text(state.get("palette_key"), "platinum_white_gold"),
        "theme_recipe": _normalize_text(state.get("theme_recipe"), "consulting_clean"),
        "tone": _normalize_text(state.get("tone"), "auto"),
        "template_family": _normalize_text(state.get("template_family"), "dashboard_dark"),
        "skill_profile": _normalize_text(state.get("skill_profile"), "general-content"),
        "template_candidates": [
            _normalize_text(item, "").lower()
            for item in _as_list(state.get("template_candidates"))
            if _normalize_text(item, "")
        ],
        "template_family_whitelist": [
            _normalize_text(item, "").lower()
            for item in _as_list(state.get("template_family_whitelist"))
            if _normalize_text(item, "")
        ],
        "template_selection_mode": _normalize_text(state.get("template_selection_mode"), "catalog_resolve"),
        "recommended_load_skills": _dedupe_skills(aggregated_load_skills),
        "page_skill_directives": _page_skill_directives(
            _normalize_text(state.get("slide_type"), "content"),
            _normalize_text(state.get("layout_grid"), "split_2"),
            _normalize_text(state.get("render_path"), "svg"),
        ),
        "text_constraints": _text_constraints(
            _normalize_text(state.get("slide_type"), "content"),
            _normalize_text(state.get("layout_grid"), "split_2"),
        ),
        "image_policy": _image_policy(
            _normalize_text(state.get("slide_type"), "content"),
            _normalize_text(state.get("layout_grid"), "split_2"),
        ),
        "page_design_intent": (
            f"{_normalize_text(state.get('slide_type'), 'content')} page with "
            f"{_normalize_text(state.get('layout_grid'), 'split_2')} layout"
        ),
        "sources": list(_SOURCES),
    }
    if _normalize_text(direct_context.get("agent_type"), ""):
        context["agent_type"] = _normalize_text(direct_context.get("agent_type"), context["agent_type"])
    if _normalize_text(direct_context.get("style_variant"), ""):
        context["style_variant"] = _normalize_text(direct_context.get("style_variant"), context["style_variant"])
    if _normalize_text(direct_context.get("palette_key"), ""):
        context["palette_key"] = _normalize_text(direct_context.get("palette_key"), context["palette_key"])
    if _normalize_text(direct_context.get("theme_recipe"), ""):
        context["theme_recipe"] = _normalize_text(direct_context.get("theme_recipe"), context["theme_recipe"])
    if _normalize_text(direct_context.get("tone"), ""):
        context["tone"] = _normalize_text(direct_context.get("tone"), context["tone"])
    if _normalize_text(direct_context.get("template_family"), ""):
        context["template_family"] = _normalize_text(direct_context.get("template_family"), context["template_family"])
    if _normalize_text(direct_context.get("skill_profile"), ""):
        context["skill_profile"] = _normalize_text(direct_context.get("skill_profile"), context["skill_profile"])
    if isinstance(direct_context.get("template_candidates"), list):
        context["template_candidates"] = _dedupe_text_list(
            [_normalize_text(item, "").lower() for item in direct_context.get("template_candidates") or []]
        )
    if isinstance(direct_context.get("template_family_whitelist"), list):
        context["template_family_whitelist"] = _dedupe_text_list(
            [_normalize_text(item, "").lower() for item in direct_context.get("template_family_whitelist") or []]
        )
    if _normalize_text(direct_context.get("template_selection_mode"), ""):
        context["template_selection_mode"] = _normalize_text(
            direct_context.get("template_selection_mode"),
            context["template_selection_mode"],
        )
    if isinstance(direct_context.get("page_skill_directives"), list):
        context["page_skill_directives"] = _dedupe_text_list(
            [str(item or "") for item in direct_context.get("page_skill_directives") or []]
        )
    if isinstance(direct_context.get("text_constraints"), dict):
        context["text_constraints"] = _as_dict(direct_context.get("text_constraints"))
    if isinstance(direct_context.get("image_policy"), dict):
        context["image_policy"] = _as_dict(direct_context.get("image_policy"))
    if _normalize_text(direct_context.get("page_design_intent"), ""):
        context["page_design_intent"] = _normalize_text(
            direct_context.get("page_design_intent"),
            context["page_design_intent"],
        )
    if not context["recommended_load_skills"]:
        context["recommended_load_skills"] = _recommended_skills(
            slide_type=_normalize_text(state.get("slide_type"), "content").lower(),
            render_path=_normalize_text(state.get("render_path"), "svg").lower(),
            requested_skills=requested_skills,
            deck=deck,
            slide=slide,
        )
    scene_context_directives = scene_prompt_directives(
        state.get("quality_profile"),
        slide_type=_normalize_text(state.get("slide_type"), "content"),
    )
    if scene_context_directives:
        context["page_skill_directives"] = _dedupe_text_list(
            [*(_as_list(context.get("page_skill_directives"))), *scene_context_directives]
        )
    context["skill_write_policy"] = {
        "version": "v1",
        "strict_mode": bool(strict_policy),
        "primary_visual_single_writer": bool(strict_primary_writer),
        "primary_visual_owner": sorted(primary_visual_skills),
        "single_writer_fields": sorted(_PRIMARY_VISUAL_FIELDS),
    }
    context["skill_write_violations"] = policy_violations
    context["skill_write_conflicts"] = policy_conflicts
    context["skill_write_conflict"] = policy_conflicts

    if context["agent_type"]:
        merged_patch.setdefault("agent_type", context["agent_type"])
    if context["style_variant"]:
        merged_patch.setdefault("style_variant", context["style_variant"])
    if context["palette_key"]:
        merged_patch.setdefault("palette_key", context["palette_key"])
    if context["theme_recipe"]:
        merged_patch.setdefault("theme_recipe", context["theme_recipe"])
    if context["tone"]:
        merged_patch.setdefault("tone", context["tone"])
    if context["template_family"]:
        merged_patch.setdefault("template_family", context["template_family"])
    if context["skill_profile"]:
        merged_patch.setdefault("skill_profile", context["skill_profile"])
    if state.get("quality_profile"):
        merged_patch.setdefault("quality_profile", state["quality_profile"])
    if context["recommended_load_skills"]:
        merged_patch.setdefault("load_skills", context["recommended_load_skills"])

    return {
        "version": 1,
        "results": results,
        "patch": merged_patch,
        "context": context,
        "skill_write_violations": policy_violations,
        "skill_write_conflicts": policy_conflicts,
        "skill_write_conflict": policy_conflicts,
        "note": "installed_skill_executor_ok",
    }


def _read_stdin_payload() -> Dict[str, Any]:
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        raw = buffer.read().decode("utf-8")
    else:
        raw = sys.stdin.read()
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception:
        parsed = {}
    return _as_dict(parsed)


def _write_json_stdout(payload: Dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(raw.encode("utf-8"))
    else:
        sys.stdout.write(raw)
    sys.stdout.flush()


def main() -> int:
    payload = _read_stdin_payload()
    output = execute_installed_skill_request(payload)
    _write_json_stdout(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
