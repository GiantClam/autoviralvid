"""
Skills Registry - Central registry for skill discovery and management.
"""

import os
import asyncio
import logging
from typing import Dict, List, Optional, Type, TYPE_CHECKING

from .models import (
    Skill,
    SkillCategory,
    SkillProvider,
    SkillCapabilities,
    SkillMetrics,
    Pipeline,
)
from .base import SkillAdapter, BaseSkillAdapter

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger("skills.registry")

# Global singleton instance
_skills_registry: Optional["SkillsRegistry"] = None
_registry_lock: asyncio.Lock = asyncio.Lock()


class SkillsRegistry:
    """
    Central registry for all available skills.

    Supports:
    - Loading skills from Supabase database
    - Registering skills programmatically
    - Legacy provider compatibility
    - Skill lookup and filtering
    """

    def __init__(self, supabase: Optional["Client"] = None):
        """
        Initialize the registry.

        Args:
            supabase: Optional Supabase client for database operations
        """
        self.supabase = supabase
        self._skills_cache: Dict[str, Skill] = {}
        self._pipelines_cache: Dict[str, Pipeline] = {}
        self._adapter_classes: Dict[str, Type[BaseSkillAdapter]] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the registry by loading skills from database and registering built-ins.

        This method is idempotent - calling it multiple times has no effect.
        """
        if self._initialized:
            return

        # Register built-in adapter classes
        self._register_builtin_adapters()

        # Load skills from database
        if self.supabase:
            await self._load_from_database()

        # Register legacy skills for backward compatibility
        self._register_legacy_skills()

        # Load pipelines from YAML config (preferred, declarative)
        self._load_pipelines_from_yaml()

        # Register pipelines (hardcoded fallback, after skills are loaded)
        self._register_pipelines()

        self._initialized = True
        logger.info(
            f"Skills registry initialized with {len(self._skills_cache)} skills "
            f"and {len(self._pipelines_cache)} pipelines"
        )

    def _register_builtin_adapters(self) -> None:
        """Register adapter classes for each provider."""
        # Import adapters here to avoid circular imports
        try:
            from .adapters.runninghub import RunningHubAdapter
            self._adapter_classes["runninghub"] = RunningHubAdapter
        except ImportError as e:
            logger.warning(f"Failed to import RunningHubAdapter: {e}")

        # Mock-like adapters are intentionally disabled in all environments.

        logger.debug(f"Registered {len(self._adapter_classes)} adapter classes")

    async def _load_from_database(self) -> None:
        """Load skill definitions from Supabase."""
        if not self.supabase:
            return

        try:
            result = self.supabase.table("autoviralvid_skills") \
                .select("*") \
                .eq("is_enabled", True) \
                .order("priority") \
                .execute()

            for row in result.data or []:
                try:
                    skill = Skill.from_db_row(row)
                    if skill.provider in {SkillProvider.MOCK, SkillProvider.SEEDANCE}:
                        logger.info(f"Skipping mock-like DB skill: {skill.name}")
                        continue
                    self._skills_cache[skill.name] = skill
                    logger.debug(f"Loaded skill: {skill.name} ({skill.category.value})")
                except Exception as e:
                    logger.error(f"Failed to load skill from row: {e}")

            logger.info(f"Loaded {len(result.data or [])} skills from database")

        except Exception as e:
            logger.error(f"Failed to load skills from database: {e}")

    def _register_legacy_skills(self) -> None:
        """
        Register skills from current provider configuration for backward compatibility.

        This ensures existing workflows continue to work even if database is empty.
        """
        # RunningHub Sora2
        if os.getenv("RUNNINGHUB_API_KEY"):
            workflow_id = os.getenv("RUNNINGHUB_SORA2_WORKFLOW_ID", "1985261217524629506")
            self._skills_cache.setdefault("runninghub_sora2_i2v", Skill(
                id="legacy_runninghub_sora2",
                name="runninghub_sora2_i2v",
                display_name="RunningHub Sora2 Video",
                category=SkillCategory.I2V,
                provider=SkillProvider.RUNNINGHUB,
                workflow_id=workflow_id,
                node_mappings={
                    "prompt": {"nodeId": "41", "fieldName": "prompt"},
                    "image": {"nodeId": "40", "fieldName": "image"}
                },
                capabilities=SkillCapabilities(
                    max_duration=10,
                    min_duration=5,
                    orientations=["landscape", "portrait"],
                    supports_image_ref=True,
                    supports_audio=True,
                ),
                requires_upload=True,
                priority=10,
                description="Legacy RunningHub Sora2 skill",
                tags=["video", "sora2", "legacy"],
                pipeline="sora2",  # Bundled with runninghub_qwen_t2i
            ))
            logger.debug("Registered legacy skill: runninghub_sora2_i2v")

        # RunningHub Image (Qwen)
        image_workflow_id = os.getenv("RUNNINGHUB_IMAGE_WORKFLOW_ID") or os.getenv("RUNNINGHUB_WORKFLOW_ID")
        if os.getenv("RUNNINGHUB_API_KEY") and image_workflow_id:
            self._skills_cache.setdefault("runninghub_qwen_t2i", Skill(
                id="legacy_runninghub_qwen",
                name="runninghub_qwen_t2i",
                display_name="RunningHub Qwen Image",
                category=SkillCategory.T2I,
                provider=SkillProvider.RUNNINGHUB,
                workflow_id=image_workflow_id,
                node_mappings={
                    "prompt": {"nodeId": "3", "fieldName": "text"},
                    "image": {"nodeId": "21", "fieldName": "image"}
                },
                capabilities=SkillCapabilities(
                    supports_image_ref=True,
                ),
                requires_upload=True,
                priority=10,
                description="Legacy RunningHub Qwen image skill",
                tags=["image", "qwen", "legacy"],
                pipeline="sora2",  # Bundled with runninghub_sora2_i2v
            ))
            logger.debug("Registered legacy skill: runninghub_qwen_t2i")

        # --- Qwen Product Pipeline ---
        # T2I: Qwen+NextScene Storyboard (batch image generation)
        qwen_storyboard_workflow_id = os.getenv(
            "RUNNINGHUB_QWEN_STORYBOARD_WORKFLOW_ID", "2021433434782044162"
        )
        if os.getenv("RUNNINGHUB_API_KEY") and qwen_storyboard_workflow_id:
            self._skills_cache.setdefault("runninghub_qwen_storyboard_t2i", Skill(
                id="legacy_runninghub_qwen_storyboard",
                name="runninghub_qwen_storyboard_t2i",
                display_name="RunningHub Qwen Storyboard Images",
                category=SkillCategory.T2I,
                provider=SkillProvider.RUNNINGHUB,
                workflow_id=qwen_storyboard_workflow_id,
                node_mappings={
                    "image": {"nodeId": "74", "fieldName": "image"},
                    "prompt": {"nodeId": "103", "fieldName": "text"},
                },
                capabilities=SkillCapabilities(
                    supports_image_ref=True,
                    supports_batch_output=True,
                    output_formats=["png", "jpg", "txt"],
                ),
                requires_upload=True,
                priority=15,
                description="Legacy RunningHub Qwen storyboard T2I skill (qwen_product pipeline)",
                tags=["image", "qwen", "storyboard", "batch", "product", "legacy"],
                pipeline="qwen_product",
            ))
            logger.debug("Registered legacy skill: runninghub_qwen_storyboard_t2i")

        # I2V: Qwen first+last frame video generation
        qwen_fl_workflow_id = os.getenv(
            "RUNNINGHUB_QWEN_FL_WORKFLOW_ID", "2019403401959837698"
        )
        if os.getenv("RUNNINGHUB_API_KEY") and qwen_fl_workflow_id:
            self._skills_cache.setdefault("runninghub_qwen_fl_i2v", Skill(
                id="legacy_runninghub_qwen_fl",
                name="runninghub_qwen_fl_i2v",
                display_name="RunningHub Qwen First/Last Frame Video",
                category=SkillCategory.I2V,
                provider=SkillProvider.RUNNINGHUB,
                workflow_id=qwen_fl_workflow_id,
                node_mappings={
                    "first_frame": {"nodeId": "48", "fieldName": "image"},
                    "last_frame": {"nodeId": "49", "fieldName": "image"},
                    "prompt": {"nodeId": "34", "fieldName": "text"},
                    "width": {"nodeId": "30", "fieldName": "width", "default": 720},
                    "height": {"nodeId": "29", "fieldName": "height", "default": 1280},
                    "duration": {"nodeId": "56", "fieldName": "num_frames", "default": 5},
                },
                capabilities=SkillCapabilities(
                    max_duration=10,
                    min_duration=3,
                    orientations=["landscape", "portrait"],
                    supports_image_ref=True,
                    supports_first_last_frame=True,
                    supports_custom_resolution=True,
                    default_width=720,
                    default_height=1280,
                ),
                requires_upload=True,
                priority=15,
                description="Legacy RunningHub Qwen first+last frame I2V skill (qwen_product pipeline)",
                tags=["video", "qwen", "first-last-frame", "product", "legacy"],
                pipeline="qwen_product",
            ))
            logger.debug("Registered legacy skill: runninghub_qwen_fl_i2v")
    def _load_pipelines_from_yaml(self) -> None:
        """
        Load pipeline and skill definitions from skills.yaml.
        
        This is the preferred, declarative way to register pipelines.
        The YAML file is the source of truth for pipeline configurations.
        """
        import yaml
        yaml_path = os.path.join(os.path.dirname(__file__), "..", "configs", "skills.yaml")
        if not os.path.exists(yaml_path):
            logger.debug("skills.yaml not found, skipping YAML pipeline loading")
            return

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load skills.yaml: {e}")
            return

        # Load skills from YAML
        for skill_def in config.get("skills", []):
            name = skill_def.get("name")
            if not name or name in self._skills_cache:
                continue  # Skip if already loaded (from DB or legacy)
            if skill_def.get("is_enabled") is False:
                continue  # Skip disabled skills

            try:
                # Map provider string to enum
                provider_str = skill_def.get("provider", "runninghub")
                provider = SkillProvider.RUNNINGHUB  # default
                for p in SkillProvider:
                    if p.value == provider_str:
                        provider = p
                        break

                if provider in {SkillProvider.MOCK, SkillProvider.SEEDANCE}:
                    logger.info(f"Skipping mock-like YAML skill: {name}")
                    continue

                # Map category string to enum
                category_str = skill_def.get("category", "i2v")
                category = SkillCategory.I2V  # default
                for c in SkillCategory:
                    if c.value == category_str:
                        category = c
                        break

                caps_dict = skill_def.get("capabilities", {})
                skill = Skill(
                    id=f"yaml_{name}",
                    name=name,
                    display_name=skill_def.get("display_name", name),
                    category=category,
                    provider=provider,
                    workflow_id=skill_def.get("workflow_id"),
                    node_mappings=skill_def.get("node_mappings", {}),
                    capabilities=SkillCapabilities(
                        max_duration=caps_dict.get("max_duration", 10),
                        min_duration=caps_dict.get("min_duration", 3),
                        orientations=caps_dict.get("orientations", ["landscape", "portrait"]),
                        supports_image_ref=caps_dict.get("supports_image_ref", False),
                        supports_audio=caps_dict.get("supports_audio", False),
                        supports_batch_output=caps_dict.get("supports_batch_output", False),
                        supports_first_last_frame=caps_dict.get("supports_first_last_frame", False),
                        supports_custom_resolution=caps_dict.get("supports_custom_resolution", False),
                    ),
                    requires_upload=skill_def.get("requires_upload", False),
                    priority=skill_def.get("priority", 50),
                    description=skill_def.get("description", ""),
                    tags=skill_def.get("tags", []),
                    pipeline=skill_def.get("pipeline"),
                )
                self._skills_cache[name] = skill
                logger.debug(f"Loaded skill from YAML: {name}")
            except Exception as e:
                logger.warning(f"Failed to load skill '{name}' from YAML: {e}")

        # Load pipelines from YAML
        for pipe_def in config.get("pipelines", []):
            name = pipe_def.get("name")
            if not name or name in self._pipelines_cache:
                continue

            t2i_name = pipe_def.get("t2i_skill")
            i2v_name = pipe_def.get("i2v_skill")
            is_enabled = pipe_def.get("is_enabled", True)

            # If pipeline is enabled, verify its skills exist
            if is_enabled and t2i_name and i2v_name:
                if t2i_name not in self._skills_cache or i2v_name not in self._skills_cache:
                    logger.debug(
                        f"Pipeline '{name}' skipped: missing skills "
                        f"(t2i={t2i_name in self._skills_cache}, i2v={i2v_name in self._skills_cache})"
                    )
                    continue

            pipeline = Pipeline(
                name=name,
                display_name=pipe_def.get("display_name", name),
                description=pipe_def.get("description", ""),
                t2i_skill_name=t2i_name,
                i2v_skill_name=i2v_name,
                is_enabled=is_enabled,
                priority=pipe_def.get("priority", 50),
                tags=pipe_def.get("tags", []),
                suitable_for=pipe_def.get("suitable_for", []),
            )
            self._pipelines_cache[name] = pipeline
            logger.info(f"Loaded pipeline from YAML: {name} (enabled={is_enabled})")

        yaml_pipeline_count = len([p for p in config.get("pipelines", [])])
        logger.info(f"YAML loading complete: processed {yaml_pipeline_count} pipeline definitions")

    def _register_pipelines(self) -> None:
        """
        Register pipelines that bundle co-dependent skills (hardcoded fallback).

        A pipeline guarantees that its T2I and I2V skills are always used
        together. This prevents, for example, a future non-sora2 video model
        from accidentally referencing the sora2-specific image generation skill.
        """
        # Sora2 Pipeline: Qwen T2I + Sora2 I2V (must be used together)
        if (self._skills_cache.get("runninghub_qwen_t2i")
                and self._skills_cache.get("runninghub_sora2_i2v")):
            self._pipelines_cache.setdefault("sora2", Pipeline(
                name="sora2",
                display_name="Sora2 Pipeline (Qwen Image + Sora2 Video)",
                description=(
                    "End-to-end Sora2 generation pipeline. "
                    "Uses Qwen for image/storyboard generation and Sora2 for video generation. "
                    "Both skills are intended to be used together."
                ),
                t2i_skill_name="runninghub_qwen_t2i",
                i2v_skill_name="runninghub_sora2_i2v",
                is_enabled=True,
                priority=10,
                tags=["sora2", "runninghub", "production"],
            ))
            logger.debug("Registered pipeline: sora2")

        # Qwen Product Pipeline: Qwen Storyboard T2I + Qwen First/Last Frame I2V
        if (self._skills_cache.get("runninghub_qwen_storyboard_t2i")
                and self._skills_cache.get("runninghub_qwen_fl_i2v")):
            self._pipelines_cache.setdefault("qwen_product", Pipeline(
                name="qwen_product",
                display_name="Qwen Product Showcase Pipeline",
                description=(
                    "Product showcase pipeline. "
                    "Uses Qwen+NextScene to generate storyboard images and prompts, "
                    "then composes adjacent images into first/last-frame video clips."
                ),
                t2i_skill_name="runninghub_qwen_storyboard_t2i",
                i2v_skill_name="runninghub_qwen_fl_i2v",
                is_enabled=True,
                priority=15,
                tags=["qwen", "product", "runninghub", "production"],
            ))
            logger.debug("Registered pipeline: qwen_product")

        # Future: register additional pipelines here
        # e.g. wan21 pipeline, seedance pipeline, etc.

        logger.info(f"Registered {len(self._pipelines_cache)} pipelines")

    # Pipeline Query Methods

    def get_pipeline(self, name: str) -> Optional[Pipeline]:
        """Get a pipeline by name."""
        return self._pipelines_cache.get(name)

    def get_enabled_pipelines(self) -> List[Pipeline]:
        """Get all enabled pipelines, ordered by priority."""
        pipelines = [p for p in self._pipelines_cache.values() if p.is_enabled]
        return sorted(pipelines, key=lambda p: p.priority)

    def get_pipeline_for_skill(self, skill_name: str) -> Optional[Pipeline]:
        """
        Find the pipeline that contains a given skill.

        Returns None if the skill is not part of any pipeline.
        """
        for pipeline in self._pipelines_cache.values():
            if skill_name in pipeline.get_skill_names():
                return pipeline
        return None

    def resolve_pipeline_skills(self, pipeline_name: str) -> Dict[str, Optional[Skill]]:
        """
        Resolve a pipeline's skill names to actual Skill objects.

        Returns a dict like:
            {"t2i": <Skill>, "i2v": <Skill>, "t2v": None, "audio": None}
        """
        pipeline = self.get_pipeline(pipeline_name)
        if not pipeline:
            return {"t2i": None, "i2v": None, "t2v": None, "audio": None}

        return {
            "t2i": self.get_skill(pipeline.t2i_skill_name) if pipeline.t2i_skill_name else None,
            "i2v": self.get_skill(pipeline.i2v_skill_name) if pipeline.i2v_skill_name else None,
            "t2v": self.get_skill(pipeline.t2v_skill_name) if pipeline.t2v_skill_name else None,
            "audio": self.get_skill(pipeline.audio_skill_name) if pipeline.audio_skill_name else None,
        }

    def register_pipeline(self, pipeline: Pipeline) -> None:
        """Register or update a pipeline."""
        self._pipelines_cache[pipeline.name] = pipeline
        logger.info(f"Registered pipeline: {pipeline.name}")

    # Query Methods

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills_cache.get(name)

    def get_skill_by_id(self, skill_id: str) -> Optional[Skill]:
        """Get a skill by ID."""
        for skill in self._skills_cache.values():
            if skill.id == skill_id:
                return skill
        return None

    def get_skills_by_category(self, category: SkillCategory) -> List[Skill]:
        """Get all skills in a category, ordered by priority."""
        skills = [s for s in self._skills_cache.values() if s.category == category]
        return sorted(skills, key=lambda s: s.priority)

    def get_skills_by_provider(self, provider: SkillProvider) -> List[Skill]:
        """Get all skills from a provider."""
        return [s for s in self._skills_cache.values() if s.provider == provider]

    def get_pipeline_skill(self, pipeline: str, category: SkillCategory) -> Optional[Skill]:
        """
        Get a skill from a named pipeline by category.
        
        Used to resolve companion skills - e.g., when an I2V skill from pipeline
        'sora2' is selected, this finds the co-dependent T2I skill in the same pipeline.
        """
        for s in self._skills_cache.values():
            if s.pipeline == pipeline and s.category == category and s.is_enabled:
                return s
        return None

    def get_enabled_skills(self) -> List[Skill]:
        """Get all enabled skills, ordered by priority."""
        skills = [s for s in self._skills_cache.values() if s.is_enabled]
        return sorted(skills, key=lambda s: s.priority)

    def list_all_skills(self) -> List[Skill]:
        """Get all registered skills."""
        return list(self._skills_cache.values())

    def get_adapter_class(self, provider: SkillProvider) -> Optional[Type[BaseSkillAdapter]]:
        """Get the adapter class for a provider."""
        return self._adapter_classes.get(provider.value)

    def create_adapter(self, skill: Skill) -> Optional[BaseSkillAdapter]:
        """Create an adapter instance for a skill."""
        adapter_class = self.get_adapter_class(skill.provider)
        if adapter_class:
            return adapter_class(skill)
        logger.warning(f"No adapter class for provider: {skill.provider.value}")
        return None

    # Registration Methods

    def register_skill(self, skill: Skill) -> None:
        """Register or update a skill in the cache."""
        if skill.provider in {SkillProvider.MOCK, SkillProvider.SEEDANCE}:
            logger.warning(f"Rejecting mock-like skill registration: {skill.name}")
            return
        self._skills_cache[skill.name] = skill
        logger.info(f"Registered skill: {skill.name}")

    def register_adapter_class(
        self,
        provider: SkillProvider,
        adapter_class: Type[BaseSkillAdapter]
    ) -> None:
        """Register an adapter class for a provider."""
        if provider in {SkillProvider.MOCK, SkillProvider.SEEDANCE}:
            logger.warning(
                f"Rejecting mock-like adapter registration for provider: {provider.value}"
            )
            return
        self._adapter_classes[provider.value] = adapter_class
        logger.info(f"Registered adapter class for provider: {provider.value}")

    async def persist_skill(self, skill: Skill) -> None:
        """Save or update a skill in the database."""
        if skill.provider in {SkillProvider.MOCK, SkillProvider.SEEDANCE}:
            logger.warning(f"Rejecting persist for mock-like skill: {skill.name}")
            return
        if not self.supabase:
            logger.warning("Cannot persist skill: no Supabase client")
            return

        data = {
            "name": skill.name,
            "display_name": skill.display_name,
            "category": skill.category.value,
            "provider": skill.provider.value,
            "workflow_id": skill.workflow_id,
            "version": skill.version,
            "node_mappings": skill.node_mappings,
            "capabilities": skill.capabilities.to_dict(),
            "input_schema": skill.input_schema,
            "output_schema": skill.output_schema,
            "quality_score": skill.metrics.quality_score,
            "reliability_score": skill.metrics.reliability_score,
            "avg_latency_ms": skill.metrics.avg_latency_ms,
            "cost_per_execution": skill.metrics.cost_per_execution,
            "priority": skill.priority,
            "is_enabled": skill.is_enabled,
            "requires_upload": skill.requires_upload,
            "api_base_url": skill.api_base_url,
            "description": skill.description,
            "tags": skill.tags,
        }

        try:
            self.supabase.table("autoviralvid_skills").upsert(
                data,
                on_conflict="name"
            ).execute()
            logger.info(f"Persisted skill: {skill.name}")
        except Exception as e:
            logger.error(f"Failed to persist skill {skill.name}: {e}")

    async def update_skill_metrics(
        self,
        skill_name: str,
        quality_score: Optional[float] = None,
        reliability_score: Optional[float] = None,
        avg_latency_ms: Optional[int] = None,
    ) -> None:
        """Update metrics for a skill in both cache and database."""
        skill = self.get_skill(skill_name)
        if not skill:
            logger.warning(f"Cannot update metrics: skill not found: {skill_name}")
            return

        # Update cache
        if quality_score is not None:
            skill.metrics.quality_score = quality_score
        if reliability_score is not None:
            skill.metrics.reliability_score = reliability_score
        if avg_latency_ms is not None:
            skill.metrics.avg_latency_ms = avg_latency_ms

        # Update database
        if self.supabase:
            update_data = {}
            if quality_score is not None:
                update_data["quality_score"] = quality_score
            if reliability_score is not None:
                update_data["reliability_score"] = reliability_score
            if avg_latency_ms is not None:
                update_data["avg_latency_ms"] = avg_latency_ms

            if update_data:
                try:
                    self.supabase.table("autoviralvid_skills").update(update_data) \
                        .eq("name", skill_name) \
                        .execute()
                except Exception as e:
                    logger.error(f"Failed to update skill metrics: {e}")


async def get_skills_registry() -> SkillsRegistry:
    """
    Get the global SkillsRegistry singleton.

    Creates and initializes the registry if not already done.
    Thread-safe via asyncio.Lock.
    """
    global _skills_registry

    if _skills_registry is not None:
        return _skills_registry

    async with _registry_lock:
        # Double-check after acquiring lock
        if _skills_registry is not None:
            return _skills_registry

        # Create Supabase client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")

        supabase = None
        if supabase_url and supabase_key:
            try:
                from supabase import create_client
                supabase = create_client(supabase_url, supabase_key)
            except Exception as e:
                logger.error(f"Failed to create Supabase client: {e}")

        registry = SkillsRegistry(supabase)
        await registry.initialize()
        _skills_registry = registry

    return _skills_registry


def reset_skills_registry() -> None:
    """Reset the global registry (for testing)."""
    global _skills_registry
    _skills_registry = None

