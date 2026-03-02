"""
Skill Selector - Intelligent skill selection based on requirements and performance.
"""

import os
import logging
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from .models import Skill, SkillCategory, UserPreferences, Pipeline

if TYPE_CHECKING:
    from .registry import SkillsRegistry

logger = logging.getLogger("skills.selector")

# Global singleton
_skill_selector: Optional["SkillSelector"] = None


class SkillSelector:
    """
    Intelligent skill selection based on requirements and historical performance.

    Scores skills using a weighted combination of:
    - Quality score (user ratings + auto-scoring)
    - Speed (inverse of latency)
    - Cost (inverse of cost per execution)
    - Reliability (success rate)
    """

    def __init__(self, registry: "SkillsRegistry"):
        """
        Initialize the selector.

        Args:
            registry: SkillsRegistry for skill lookup
        """
        self.registry = registry

    async def select_skill(
        self,
        category: SkillCategory,
        requirements: Dict[str, Any],
        user_preferences: Optional[UserPreferences] = None,
        exclude_skills: Optional[List[str]] = None,
    ) -> Optional[Skill]:
        """
        Select the best skill for the given category and requirements.

        Args:
            category: Type of skill needed (t2i, i2v, etc.)
            requirements: Task-specific requirements (duration, orientation, etc.)
            user_preferences: Optional user preference weights
            exclude_skills: Skills to skip (e.g., after failure)

        Returns:
            Best matching Skill or None
        """
        exclude_skills = exclude_skills or []

        # Get candidate skills
        candidates = self.registry.get_skills_by_category(category)
        candidates = [s for s in candidates if s.name not in exclude_skills]
        candidates = [s for s in candidates if s.is_enabled]

        # Filter by user blocks
        if user_preferences:
            candidates = [s for s in candidates if s.name not in user_preferences.blocked_skills]

            # Check if user has explicit preference for this category
            preferred = user_preferences.preferred_skills.get(category.value, [])
            if preferred:
                preferred_candidates = [s for s in candidates if s.name in preferred]
                if preferred_candidates:
                    candidates = preferred_candidates

        if not candidates:
            logger.warning(f"No available skills for category: {category.value}")
            return None

        # Filter by capability requirements
        candidates = self._filter_by_requirements(candidates, requirements)

        if not candidates:
            logger.warning(f"No skills meet requirements for {category.value}: {requirements}")
            return None

        # Score and rank
        scored = [(s, self._score_skill(s, requirements, user_preferences)) for s in candidates]
        scored.sort(key=lambda x: (-x[1], x[0].priority))  # Higher score first, then priority

        selected = scored[0][0]
        logger.info(
            f"[SkillSelector] Selected skill: {selected.name} "
            f"(score: {scored[0][1]:.3f}, priority: {selected.priority})"
        )

        # Log other candidates for debugging
        if len(scored) > 1:
            others = ", ".join([f"{s.name}:{score:.3f}" for s, score in scored[1:4]])
            logger.debug(f"[SkillSelector] Other candidates: {others}")

        return selected

    def _filter_by_requirements(
        self,
        skills: List[Skill],
        requirements: Dict[str, Any],
    ) -> List[Skill]:
        """Filter skills by hard requirements."""
        result = []

        for skill in skills:
            if skill.matches_requirements(requirements):
                result.append(skill)
            else:
                logger.debug(f"[SkillSelector] Filtered out skill {skill.name}: requirements mismatch")

        return result

    def _score_skill(
        self,
        skill: Skill,
        requirements: Dict[str, Any],
        preferences: Optional[UserPreferences] = None,
    ) -> float:
        """
        Calculate a composite score for skill ranking.
        Higher score = better match.

        Score = (quality_weight * quality) + (speed_weight * speed) +
                (cost_weight * cost_inv) + (reliability_weight * reliability)
        """
        metrics = skill.metrics

        # Load default weights from config
        try:
            from configs.settings import get_config
            config = get_config()
            quality_weight = config.skills.quality_weight
            speed_weight = config.skills.speed_weight
            cost_weight = config.skills.cost_weight
            reliability_weight = config.skills.reliability_weight
            max_latency = config.skills.max_latency_ms
            max_cost = config.skills.max_cost_per_execution
        except ImportError:
            # Fallback to hardcoded defaults
            quality_weight = 0.40
            speed_weight = 0.30
            cost_weight = 0.20
            reliability_weight = 0.10
            max_latency = 300000
            max_cost = 1.0

        if preferences:
            quality_weight = preferences.quality_weight
            speed_weight = preferences.speed_weight
            cost_weight = preferences.cost_weight
            # Reliability gets the remaining weight
            reliability_weight = max(0, 1.0 - quality_weight - speed_weight - cost_weight)

        # Normalize scores to 0-1 range

        # Quality: direct from metrics
        quality_score = min(1.0, max(0.0, metrics.quality_score))

        # Speed: inverse of latency, normalized
        speed_score = max(0, 1 - (metrics.avg_latency_ms / max_latency))

        # Cost: inverse, normalized
        cost_score = max(0, 1 - (metrics.cost_per_execution / max_cost))

        # Reliability: direct from metrics
        reliability_score = min(1.0, max(0.0, metrics.reliability_score))

        # Calculate composite score
        score = (
            quality_weight * quality_score +
            speed_weight * speed_score +
            cost_weight * cost_score +
            reliability_weight * reliability_score
        )

        logger.debug(
            f"[SkillSelector] Score for {skill.name}: "
            f"quality={quality_score:.2f}*{quality_weight:.2f}, "
            f"speed={speed_score:.2f}*{speed_weight:.2f}, "
            f"cost={cost_score:.2f}*{cost_weight:.2f}, "
            f"reliability={reliability_score:.2f}*{reliability_weight:.2f} "
            f"= {score:.3f}"
        )

        return score

    async def select_pipeline(
        self,
        requirements: Dict[str, Any],
        user_preferences: Optional[UserPreferences] = None,
        exclude_pipelines: Optional[List[str]] = None,
    ) -> Optional[Pipeline]:
        """
        Select the best pipeline for the given requirements.

        A pipeline bundles co-dependent T2I + I2V skills. This method ensures
        that when a video generation pipeline is selected, the paired image
        generation skill is also locked in — preventing cross-pipeline mixing.

        Args:
            requirements: Task-specific requirements (duration, orientation, etc.)
            user_preferences: Optional user preference weights
            exclude_pipelines: Pipeline names to skip (e.g., after failure)

        Returns:
            Best matching Pipeline or None
        """
        exclude_pipelines = exclude_pipelines or []

        # Get all enabled pipelines
        pipelines = self.registry.get_enabled_pipelines()
        pipelines = [p for p in pipelines if p.name not in exclude_pipelines]

        if not pipelines:
            logger.warning("[SkillSelector] No enabled pipelines available")
            return None

        # Score each pipeline based on its I2V skill (primary capability)
        scored: List[tuple] = []
        for pipeline in pipelines:
            # Resolve the I2V skill to check capabilities
            i2v_skill = self.registry.get_skill(pipeline.i2v_skill_name) if pipeline.i2v_skill_name else None
            if not i2v_skill or not i2v_skill.is_enabled:
                logger.debug(f"[SkillSelector] Pipeline {pipeline.name}: I2V skill missing or disabled")
                continue

            # Check if I2V skill meets requirements
            if not i2v_skill.matches_requirements(requirements):
                logger.debug(f"[SkillSelector] Pipeline {pipeline.name}: I2V skill doesn't match requirements")
                continue

            # Also verify the T2I skill exists and is enabled
            t2i_skill = self.registry.get_skill(pipeline.t2i_skill_name) if pipeline.t2i_skill_name else None
            if not t2i_skill or not t2i_skill.is_enabled:
                logger.debug(f"[SkillSelector] Pipeline {pipeline.name}: T2I skill missing or disabled")
                continue

            # Score based on I2V skill quality
            score = self._score_skill(i2v_skill, requirements, user_preferences)
            scored.append((pipeline, score))

        if not scored:
            logger.warning("[SkillSelector] No pipelines match requirements")
            return None

        # Sort by score (descending) then priority (ascending)
        scored.sort(key=lambda x: (-x[1], x[0].priority))

        selected = scored[0][0]
        logger.info(
            f"[SkillSelector] Selected pipeline: {selected.name} "
            f"(score: {scored[0][1]:.3f}, priority: {selected.priority}, "
            f"t2i={selected.t2i_skill_name}, i2v={selected.i2v_skill_name})"
        )

        if len(scored) > 1:
            others = ", ".join([f"{p.name}:{s:.3f}" for p, s in scored[1:4]])
            logger.debug(f"[SkillSelector] Other pipeline candidates: {others}")

        return selected

    async def select_pipeline_with_fallback(
        self,
        requirements: Dict[str, Any],
        user_preferences: Optional[UserPreferences] = None,
        max_fallbacks: int = 3,
    ) -> List[Pipeline]:
        """
        Select primary pipeline and fallback options.

        Args:
            requirements: Task requirements
            user_preferences: User preferences
            max_fallbacks: Maximum number of pipelines to return

        Returns:
            Ordered list of pipelines to try (best first)
        """
        selected = []
        excluded = []

        for _ in range(max_fallbacks):
            pipeline = await self.select_pipeline(
                requirements=requirements,
                user_preferences=user_preferences,
                exclude_pipelines=excluded,
            )

            if pipeline:
                selected.append(pipeline)
                excluded.append(pipeline.name)
            else:
                break

        if selected:
            logger.info(
                f"[SkillSelector] Selected pipeline chain: "
                f"{[p.name for p in selected]}"
            )
        else:
            logger.warning("[SkillSelector] No pipelines available")

        return selected

    async def select_with_fallback(
        self,
        category: SkillCategory,
        requirements: Dict[str, Any],
        user_preferences: Optional[UserPreferences] = None,
        max_fallbacks: int = 3,
    ) -> List[Skill]:
        """
        Select primary skill and fallback options.

        Args:
            category: Skill category
            requirements: Task requirements
            user_preferences: User preferences
            max_fallbacks: Maximum number of skills to return

        Returns:
            Ordered list of skills to try (best first)
        """
        selected = []
        excluded = []

        for _ in range(max_fallbacks):
            skill = await self.select_skill(
                category=category,
                requirements=requirements,
                user_preferences=user_preferences,
                exclude_skills=excluded,
            )

            if skill:
                selected.append(skill)
                excluded.append(skill.name)
            else:
                break

        if selected:
            logger.info(
                f"[SkillSelector] Selected skill chain for {category.value}: "
                f"{[s.name for s in selected]}"
            )
        else:
            logger.warning(f"[SkillSelector] No skills available for {category.value}")

        return selected

    async def get_user_preferences(self, user_id: str) -> UserPreferences:
        """
        Load user preferences from database.

        Args:
            user_id: User identifier

        Returns:
            UserPreferences (default if not found)
        """
        if self.registry.supabase:
            try:
                result = self.registry.supabase.table("autoviralvid_user_skill_preferences") \
                    .select("*") \
                    .eq("user_id", user_id) \
                    .limit(1) \
                    .execute()

                if result.data and len(result.data) > 0:
                    return UserPreferences.from_db_row(result.data[0])
            except Exception as e:
                logger.warning(f"Failed to load user preferences: {e}")

        return UserPreferences.default(user_id)


async def get_skill_selector() -> SkillSelector:
    """
    Get the global SkillSelector singleton.

    Creates and initializes the selector if not already done.
    """
    global _skill_selector

    if _skill_selector is None:
        from .registry import get_skills_registry
        registry = await get_skills_registry()
        _skill_selector = SkillSelector(registry)

    return _skill_selector


def reset_skill_selector() -> None:
    """Reset the global selector (for testing)."""
    global _skill_selector
    _skill_selector = None
