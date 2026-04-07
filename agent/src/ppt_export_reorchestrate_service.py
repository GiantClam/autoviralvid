"""Re-orchestration service for retry slide payload updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List


@dataclass(frozen=True)
class PPTExportReorchestrateResult:
    slides: List[Dict[str, Any]]
    design_decision: Dict[str, Any]
    updated: bool


class PPTExportReorchestrateService:
    """Regenerate retry slides and keep visual critic repair metadata."""

    async def reorchestrate(
        self,
        *,
        seed_slides: List[Dict[str, Any]],
        title: str,
        effective_style_variant: str,
        effective_palette_key: str,
        effective_theme_recipe: str,
        effective_tone: str,
        effective_template_family: str,
        effective_skill_profile: str,
        requested_execution_profile: str,
        requested_force_ppt_master: bool,
        quality_profile: str,
        req_hardness_profile: Any,
        req_schema_profile: Any,
        req_contract_profile: Any,
        req_svg_mode: Any,
        route_mode: str,
        current_design_decision: Dict[str, Any],
        apply_skill_planning_to_render_payload: Callable[..., Dict[str, Any]],
        apply_visual_orchestration: Callable[[Dict[str, Any]], Dict[str, Any]],
        hydrate_image_assets: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
        normalize_design_decision_v1: Callable[[Any], Dict[str, Any]],
        build_design_decision_v1: Callable[..., Dict[str, Any]],
        freeze_retry_visual_identity: Callable[
            [List[Dict[str, Any]], Dict[str, Any]], List[Dict[str, Any]]
        ],
    ) -> PPTExportReorchestrateResult:
        repaired = await hydrate_image_assets(
            apply_visual_orchestration(
                apply_skill_planning_to_render_payload(
                    {
                        "title": title,
                        "theme": {
                            "palette": effective_palette_key,
                            "style": effective_style_variant,
                            "theme_recipe": effective_theme_recipe,
                            "tone": effective_tone,
                        },
                        "theme_recipe": effective_theme_recipe,
                        "tone": effective_tone,
                        "slides": seed_slides,
                        "template_family": effective_template_family,
                        "template_id": (
                            effective_template_family
                            if effective_template_family != "auto"
                            else ""
                        ),
                        "skill_profile": effective_skill_profile,
                        "hardness_profile": req_hardness_profile,
                        "schema_profile": req_schema_profile,
                        "contract_profile": req_contract_profile,
                        "quality_profile": quality_profile,
                        "svg_mode": req_svg_mode,
                    },
                    execution_profile=requested_execution_profile,
                    force_ppt_master=requested_force_ppt_master,
                )
            )
        )
        repaired_slides = repaired.get("slides")
        if not (isinstance(repaired_slides, list) and repaired_slides):
            return PPTExportReorchestrateResult(
                slides=seed_slides,
                design_decision=current_design_decision,
                updated=False,
            )

        critic_repair_by_slide: Dict[str, Dict[str, Any]] = {}
        for idx, raw_slide in enumerate(seed_slides):
            if not isinstance(raw_slide, dict):
                continue
            raw_visual = raw_slide.get("visual")
            critic_repair = (
                raw_visual.get("critic_repair") if isinstance(raw_visual, dict) else None
            )
            if not isinstance(critic_repair, dict) or not critic_repair:
                continue
            slide_id = str(
                raw_slide.get("slide_id") or raw_slide.get("id") or f"slide-{idx + 1}"
            ).strip()
            if slide_id:
                critic_repair_by_slide[slide_id] = dict(critic_repair)

        if critic_repair_by_slide:
            for idx, repaired_slide in enumerate(repaired_slides):
                if not isinstance(repaired_slide, dict):
                    continue
                slide_id = str(
                    repaired_slide.get("slide_id")
                    or repaired_slide.get("id")
                    or f"slide-{idx + 1}"
                ).strip()
                critic_repair = critic_repair_by_slide.get(slide_id)
                if not isinstance(critic_repair, dict):
                    continue
                visual = repaired_slide.get("visual")
                if not isinstance(visual, dict):
                    visual = {}
                    repaired_slide["visual"] = visual
                visual["critic_repair"] = dict(critic_repair)

        next_decision = normalize_design_decision_v1(
            repaired.get("design_decision_v1") or current_design_decision
        )
        if not isinstance(next_decision.get("deck"), dict) or not next_decision.get(
            "deck"
        ):
            next_decision = build_design_decision_v1(
                style_variant=effective_style_variant,
                palette_key=effective_palette_key,
                theme_recipe=effective_theme_recipe,
                tone=effective_tone,
                template_family=effective_template_family,
                quality_profile=quality_profile,
                route_mode=route_mode,
                skill_profile=effective_skill_profile,
                slides=repaired_slides,
                decision_source="retry_reorchestrate",
            )
        frozen_slides = freeze_retry_visual_identity(repaired_slides, next_decision)
        return PPTExportReorchestrateResult(
            slides=frozen_slides,
            design_decision=next_decision,
            updated=True,
        )

