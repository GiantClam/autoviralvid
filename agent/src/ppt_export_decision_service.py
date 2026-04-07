"""Build export-time visual/design decision payload for PPT rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List


@dataclass(frozen=True)
class ExportDecisionBuildResult:
    layer1_design: Dict[str, Any]
    requested_quality_profile: str
    requested_deck_archetype_profile: str
    effective_theme_recipe: str
    effective_style_variant: str
    effective_palette_key: str
    effective_template_family: str
    effective_skill_profile: str
    effective_tone: str
    visual_seed: Dict[str, Any]
    build_meta: Dict[str, Any]


class PPTExportDecisionService:
    """Service that computes the design/visual seed for export pipeline."""

    async def build_decision(
        self,
        *,
        req: Any,
        slides_data: List[dict[str, Any]],
        requested_execution_profile: str,
        requested_force_ppt_master: bool,
        dev_fast_fail: bool,
        run_layer1_design_skill_chain: Callable[..., Dict[str, Any]],
        resolve_quality_profile_id: Callable[..., str],
        derive_deck_archetype_profile: Callable[..., str],
        canonicalize_pipeline_palette: Callable[..., str],
        default_palette_for_archetype: Callable[..., str],
        apply_skill_planning_to_render_payload: Callable[..., Dict[str, Any]],
        apply_visual_orchestration: Callable[[Dict[str, Any]], Dict[str, Any]],
        hydrate_image_assets: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
        collect_image_asset_issues: Callable[[Dict[str, Any]], List[str]],
    ) -> ExportDecisionBuildResult:
        layer1_design = run_layer1_design_skill_chain(
            deck_title=req.title,
            slides=slides_data,
            requested_style_variant=req.minimax_style_variant,
            requested_palette_key=req.minimax_palette_key,
            requested_theme_recipe=req.theme_recipe,
            requested_tone=req.tone,
            context_parts=[req.author, req.retry_hint],
            requested_template_family=req.template_family,
            requested_skill_profile=req.skill_profile,
            execution_profile=requested_execution_profile,
            force_ppt_master=requested_force_ppt_master,
        )
        requested_quality_profile = resolve_quality_profile_id(
            req.quality_profile,
            topic=req.title,
            purpose=req.retry_hint,
            audience=req.author,
            total_pages=len(slides_data),
        )
        effective_theme_recipe = str(
            layer1_design.get("theme_recipe") or req.theme_recipe or "auto"
        )
        requested_deck_archetype_profile = derive_deck_archetype_profile(
            topic=req.title,
            audience=req.author,
            purpose=req.retry_hint,
            quality_profile=requested_quality_profile,
            theme_recipe=effective_theme_recipe,
        )
        effective_style_variant = str(
            layer1_design.get("style_variant") or req.minimax_style_variant
        )
        effective_palette_key = canonicalize_pipeline_palette(
            str(
                layer1_design.get("palette_key")
                or default_palette_for_archetype(
                    requested_deck_archetype_profile,
                    str(req.minimax_palette_key or "auto"),
                )
            ),
            context_parts=[
                req.title,
                req.author,
                req.retry_hint,
                *[
                    str((slide or {}).get("title") or "")
                    for slide in slides_data[:4]
                    if isinstance(slide, dict)
                ],
            ],
            fallback="auto",
        )
        if requested_deck_archetype_profile == "education_textbook":
            effective_palette_key = "education_office_classic"
        effective_template_family = str(
            layer1_design.get("template_family") or req.template_family
        )
        effective_skill_profile = str(
            layer1_design.get("skill_profile") or req.skill_profile
        )
        effective_tone = str(layer1_design.get("tone") or req.tone or "auto").strip().lower()
        if effective_tone not in {"auto", "light", "dark"}:
            effective_tone = "auto"

        visual_seed = await hydrate_image_assets(
            apply_visual_orchestration(
                apply_skill_planning_to_render_payload(
                    {
                        "title": req.title,
                        "theme": {
                            "palette": effective_palette_key,
                            "style": effective_style_variant,
                            "theme_recipe": effective_theme_recipe,
                            "tone": effective_tone,
                        },
                        "theme_recipe": effective_theme_recipe,
                        "tone": effective_tone,
                        "slides": slides_data,
                        "template_family": effective_template_family,
                        "template_id": (
                            effective_template_family
                            if effective_template_family != "auto"
                            else ""
                        ),
                        "skill_profile": effective_skill_profile,
                        "hardness_profile": req.hardness_profile,
                        "schema_profile": req.schema_profile,
                        "contract_profile": req.contract_profile,
                        "quality_profile": requested_quality_profile,
                        "deck_archetype_profile": requested_deck_archetype_profile,
                        "svg_mode": req.svg_mode,
                        "execution_profile": requested_execution_profile,
                    },
                    execution_profile=requested_execution_profile,
                    force_ppt_master=requested_force_ppt_master,
                )
            )
        )

        build_meta: Dict[str, Any] = {
            "decision_source": "layer1+skill_planning",
            "requested_quality_profile": requested_quality_profile,
            "style_variant": effective_style_variant,
            "palette_key": effective_palette_key,
            "theme_recipe": effective_theme_recipe,
            "tone": effective_tone,
            "template_family": effective_template_family,
        }
        if dev_fast_fail and not str(req.template_file_url or "").strip():
            image_issues = collect_image_asset_issues(visual_seed)
            if image_issues:
                build_meta["image_asset_issues"] = image_issues[:8]

        return ExportDecisionBuildResult(
            layer1_design=dict(layer1_design or {}),
            requested_quality_profile=requested_quality_profile,
            requested_deck_archetype_profile=requested_deck_archetype_profile,
            effective_theme_recipe=effective_theme_recipe,
            effective_style_variant=effective_style_variant,
            effective_palette_key=effective_palette_key,
            effective_template_family=effective_template_family,
            effective_skill_profile=effective_skill_profile,
            effective_tone=effective_tone,
            visual_seed=dict(visual_seed or {}),
            build_meta=build_meta,
        )

