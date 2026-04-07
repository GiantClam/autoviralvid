"""Adapter layer for real ppt-master skill integration.

This module centralizes:
- ppt-master skill spec discovery and availability checks
- dev_strict force-hit policy
- deterministic patch/output mapping for executor runtimes
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Set


_COMPLEX_LAYOUT_HINTS: Set[str] = {
    "timeline",
    "workflow",
    "roadmap",
    "matrix",
    "matrix_2x2",
    "matrix_3x3",
    "org_chart",
    "architecture",
    "journey_map",
    "ecosystem_map",
    "value_chain",
}

_COMPLEX_BLOCK_TYPES: Set[str] = {
    "workflow",
    "diagram",
    "architecture",
    "org_chart",
    "matrix",
    "sankey",
    "funnel",
    "treemap",
    "heatmap",
    "network",
    "alluvial",
    "process",
    "journey",
    "ecosystem",
    "value_chain",
}


def _normalize_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _normalize_key(value: Any, fallback: str = "") -> str:
    return _normalize_text(value, fallback).strip().lower()


def _env_flag(name: str, default: str = "false") -> bool:
    text = _normalize_key(os.getenv(name, default), default)
    return text in {"1", "true", "yes", "on"}


def _optional_flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _normalize_key(value, "")
    if not text:
        return None
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _normalize_execution_profile(value: Any) -> str:
    raw = _normalize_key(value, "")
    if raw in {"dev", "strict", "dev-strict", "dev_strict"}:
        return "dev_strict"
    if raw in {"prod", "safe", "prod-safe", "prod_safe"}:
        return "prod_safe"
    return ""


def _parse_env_paths(raw_value: str) -> List[Path]:
    text = _normalize_text(raw_value, "")
    if not text:
        return []
    out: List[Path] = []
    for item in text.split(os.pathsep):
        row = _normalize_text(item, "")
        if row:
            out.append(Path(row))
    return out


def execution_profile(requested: Any = None) -> str:
    requested_norm = _normalize_execution_profile(requested)
    if requested_norm:
        return requested_norm
    env_norm = _normalize_execution_profile(
        os.getenv("PPT_EXECUTION_PROFILE", "prod_safe")
    )
    return env_norm or "prod_safe"


def is_dev_strict_profile(requested: Any = None) -> bool:
    return execution_profile(requested) == "dev_strict"


def should_force_ppt_master_hit(
    *,
    requested_execution_profile: Any = None,
    requested_force_flag: Any = None,
    quality_profile: Any = None,
    purpose: Any = None,
    topic: Any = None,
) -> bool:
    request_force = _optional_flag(requested_force_flag)
    if request_force is not None:
        return request_force
    explicit_env = _normalize_text(os.getenv("PPT_FORCE_PPT_MASTER", ""), "")
    if explicit_env:
        return _env_flag("PPT_FORCE_PPT_MASTER", "false")

    # Force ppt-master for education/training content
    quality_key = _normalize_key(quality_profile, "")
    purpose_key = _normalize_key(purpose, "")
    topic_text = _normalize_text(topic, "").lower()

    education_keywords = [
        "教学",
        "课程",
        "课堂",
        "培训",
        "教育",
        "学习",
        "高中",
        "学生",
        "classroom",
        "teaching",
        "lesson",
        "education",
        "training",
        "courseware",
    ]

    if quality_key in {"training_deck", "high_density_consulting"}:
        return True

    if any(keyword in purpose_key for keyword in ["课程", "教学", "培训", "教育"]):
        return True

    if any(keyword in topic_text for keyword in education_keywords):
        return True

    return is_dev_strict_profile(requested_execution_profile)


def _skill_search_roots() -> List[Path]:
    here = Path(__file__).resolve()
    agent_root = here.parents[1]
    repo_root = here.parents[2]
    roots: List[Path] = []
    roots.extend(_parse_env_paths(os.getenv("PPT_MASTER_SKILL_ROOTS", "")))
    roots.extend(
        [
            repo_root / "vendor" / "minimax-skills" / "skills",
            repo_root / "skills",
            agent_root
            / "tests"
            / "fixtures"
            / "skills_reference"
            / "ppt-master"
            / "skills",
        ]
    )
    out: List[Path] = []
    seen: Set[str] = set()
    for root in roots:
        key = str(root).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def resolve_ppt_master_skill_spec_path() -> str:
    for root in _skill_search_roots():
        skill_file = root / "ppt-master" / "SKILL.md"
        if skill_file.exists():
            return str(skill_file)
    return ""


def _resolve_render_path(slide: Dict[str, Any], state: Dict[str, Any]) -> str:
    return _normalize_key(
        state.get("render_path") or slide.get("render_path"),
        "svg",
    )


def _resolve_layout_grid(slide: Dict[str, Any], state: Dict[str, Any]) -> str:
    return _normalize_key(
        state.get("layout_grid") or slide.get("layout_grid") or slide.get("layout"),
        "split_2",
    )


def _block_types(slide: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    blocks = slide.get("blocks")
    if isinstance(blocks, list):
        for item in blocks:
            if not isinstance(item, dict):
                continue
            t = _normalize_key(item.get("block_type") or item.get("type"), "")
            if t:
                out.add(t)
    return out


def is_ppt_master_candidate(
    slide: Dict[str, Any], state: Dict[str, Any] | None = None
) -> bool:
    runtime = state if isinstance(state, dict) else {}
    render_path = _resolve_render_path(slide, runtime)
    if render_path == "svg":
        return True
    layout = _resolve_layout_grid(slide, runtime)
    if layout in _COMPLEX_LAYOUT_HINTS:
        return True
    types = _block_types(slide)
    if types & _COMPLEX_BLOCK_TYPES:
        return True
    slide_type = _normalize_key(
        runtime.get("slide_type") or slide.get("slide_type"), ""
    )
    return slide_type in {"timeline", "workflow", "diagram", "architecture"}


def execute_ppt_master_skill(
    *,
    slide: Dict[str, Any],
    deck: Dict[str, Any],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    requested_profile = (
        state.get("execution_profile")
        or slide.get("execution_profile")
        or deck.get("execution_profile")
    )
    requested_force_flag = (
        state.get("force_ppt_master")
        if "force_ppt_master" in state
        else slide.get("force_ppt_master")
        if "force_ppt_master" in slide
        else deck.get("force_ppt_master")
    )
    resolved_profile = execution_profile(requested_profile)
    strict_hit = should_force_ppt_master_hit(
        requested_execution_profile=resolved_profile,
        requested_force_flag=requested_force_flag,
    )
    enabled = _env_flag("PPT_MASTER_SKILL_ENABLED", "true")
    if not enabled:
        return {
            "status": "error" if strict_hit else "noop",
            "patch": {},
            "outputs": {},
            "note": "ppt_master_skill_disabled",
        }

    skill_spec_path = resolve_ppt_master_skill_spec_path()
    if not skill_spec_path:
        return {
            "status": "error" if strict_hit else "noop",
            "patch": {},
            "outputs": {
                "ppt_master_adapter": {
                    "active": False,
                    "reason": "skill_spec_missing",
                }
            },
            "note": "ppt_master_skill_spec_missing",
        }

    patch: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
    complex_candidate = is_ppt_master_candidate(slide, state)
    render_path = _resolve_render_path(slide, state)
    current_profile = _normalize_key(state.get("skill_profile"), "")
    if complex_candidate and render_path != "svg":
        patch["render_path"] = "svg"
    if complex_candidate and not current_profile:
        patch["skill_profile"] = "architecture"

    outputs["ppt_master_adapter"] = {
        "active": True,
        "skill_spec_path": skill_spec_path,
        "execution_profile": resolved_profile,
        "force_hit": bool(strict_hit),
        "complex_candidate": bool(complex_candidate),
    }
    outputs["recommended_load_skills"] = ["ppt-master", "pptx"]
    outputs["page_skill_directives"] = [
        "Follow ppt-master serial pipeline discipline for SVG-first complex pages.",
        "Do not batch-generate SVG pages in grouped chunks when ppt-master path is selected.",
        "Keep source-to-layout semantic mapping stable before post-processing.",
    ]
    outputs["ppt_master_contract"] = {
        "serial_execution": True,
        "no_cross_phase_bundling": True,
        "no_subagent_svg_generation": True,
        "sequential_page_generation_only": True,
    }
    if not patch:
        patch["skill_profile"] = current_profile or (
            "architecture"
            if complex_candidate
            else _normalize_key(deck.get("skill_profile"), "general-content")
        )
    return {
        "status": "applied" if patch or outputs else "noop",
        "patch": patch,
        "outputs": outputs,
        "note": "ppt_master_adapter_applied",
    }
