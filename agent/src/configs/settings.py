"""
Centralized configuration settings for the video generation agent.

All configurable values are loaded from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SkillsConfig:
    """Configuration for the Skills system."""

    # Skill selection weights (must sum to 1.0)
    quality_weight: float = field(
        default_factory=lambda: float(os.getenv("SKILLS_QUALITY_WEIGHT", "0.40"))
    )
    speed_weight: float = field(
        default_factory=lambda: float(os.getenv("SKILLS_SPEED_WEIGHT", "0.30"))
    )
    cost_weight: float = field(
        default_factory=lambda: float(os.getenv("SKILLS_COST_WEIGHT", "0.20"))
    )
    reliability_weight: float = field(
        default_factory=lambda: float(os.getenv("SKILLS_RELIABILITY_WEIGHT", "0.10"))
    )

    # Scoring normalization limits
    max_latency_ms: int = field(
        default_factory=lambda: int(os.getenv("SKILLS_MAX_LATENCY_MS", "300000"))  # 5 minutes
    )
    max_cost_per_execution: float = field(
        default_factory=lambda: float(os.getenv("SKILLS_MAX_COST", "1.0"))
    )

    # Fallback chain
    max_fallbacks: int = field(
        default_factory=lambda: int(os.getenv("SKILLS_MAX_FALLBACKS", "3"))
    )


@dataclass
class VideoQueueConfig:
    """Configuration for the video task queue."""

    # Polling intervals
    poll_interval_seconds: float = field(
        default_factory=lambda: float(os.getenv("VIDEO_QUEUE_POLL_INTERVAL", "20.0"))
    )

    # Concurrency – worker-level (how many tasks the worker processes at once)
    max_concurrent_tasks: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_QUEUE_MAX_CONCURRENT", "1"))
    )

    # Global RunningHub concurrency limit (across ALL templates/workflows)
    runninghub_max_concurrent: int = field(
        default_factory=lambda: int(os.getenv("RUNNINGHUB_MAX_CONCURRENT", "3"))
    )

    # Retry settings
    max_queue_full_retries: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_QUEUE_MAX_QUEUE_RETRIES", "60"))
    )
    max_general_retries: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_QUEUE_MAX_GENERAL_RETRIES", "3"))
    )

    # Provider task polling
    provider_poll_retries: int = field(
        default_factory=lambda: int(os.getenv("VIDEO_QUEUE_PROVIDER_POLL_RETRIES", "3"))
    )


@dataclass
class WorkflowConfig:
    """Configuration for the video generation workflow."""

    # Default clip settings
    default_clip_duration: float = field(
        default_factory=lambda: float(os.getenv("WORKFLOW_CLIP_DURATION", "10.0"))
    )
    default_total_duration: float = field(
        default_factory=lambda: float(os.getenv("WORKFLOW_TOTAL_DURATION", "120.0"))
    )

    # Timeouts
    executor_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("WORKFLOW_EXECUTOR_TIMEOUT", "300"))
    )


@dataclass
class RunningHubConfig:
    """Configuration for RunningHub provider."""

    base_url: str = field(
        default_factory=lambda: os.getenv("RUNNINGHUB_API_BASE", "https://www.runninghub.cn")
    )
    api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("RUNNINGHUB_API_KEY")
    )
    timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("RUNNINGHUB_TIMEOUT", "300"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("RUNNINGHUB_MAX_RETRIES", "3"))
    )

    # Workflow IDs
    sora2_workflow_id: Optional[str] = field(
        default_factory=lambda: os.getenv("RUNNINGHUB_SORA2_WORKFLOW_ID", "1985261217524629506")
    )
    image_workflow_id: Optional[str] = field(
        default_factory=lambda: os.getenv("RUNNINGHUB_IMAGE_WORKFLOW_ID") or os.getenv("RUNNINGHUB_WORKFLOW_ID")
    )


@dataclass
class PPTPipelineConfig:
    """Configuration for PPT export/retry/render consistency behavior."""

    export_channel: str = field(
        default_factory=lambda: os.getenv("PPT_EXPORT_CHANNEL", "local")
    )
    generator_mode: str = field(
        default_factory=lambda: os.getenv("PPT_GENERATOR_MODE", "official")
    )
    allow_legacy_mode: bool = field(
        default_factory=lambda: str(os.getenv("PPT_ALLOW_LEGACY_MODE", "false")).strip().lower() not in {"0", "false", "no", "off"}
    )
    enable_legacy_fallback: bool = field(
        default_factory=lambda: str(os.getenv("PPT_ENABLE_LEGACY_FALLBACK", "false")).strip().lower() not in {"0", "false", "no", "off"}
    )
    visual_priority: bool = field(
        default_factory=lambda: str(os.getenv("PPT_VISUAL_PRIORITY", "true")).strip().lower() not in {"0", "false", "no", "off"}
    )
    visual_preset: str = field(
        default_factory=lambda: os.getenv("PPT_VISUAL_PRESET", "tech_cinematic")
    )
    visual_density: str = field(
        default_factory=lambda: os.getenv("PPT_VISUAL_DENSITY", "balanced")
    )
    retry_enabled: bool = field(
        default_factory=lambda: str(os.getenv("PPT_RETRY_ENABLED", "true")).strip().lower() not in {"0", "false", "no", "off"}
    )
    partial_retry_enabled: bool = field(
        default_factory=lambda: str(os.getenv("PPT_PARTIAL_RETRY_ENABLED", "true")).strip().lower() not in {"0", "false", "no", "off"}
    )
    retry_max_attempts: int = field(
        default_factory=lambda: int(os.getenv("PPT_RETRY_MAX_ATTEMPTS", "3"))
    )
    video_base_mode: str = field(
        default_factory=lambda: os.getenv("PPT_VIDEO_BASE_MODE", "ppt_image_slideshow")
    )


@dataclass
class AppConfig:
    """Main application configuration."""

    skills: SkillsConfig = field(default_factory=SkillsConfig)
    video_queue: VideoQueueConfig = field(default_factory=VideoQueueConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    runninghub: RunningHubConfig = field(default_factory=RunningHubConfig)
    ppt_pipeline: PPTPipelineConfig = field(default_factory=PPTPipelineConfig)

    def validate(self) -> list[str]:
        """
        Validate configuration and return list of errors.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Validate skill weights sum to ~1.0
        weights_sum = (
            self.skills.quality_weight +
            self.skills.speed_weight +
            self.skills.cost_weight +
            self.skills.reliability_weight
        )
        if abs(weights_sum - 1.0) > 0.01:
            errors.append(
                f"Skill weights must sum to 1.0 (current: {weights_sum:.2f})"
            )

        # Validate RunningHub configuration
        if not self.runninghub.api_key:
            errors.append("RUNNINGHUB_API_KEY is required")

        # Validate positive values
        if self.video_queue.poll_interval_seconds <= 0:
            errors.append("VIDEO_QUEUE_POLL_INTERVAL must be positive")

        if self.workflow.default_clip_duration <= 0:
            errors.append("WORKFLOW_CLIP_DURATION must be positive")

        if self.ppt_pipeline.retry_max_attempts < 1:
            errors.append("PPT_RETRY_MAX_ATTEMPTS must be >= 1")
        if str(self.ppt_pipeline.export_channel).strip().lower() not in {"local", "remote", "auto"}:
            errors.append("PPT_EXPORT_CHANNEL must be local, remote, or auto")
        if self.ppt_pipeline.generator_mode not in {"official", "legacy"}:
            errors.append("PPT_GENERATOR_MODE must be official or legacy")
        if self.ppt_pipeline.visual_density not in {"sparse", "balanced", "dense"}:
            errors.append("PPT_VISUAL_DENSITY must be sparse, balanced, or dense")

        return errors


# Global singleton
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration singleton."""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def validate_config() -> tuple[bool, list[str]]:
    """
    Validate the current configuration.

    Returns:
        Tuple of (is_valid, errors)
    """
    config = get_config()
    errors = config.validate()
    return len(errors) == 0, errors
