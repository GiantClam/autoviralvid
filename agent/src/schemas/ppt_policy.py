"""Structured policy schemas for PPT route/orchestration configuration."""

from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field, field_validator


_DEFAULT_LAYOUT_CYCLE = ["grid_3", "grid_4", "bento_5", "timeline", "bento_6"]
_DEFAULT_LAYOUT_REPLACE_FROM = ["split_2", "asymmetric_2"]
_DEFAULT_SKIP_SLIDE_TYPES = ["cover", "summary", "toc", "divider", "hero_1"]


def _normalize_key_list(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        key = str(value or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


class RoutePolicyConfig(BaseModel):
    mode: Literal["fast", "standard", "refine"]
    max_retry_attempts: int = Field(default=3, ge=1, le=10)
    partial_retry_enabled: bool = True
    run_post_render_visual_qa: bool = True
    require_weighted_quality_score: bool = True
    force_rasterization: bool = True
    quality_threshold_offset: float = Field(default=0.0, ge=-30.0, le=30.0)
    warn_threshold_offset: float = Field(default=0.0, ge=-30.0, le=30.0)


class RouteRecommendationConfig(BaseModel):
    refine_if_pages_gt: int = Field(default=15, ge=1, le=200)
    refine_if_constraints_gte: int = Field(default=3, ge=0, le=50)
    refine_quality_profiles: List[str] = Field(default_factory=lambda: ["high_density_consulting"])
    fast_if_pages_lte: int = Field(default=5, ge=1, le=200)
    fast_if_constraints_eq: int = Field(default=0, ge=0, le=50)
    fast_quality_profiles: List[str] = Field(
        default_factory=lambda: ["", "auto", "default", "lenient_draft"]
    )
    fast_visual_densities: List[str] = Field(default_factory=lambda: ["", "auto", "balanced", "sparse"])

    @field_validator("refine_quality_profiles", "fast_quality_profiles", "fast_visual_densities")
    @classmethod
    def normalize_lists(cls, value: List[str]) -> List[str]:
        return _normalize_key_list(value)


class DenseLayoutRemapPolicy(BaseModel):
    enabled: bool = False
    replace_from: List[str] = Field(default_factory=lambda: list(_DEFAULT_LAYOUT_REPLACE_FROM))
    cycle: List[str] = Field(default_factory=lambda: list(_DEFAULT_LAYOUT_CYCLE))

    @field_validator("replace_from", "cycle")
    @classmethod
    def normalize_layout_lists(cls, value: List[str]) -> List[str]:
        return _normalize_key_list(value)


class FamilyConvergencePolicy(BaseModel):
    enabled: bool = False
    only_when_deck_template_auto: bool = True
    layout_to_family: Dict[str, str] = Field(default_factory=dict)
    default_family: str = "dashboard_dark"
    lock_after_apply: bool = True
    skip_slide_types: List[str] = Field(default_factory=lambda: list(_DEFAULT_SKIP_SLIDE_TYPES))

    @field_validator("layout_to_family", mode="before")
    @classmethod
    def normalize_layout_mapping(cls, value: object) -> Dict[str, str]:
        if not isinstance(value, dict):
            return {}
        out: Dict[str, str] = {}
        for raw_key, raw_val in value.items():
            key = str(raw_key or "").strip().lower()
            val = str(raw_val or "").strip().lower()
            if key and val:
                out[key] = val
        return out

    @field_validator("skip_slide_types")
    @classmethod
    def normalize_skip_types(cls, value: List[str]) -> List[str]:
        return _normalize_key_list(value)


class QualityOrchestrationPolicy(BaseModel):
    require_image_anchor: bool = False
    dense_layout_remap: DenseLayoutRemapPolicy = Field(default_factory=DenseLayoutRemapPolicy)
    prevent_adjacent_layout_repeat: bool = True
    family_convergence: FamilyConvergencePolicy = Field(default_factory=FamilyConvergencePolicy)
