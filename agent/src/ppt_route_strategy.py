"""Routing strategy for PPT export quality/speed trade-offs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict

from src.ppt_template_catalog import (
    route_policy as shared_route_policy,
    route_recommendation_policy as shared_route_recommendation_policy,
)


@dataclass(frozen=True)
class RoutePolicy:
    mode: str
    max_retry_attempts: int
    partial_retry_enabled: bool
    run_post_render_visual_qa: bool
    require_weighted_quality_score: bool
    force_rasterization: bool
    quality_threshold_offset: float
    warn_threshold_offset: float


_KNOWN_ROUTE_MODES = {"fast", "standard", "refine"}


def _to_route_policy(config: Dict[str, object]) -> RoutePolicy:
    return RoutePolicy(
        mode=str(config.get("mode") or "standard"),
        max_retry_attempts=max(1, int(config.get("max_retry_attempts") or 3)),
        partial_retry_enabled=bool(config.get("partial_retry_enabled", True)),
        run_post_render_visual_qa=bool(config.get("run_post_render_visual_qa", True)),
        require_weighted_quality_score=bool(config.get("require_weighted_quality_score", True)),
        force_rasterization=bool(config.get("force_rasterization", True)),
        quality_threshold_offset=float(config.get("quality_threshold_offset") or 0.0),
        warn_threshold_offset=float(config.get("warn_threshold_offset") or 0.0),
    )


def _resolve_route_policy_map() -> Dict[str, RoutePolicy]:
    out: Dict[str, RoutePolicy] = {}
    for mode in _KNOWN_ROUTE_MODES:
        out[mode] = _to_route_policy(shared_route_policy(mode))
    return out


def normalize_route_mode(value: str | None) -> str:
    requested = str(value or "").strip().lower()
    route_policies = _resolve_route_policy_map()
    if requested in route_policies or requested == "auto":
        return requested
    configured = str(os.getenv("PPT_ROUTE_MODE", "auto")).strip().lower()
    if configured in route_policies or configured == "auto":
        return configured
    return "auto"


def recommend_route_mode(
    *,
    slide_count: int = 0,
    constraint_count: int = 0,
    quality_profile: str | None = None,
    has_explicit_template: bool = False,
    visual_density: str | None = None,
) -> str:
    """Pick route mode based on request complexity."""
    recommendation = shared_route_recommendation_policy()
    pages = max(0, int(slide_count or 0))
    constraints = max(0, int(constraint_count or 0))
    profile = str(quality_profile or "").strip().lower()
    density = str(visual_density or "").strip().lower()
    refine_if_pages_gt = max(1, int(recommendation.get("refine_if_pages_gt") or 15))
    refine_if_constraints_gte = max(0, int(recommendation.get("refine_if_constraints_gte") or 3))
    refine_profiles = {
        str(item or "").strip().lower()
        for item in (recommendation.get("refine_quality_profiles") or [])
        if str(item or "").strip()
    }
    fast_if_pages_lte = max(1, int(recommendation.get("fast_if_pages_lte") or 5))
    fast_if_constraints_eq = max(0, int(recommendation.get("fast_if_constraints_eq") or 0))
    fast_profiles = {
        str(item or "").strip().lower()
        for item in (recommendation.get("fast_quality_profiles") or [])
    }
    fast_densities = {
        str(item or "").strip().lower()
        for item in (recommendation.get("fast_visual_densities") or [])
    }
    fast_profiles.add("")
    fast_densities.add("")
    if pages > refine_if_pages_gt or constraints >= refine_if_constraints_gte or profile in refine_profiles:
        return "refine"
    if (
        pages <= fast_if_pages_lte
        and constraints == fast_if_constraints_eq
        and (not has_explicit_template)
        and profile in fast_profiles
        and density in fast_densities
    ):
        return "fast"
    return "standard"


def resolve_route_policy(
    value: str | None,
    *,
    slide_count: int = 0,
    constraint_count: int = 0,
    quality_profile: str | None = None,
    has_explicit_template: bool = False,
    visual_density: str | None = None,
) -> RoutePolicy:
    route_policies = _resolve_route_policy_map()
    mode = normalize_route_mode(value)
    if mode == "auto":
        mode = recommend_route_mode(
            slide_count=slide_count,
            constraint_count=constraint_count,
            quality_profile=quality_profile,
            has_explicit_template=has_explicit_template,
            visual_density=visual_density,
        )
    return route_policies.get(mode, route_policies["standard"])
