"""Direct skill runtime adapter for PPT planning.

This module is designed to be invoked as an external process by
``src.installed_skill_executor`` through stdin/stdout JSON.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from src.ppt_codex_skill_bridge import (
    build_skill_specs_block,
    invoke_codex_cli_json,
    load_skill_specs,
    normalize_codex_cli_model_id,
    normalize_text as _bridge_normalize_text,
    parse_command_args as _bridge_parse_command_args,
    resolve_skill_roots,
)
from src.ppt_master_skill_adapter import execute_ppt_master_skill
from src.ppt_template_catalog import (
    list_template_ids as catalog_list_template_ids,
    resolve_template_for_slide as catalog_resolve_template_for_slide,
    template_capabilities as catalog_template_capabilities,
    template_profiles as catalog_template_profiles,
)

_DEFAULT_LAYOUT_BY_SLIDE_TYPE: Dict[str, str] = {
    "cover": "hero_1",
    "toc": "split_2",
    "divider": "split_2",
    "section": "split_2",
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

_STYLE_TEMPLATE_BY_TYPE: Dict[str, Dict[str, str]] = {
    "sharp": {
        "cover": "hero_tech_cover",
        "toc": "dashboard_dark",
        "divider": "architecture_dark_panel",
        "summary": "dashboard_dark",
        "content": "architecture_dark_panel",
    },
    "soft": {
        "cover": "hero_tech_cover",
        "toc": "consulting_warm_light",
        "divider": "ops_lifecycle_light",
        "summary": "comparison_cards_light",
        "content": "consulting_warm_light",
    },
    "rounded": {
        "cover": "hero_dark",
        "toc": "ops_lifecycle_light",
        "divider": "ops_lifecycle_light",
        "summary": "ops_lifecycle_light",
        "content": "ops_lifecycle_light",
    },
    "pill": {
        "cover": "hero_dark",
        "toc": "dashboard_dark",
        "divider": "ecosystem_orange_dark",
        "summary": "ecosystem_orange_dark",
        "content": "bento_mosaic_dark",
    },
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
]

_SECTION_HINT_RE = re.compile(
    r"(section|chapter|part|agenda)\b",
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

_SKILL_ALIASES: Dict[str, str] = {
    "pptx": "pptx-generator",
}

_CONTENT_LAYOUT_ROTATION: List[str] = ["split_2", "grid_3", "grid_4", "asymmetric_2", "timeline"]
_CONTENT_LAYOUT_SET = set(_CONTENT_LAYOUT_ROTATION)
_CONTENT_LAYOUT_MAX_RATIO = 0.5
_CONTENT_LAYOUT_MAX_SPLIT_RATIO = 0.34
_CONTENT_TEMPLATE_MAX_RATIO = 0.5
_CONTENT_TEMPLATE_MAX_DASHBOARD_RATIO = 0.34
_GENERIC_COVER_TEMPLATE_OVERRIDES = {
    "",
    "auto",
    "dashboard_dark",
    "bento_2x2_dark",
    "bento_mosaic_dark",
    "split_media_dark",
}


def _normalize_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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


def _env_flag(name: str, default: str = "false") -> bool:
    text = str(os.getenv(name, default) or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _skill_roots() -> List[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    defaults = [
        repo_root / "vendor" / "minimax-skills" / "plugins" / "pptx-plugin" / "skills",
        repo_root / "vendor" / "minimax-skills" / "skills",
        repo_root / "skills",
    ]
    return resolve_skill_roots(env_key="PPT_DIRECT_SKILL_RUNTIME_SKILL_ROOTS", default_roots=defaults)


def _build_codex_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["version", "results", "patch", "context"],
        "properties": {
            "version": {"type": "integer"},
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["skill", "status", "patch", "outputs"],
                    "properties": {
                        "skill": {"type": "string"},
                        "status": {"type": "string"},
                        "patch": {"type": "object"},
                        "outputs": {"type": "object"},
                        "note": {"type": "string"},
                        "source": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
            "patch": {"type": "object"},
            "context": {"type": "object"},
            "note": {"type": "string"},
        },
        "additionalProperties": True,
    }


def _build_codex_prompt(
    *,
    requested_skills: List[str],
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    state: Dict[str, Any],
) -> str:
    docs = load_skill_specs(
        requested_skills=requested_skills,
        skill_roots=_skill_roots(),
        aliases=_SKILL_ALIASES,
    )
    max_chars_raw = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_SKILL_CONTENT_MAX_CHARS", "120000"), "120000")
    try:
        max_chars = max(4000, int(max_chars_raw))
    except Exception:
        max_chars = 120000
    skill_block = build_skill_specs_block(docs, max_chars=max_chars)
    payload = {
        "requested_skills": requested_skills,
        "slide": slide,
        "deck": deck,
        "state": state,
    }
    payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "You are a strict PPT skill runtime planner.\n"
        "Use only the provided skill specs as constraints. Do not invent skills.\n"
        "Return strict JSON only; no markdown.\n"
        "Output contract:\n"
        "1) version must be 1\n"
        "2) results must include one row per requested skill in the same order\n"
        "3) each result.status in applied|noop|error\n"
        "4) patch/context must be objects\n"
        "5) patch keys should stay in planning scope: slide_type, layout_grid, render_path, "
        "template_family, skill_profile, style_variant, palette_key, agent_type, load_skills\n\n"
        "Loaded skill specifications:\n\n"
        f"{skill_block}\n\n"
        "Runtime input:\n"
        f"{payload_text}\n"
    )


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


def _normalize_runtime_output(
    raw_output: Dict[str, Any],
    requested_skills: List[str],
    *,
    source: str,
) -> Dict[str, Any]:
    out = _as_dict(raw_output)
    results_raw = out.get("results") if isinstance(out.get("results"), list) else []
    by_skill: Dict[str, Dict[str, Any]] = {}
    normalized_results: List[Dict[str, Any]] = []
    for row in results_raw:
        if not isinstance(row, dict):
            continue
        normalized = _normalize_runtime_row(row)
        skill = _normalize_skill_key(normalized.get("skill"))
        if not skill:
            continue
        normalized["source"] = source
        by_skill[skill] = normalized
    for skill in requested_skills:
        existing = by_skill.get(skill)
        if existing:
            normalized_results.append(existing)
            continue
        normalized_results.append(
            {
                "skill": skill,
                "status": "error",
                "patch": {},
                "outputs": {},
                "note": f"{source}_missing_skill_result:{skill}",
                "source": source,
            }
        )
    normalized_patch = _as_dict(out.get("patch") or out.get("slide_patch"))
    normalized_context = _as_dict(out.get("context"))
    return {
        "version": 1,
        "results": normalized_results,
        "patch": normalized_patch,
        "context": normalized_context,
        "note": _normalize_text(out.get("note"), f"{source}_ok"),
    }


def _runtime_error_output(
    *,
    requested_skills: List[str],
    reason: str,
    source: str,
) -> Dict[str, Any]:
    context = {
        "agent_type": "content-page-generator",
        "style_variant": "soft",
        "palette_key": "platinum_white_gold",
        "template_family": "dashboard_dark",
        "skill_profile": "general-content",
        "recommended_load_skills": list(requested_skills),
        "page_skill_directives": [],
        "text_constraints": {},
        "image_policy": {},
        "page_design_intent": "",
        "sources": list(_SOURCES),
    }
    return {
        "version": 1,
        "results": [
            {
                "skill": skill,
                "status": "error",
                "patch": {},
                "outputs": {},
                "note": reason,
                "source": source,
            }
            for skill in requested_skills
        ],
        "patch": {},
        "context": context,
        "note": reason,
    }


def _run_codex_cli_mode(
    *,
    requested_skills: List[str],
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    prompt = _build_codex_prompt(
        requested_skills=requested_skills,
        slide=slide,
        deck=deck,
        state=state,
    )
    bin_name = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_CODEX_BIN", ""), "codex")
    args = _bridge_parse_command_args(os.getenv("PPT_DIRECT_SKILL_RUNTIME_CODEX_ARGS", ""))
    if not args:
        args = ["exec", "--skip-git-repo-check", "--sandbox", "read-only"]
    timeout_raw = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_CODEX_TIMEOUT_SEC", "90"), "90")
    try:
        timeout_sec = max(15, int(timeout_raw))
    except Exception:
        timeout_sec = 90
    cwd = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_CODEX_CWD", ""), "")
    if not cwd:
        cwd = str(Path(__file__).resolve().parents[1])
    model_id = normalize_codex_cli_model_id(_normalize_text(os.getenv("CONTENT_LLM_MODEL", ""), ""))
    invoked = invoke_codex_cli_json(
        prompt=prompt,
        schema=None,
        model_id=model_id,
        bin_name=bin_name,
        extra_args=args,
        cwd=Path(cwd),
        timeout_sec=timeout_sec,
    )
    if not bool(invoked.get("ok")):
        reason = _bridge_normalize_text(invoked.get("reason"), "codex_cli_failed")
        strict = _env_flag("PPT_DIRECT_SKILL_RUNTIME_REQUIRE", "true")
        if strict:
            return _runtime_error_output(
                requested_skills=requested_skills,
                reason=reason,
                source="codex_cli",
            )
        return {}
    data = _as_dict(invoked.get("data"))
    if not data:
        return {}
    return _normalize_runtime_output(
        data,
        requested_skills,
        source="codex_cli",
    )


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


def _parse_used_content_layouts(deck: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
    raw = []
    if isinstance(deck.get("used_content_layouts"), list):
        raw = list(deck.get("used_content_layouts") or [])
    elif isinstance(state.get("used_content_layouts"), list):
        raw = list(state.get("used_content_layouts") or [])
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
        # Keep first content pages more diverse when page_number exists.
        return max(0, page_number - 2)
    return len(used_layouts)


def _pick_content_layout(current: str, slide: Dict[str, Any], deck: Dict[str, Any], state: Dict[str, Any]) -> str:
    locked = _as_bool(state.get("layout_lock"), False) or _as_bool(slide.get("layout_lock"), False)
    if locked and current:
        return current

    used_layouts = _parse_used_content_layouts(deck, state)
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


def _parse_template_whitelist(slide: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
    raw = (
        state.get("template_family_whitelist")
        if state.get("template_family_whitelist") is not None
        else slide.get("template_family_whitelist")
    )
    if raw is None:
        raw = (
            state.get("template_candidates")
            if state.get("template_candidates") is not None
            else slide.get("template_candidates")
        )
    if raw is None:
        raw = state.get("template_whitelist") if state.get("template_whitelist") is not None else slide.get("template_whitelist")
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


def _parse_used_template_families(deck: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
    raw: List[Any] = []
    if isinstance(deck.get("used_template_families"), list):
        raw = list(deck.get("used_template_families") or [])
    elif isinstance(state.get("used_template_families"), list):
        raw = list(state.get("used_template_families") or [])
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
    style_variant: str,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    layout_grid = _normalize_text(
        state.get("layout_grid") or slide.get("layout_grid") or slide.get("layout") or deck.get("layout_grid"),
        _DEFAULT_LAYOUT_BY_SLIDE_TYPE.get(slide_type, "split_2"),
    ).lower()
    locked = _as_bool(state.get("template_lock"), False) or _as_bool(slide.get("template_lock"), False)
    explicit = _normalize_text(
        state.get("template_family")
        or slide.get("template_family")
        or slide.get("template_id")
        or deck.get("template_family"),
        "",
    ).lower()
    mapping = _STYLE_TEMPLATE_BY_TYPE.get(style_variant, _STYLE_TEMPLATE_BY_TYPE["soft"])
    style_default = _normalize_text(
        mapping.get(slide_type, mapping.get("content", "dashboard_dark")),
        "dashboard_dark",
    ).lower()
    all_templates = [str(item or "").strip().lower() for item in catalog_list_template_ids() if str(item or "").strip()]
    valid_templates = set(all_templates)
    whitelist = _parse_template_whitelist(slide, state)
    if locked and explicit and (not valid_templates or explicit in valid_templates):
        return {"selected": explicit, "candidates": [explicit], "whitelist": whitelist, "mode": "template_lock"}

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
        cover_preferred = _normalize_text(mapping.get("cover"), "hero_dark").lower()
        if cover_preferred and cover_preferred not in ordered and (not candidate_pool or cover_preferred in candidate_pool):
            ordered.insert(0, cover_preferred)

    if slide_type == "content" and candidate_pool:
        used_templates = _parse_used_template_families(deck, state)
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


def _page_skill_directives(slide_type: str, layout_grid: str, render_path: str) -> List[str]:
    slide = _normalize_text(slide_type, "content").lower()
    layout = _normalize_text(layout_grid, "split_2").lower()
    path = _normalize_text(render_path, "pptxgenjs").lower()
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
    if path in {"svg", "png_fallback"}:
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


def _infer_slide_type(slide: Dict[str, Any], deck: Dict[str, Any], state: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        state.get("slide_type")
        or slide.get("slide_type")
        or slide.get("page_type")
        or slide.get("subtype"),
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
    if _SECTION_HINT_RE.search(_slide_text_blob(slide, deck)):
        return "divider"
    return "content"


def _infer_layout(slide_type: str, slide: Dict[str, Any], deck: Dict[str, Any], state: Dict[str, Any]) -> str:
    current = _normalize_text(state.get("layout_grid") or slide.get("layout_grid") or slide.get("layout"), "").lower()
    if slide_type == "content":
        return _pick_content_layout(current, slide, deck, state)
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


def _infer_render_path(
    slide_type: str,
    layout_grid: str,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    state: Dict[str, Any],
) -> str:
    current = _normalize_text(state.get("render_path") or slide.get("render_path"), "").lower()
    if current in {"pptxgenjs", "svg", "png_fallback"}:
        return current
    # Keep svg/png as explicit opt-in; default path should remain editable and stable.
    return "pptxgenjs"


def _choose_palette(deck: Dict[str, Any], slide: Dict[str, Any], state: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        state.get("palette_key") or slide.get("palette_key") or deck.get("palette_key"),
        "",
    )
    if explicit and explicit.lower() != "auto":
        return explicit
    blob = _slide_text_blob(slide, deck)
    for hint, palette in _PALETTE_HINTS:
        if hint in blob:
            return palette
    return "platinum_white_gold"


def _choose_style(deck: Dict[str, Any], slide: Dict[str, Any], state: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        state.get("style_variant")
        or slide.get("style_variant")
        or slide.get("style")
        or deck.get("style_variant")
        or deck.get("style"),
        "",
    ).lower()
    if explicit in {"sharp", "soft", "rounded", "pill"}:
        return explicit
    blob = _slide_text_blob(slide, deck)
    for hint, style in _STYLE_HINTS:
        if hint in blob:
            return style
    return "soft"


def _choose_template_family(
    slide_type: str,
    style_variant: str,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    state: Dict[str, Any],
) -> str:
    plan = _resolve_template_plan(slide_type, style_variant, slide, deck, state)
    return _normalize_text(plan.get("selected"), "dashboard_dark").lower()


def _choose_skill_profile(slide_type: str, template_family: str, state: Dict[str, Any]) -> str:
    explicit = _normalize_text(state.get("skill_profile"), "").lower()
    if explicit and explicit != "auto":
        return explicit
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
    deck: Dict[str, Any],
    slide: Dict[str, Any],
    state: Dict[str, Any],
) -> List[str]:
    skills: List[str] = ["slide-making-skill", "design-style-skill", "ppt-orchestra-skill"]
    template_family = _normalize_text(state.get("template_family") or deck.get("template_family"), "").lower()
    has_template_hints = bool(template_family and template_family not in {"auto"})
    has_template_hints = has_template_hints or bool(
        _parse_template_whitelist(slide, state)
        or _normalize_text(slide.get("template_family") or slide.get("template_id"), "").lower() not in {"", "auto"}
    )
    if has_template_hints:
        skills.append("ppt-editing-skill")
    if slide_type in {"cover", "toc", "summary", "divider"}:
        skills.append("color-font-skill")
    if render_path in {"svg", "png_fallback"}:
        skills.append("pptx")
    skills.extend(requested_skills)
    return _dedupe_skills(skills)


def _build_skill_row(skill: str, state: Dict[str, Any], requested_skills: List[str], slide: Dict[str, Any], deck: Dict[str, Any]) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
    note = ""

    slide_type = _normalize_text(state.get("slide_type"), "content").lower()
    layout_grid = _normalize_text(state.get("layout_grid"), "split_2").lower()
    render_path = _normalize_text(state.get("render_path"), "pptxgenjs").lower()
    style_variant = _normalize_text(state.get("style_variant"), "soft").lower()
    palette_key = _normalize_text(state.get("palette_key"), "platinum_white_gold")
    template_family = _normalize_text(state.get("template_family"), "dashboard_dark")
    skill_profile = _normalize_text(state.get("skill_profile"), "general-content")

    if skill == "ppt-orchestra-skill":
        patch.update(
            {
                "slide_type": slide_type,
                "layout_grid": layout_grid,
                "render_path": render_path,
                "agent_type": _agent_type_for_slide_type(slide_type),
            }
        )
        outputs["recommended_load_skills"] = _recommended_skills(
            slide_type=slide_type,
            render_path=render_path,
            requested_skills=requested_skills,
            deck=deck,
            slide=slide,
            state=state,
        )
        outputs["planning_mode"] = "skill-first"
        outputs["page_skill_directives"] = _page_skill_directives(slide_type, layout_grid, render_path)
        outputs["page_design_intent"] = (
            f"{slide_type} slide using {layout_grid} layout with {render_path} render path; "
            "prioritize readability, single-title hierarchy, and visual consistency."
        )
    elif skill == "slide-making-skill":
        patch.update(
            {
                "layout_grid": layout_grid,
                "render_path": render_path,
                "agent_type": _agent_type_for_slide_type(slide_type),
            }
        )
        outputs["theme_contract"] = {
            "keys": ["primary", "secondary", "accent", "light", "bg"],
            "layout_16x9": True,
        }
        outputs["text_constraints"] = _text_constraints(slide_type, layout_grid)
        outputs["image_policy"] = _image_policy(slide_type, layout_grid)
        if slide_type != "cover":
            outputs["page_badge_required"] = True
    elif skill == "design-style-skill":
        patch.update(
            {
                "style_variant": style_variant,
                "template_family": template_family,
                "skill_profile": skill_profile,
            }
        )
        outputs["style_recipe"] = style_variant
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
        outputs["font_pair"] = {"en": "Arial", "zh": "Microsoft YaHei"}
    elif skill == "ppt-editing-skill":
        patch["skill_profile"] = "template-edit"
        outputs["template_edit_pipeline"] = "unpack->xml-edit->clean->pack"
        outputs["template_edit_engine"] = "xml_with_python_pptx_fallback"
        outputs["placeholder_strategy"] = "markitdown+token-replace"
    elif skill == "pptx":
        blob = _slide_text_blob(slide, deck)
        if render_path == "pptxgenjs" and _TIMELINE_HINT_RE.search(blob):
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
                "source": "direct_skill_runtime",
            }
    else:
        note = "unknown_skill_passthrough"

    status = "applied" if patch or outputs else "noop"
    if status == "noop" and not note:
        note = "noop"
    return {
        "skill": skill,
        "status": status,
        "patch": patch,
        "outputs": outputs,
        "note": note,
        "source": "direct_skill_runtime",
    }


def execute_direct_skill_runtime(payload: Dict[str, Any]) -> Dict[str, Any]:
    req = _as_dict(payload)
    requested_skills = _dedupe_skills(req.get("requested_skills"))
    slide = _as_dict(req.get("slide"))
    deck = _as_dict(req.get("deck"))
    state = _as_dict(req.get("state"))
    execution_profile = _normalize_execution_profile(
        state.get("execution_profile")
        or slide.get("execution_profile")
        or deck.get("execution_profile")
    )
    force_ppt_master_raw: Any = None
    if "force_ppt_master" in state:
        force_ppt_master_raw = state.get("force_ppt_master")
    elif "force_ppt_master" in slide:
        force_ppt_master_raw = slide.get("force_ppt_master")
    elif "force_ppt_master" in deck:
        force_ppt_master_raw = deck.get("force_ppt_master")

    if not requested_skills:
        requested_skills = ["ppt-orchestra-skill", "slide-making-skill", "design-style-skill"]

    mode = _normalize_text(os.getenv("PPT_DIRECT_SKILL_RUNTIME_MODE", "builtin"), "builtin").lower()
    if mode in {"codex", "codex-cli", "codex_cli"}:
        codex_out = _run_codex_cli_mode(
            requested_skills=requested_skills,
            slide=slide,
            deck=deck,
            state=state,
        )
        if codex_out:
            return codex_out

    resolved_state: Dict[str, Any] = {}
    resolved_state["slide_type"] = _infer_slide_type(slide, deck, state)
    resolved_state["layout_grid"] = _infer_layout(resolved_state["slide_type"], slide, deck, state)
    resolved_state["render_path"] = _infer_render_path(
        resolved_state["slide_type"],
        resolved_state["layout_grid"],
        slide,
        deck,
        state,
    )
    resolved_state["style_variant"] = _choose_style(deck, slide, state)
    resolved_state["palette_key"] = _choose_palette(deck, slide, state)
    template_plan = _resolve_template_plan(
        resolved_state["slide_type"],
        resolved_state["style_variant"],
        slide,
        deck,
        state,
    )
    resolved_state["template_family"] = _normalize_text(template_plan.get("selected"), "dashboard_dark").lower()
    resolved_state["template_candidates"] = _as_list(template_plan.get("candidates"))
    resolved_state["template_family_whitelist"] = _as_list(template_plan.get("whitelist"))
    resolved_state["template_selection_mode"] = _normalize_text(template_plan.get("mode"), "catalog_resolve")
    resolved_state["skill_profile"] = _choose_skill_profile(
        resolved_state["slide_type"],
        resolved_state["template_family"],
        state,
    )
    if execution_profile:
        resolved_state["execution_profile"] = execution_profile
    if force_ppt_master_raw is not None:
        resolved_state["force_ppt_master"] = force_ppt_master_raw

    results: List[Dict[str, Any]] = []
    merged_patch: Dict[str, Any] = {}
    aggregated_load_skills: List[str] = []
    aggregated_page_skill_directives: List[str] = []
    aggregated_text_constraints: Dict[str, Any] = {}
    aggregated_image_policy: Dict[str, Any] = {}
    page_design_intent = ""

    for skill in requested_skills:
        row = _build_skill_row(skill, resolved_state, requested_skills, slide, deck)
        results.append(row)
        row_patch = _as_dict(row.get("patch"))
        if row_patch:
            merged_patch.update(row_patch)
            resolved_state.update(row_patch)
        outputs = _as_dict(row.get("outputs"))
        if isinstance(outputs.get("recommended_load_skills"), list):
            aggregated_load_skills.extend([str(item or "") for item in outputs.get("recommended_load_skills") or []])
        if isinstance(outputs.get("page_skill_directives"), list):
            aggregated_page_skill_directives.extend(
                [str(item or "").strip() for item in outputs.get("page_skill_directives") or [] if str(item or "").strip()]
            )
        if isinstance(outputs.get("text_constraints"), dict):
            aggregated_text_constraints.update(outputs.get("text_constraints") or {})
        if isinstance(outputs.get("image_policy"), dict):
            aggregated_image_policy.update(outputs.get("image_policy") or {})
        if not page_design_intent:
            page_design_intent = _normalize_text(outputs.get("page_design_intent"), "")

    context = {
        "agent_type": _agent_type_for_slide_type(_normalize_text(resolved_state.get("slide_type"), "content").lower()),
        "style_variant": _normalize_text(resolved_state.get("style_variant"), "soft"),
        "palette_key": _normalize_text(resolved_state.get("palette_key"), "platinum_white_gold"),
        "template_family": _normalize_text(resolved_state.get("template_family"), "dashboard_dark"),
        "skill_profile": _normalize_text(resolved_state.get("skill_profile"), "general-content"),
        "template_candidates": [
            _normalize_text(item, "").lower()
            for item in _as_list(resolved_state.get("template_candidates"))
            if _normalize_text(item, "")
        ],
        "template_family_whitelist": [
            _normalize_text(item, "").lower()
            for item in _as_list(resolved_state.get("template_family_whitelist"))
            if _normalize_text(item, "")
        ],
        "template_selection_mode": _normalize_text(resolved_state.get("template_selection_mode"), "catalog_resolve"),
        "recommended_load_skills": _dedupe_skills(aggregated_load_skills),
        "page_skill_directives": list(dict.fromkeys([item for item in aggregated_page_skill_directives if item])),
        "text_constraints": aggregated_text_constraints,
        "image_policy": aggregated_image_policy,
        "page_design_intent": page_design_intent
        or f"{_normalize_text(resolved_state.get('slide_type'), 'content')} page with {_normalize_text(resolved_state.get('layout_grid'), 'split_2')} layout",
        "sources": list(_SOURCES),
    }
    if not context["recommended_load_skills"]:
        context["recommended_load_skills"] = _recommended_skills(
            slide_type=_normalize_text(resolved_state.get("slide_type"), "content").lower(),
            render_path=_normalize_text(resolved_state.get("render_path"), "pptxgenjs").lower(),
            requested_skills=requested_skills,
            deck=deck,
            slide=slide,
            state=resolved_state,
        )
    if not context.get("page_skill_directives"):
        context["page_skill_directives"] = _page_skill_directives(
            _normalize_text(resolved_state.get("slide_type"), "content"),
            _normalize_text(resolved_state.get("layout_grid"), "split_2"),
            _normalize_text(resolved_state.get("render_path"), "pptxgenjs"),
        )
    if not context.get("text_constraints"):
        context["text_constraints"] = _text_constraints(
            _normalize_text(resolved_state.get("slide_type"), "content"),
            _normalize_text(resolved_state.get("layout_grid"), "split_2"),
        )
    if not context.get("image_policy"):
        context["image_policy"] = _image_policy(
            _normalize_text(resolved_state.get("slide_type"), "content"),
            _normalize_text(resolved_state.get("layout_grid"), "split_2"),
        )

    merged_patch.setdefault("agent_type", context["agent_type"])
    merged_patch.setdefault("style_variant", context["style_variant"])
    merged_patch.setdefault("palette_key", context["palette_key"])
    merged_patch.setdefault("template_family", context["template_family"])
    merged_patch.setdefault("skill_profile", context["skill_profile"])
    merged_patch.setdefault("load_skills", context["recommended_load_skills"])

    return {
        "version": 1,
        "results": results,
        "patch": merged_patch,
        "context": context,
        "note": "ppt_direct_skill_runtime_ok",
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
    output = execute_direct_skill_runtime(payload)
    _write_json_stdout(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
