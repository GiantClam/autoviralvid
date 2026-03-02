"""
Skills Data Models - Core data structures for the Skills system.
"""

from typing import Dict, Any, Optional, List, Literal
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class SkillCategory(str, Enum):
    """Categories of skills available in the system."""
    T2I = "t2i"             # Text-to-Image
    I2V = "i2v"             # Image-to-Video
    T2V = "t2v"             # Text-to-Video
    VIDEO_EDIT = "video_edit"  # Video editing (transitions, effects)
    AUDIO = "audio"         # Audio generation (voice, BGM)
    AVATAR = "avatar"       # Digital human synthesis


class SkillProvider(str, Enum):
    """Supported skill providers."""
    RUNNINGHUB = "runninghub"
    SEEDANCE = "seedance"
    MOCK = "mock"


@dataclass
class SkillCapabilities:
    """
    Capabilities and constraints of a skill.
    Used for filtering skills based on task requirements.
    """
    max_duration: int = 10
    min_duration: int = 5
    orientations: List[str] = field(default_factory=lambda: ["landscape", "portrait"])
    supports_image_ref: bool = True
    supports_audio: bool = False
    supports_first_last_frame: bool = False   # I2V: accepts first+last frame pair
    supports_custom_resolution: bool = False  # I2V: width/height configurable
    supports_batch_output: bool = False       # T2I: returns multiple images in one call
    default_width: Optional[int] = None       # Default output width (if configurable)
    default_height: Optional[int] = None      # Default output height (if configurable)
    output_formats: List[str] = field(default_factory=lambda: ["mp4"])
    resolution_options: List[str] = field(default_factory=lambda: ["1080p", "720p"])

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillCapabilities":
        """Create SkillCapabilities from a dictionary."""
        return cls(
            max_duration=data.get("max_duration", 10),
            min_duration=data.get("min_duration", 5),
            orientations=data.get("orientations", ["landscape", "portrait"]),
            supports_image_ref=data.get("supports_image_ref", True),
            supports_audio=data.get("supports_audio", False),
            supports_first_last_frame=data.get("supports_first_last_frame", False),
            supports_custom_resolution=data.get("supports_custom_resolution", False),
            supports_batch_output=data.get("supports_batch_output", False),
            default_width=data.get("default_width"),
            default_height=data.get("default_height"),
            output_formats=data.get("output_formats", ["mp4"]),
            resolution_options=data.get("resolution_options", ["1080p", "720p"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d: Dict[str, Any] = {
            "max_duration": self.max_duration,
            "min_duration": self.min_duration,
            "orientations": self.orientations,
            "supports_image_ref": self.supports_image_ref,
            "supports_audio": self.supports_audio,
            "supports_first_last_frame": self.supports_first_last_frame,
            "supports_custom_resolution": self.supports_custom_resolution,
            "supports_batch_output": self.supports_batch_output,
            "output_formats": self.output_formats,
            "resolution_options": self.resolution_options,
        }
        if self.default_width is not None:
            d["default_width"] = self.default_width
        if self.default_height is not None:
            d["default_height"] = self.default_height
        return d


@dataclass
class SkillMetrics:
    """
    Performance metrics for a skill.
    Updated from execution history for intelligent selection.
    """
    quality_score: float = 0.70      # 0.0-1.0, based on user ratings and auto-scoring
    reliability_score: float = 0.80  # 0.0-1.0, success rate
    avg_latency_ms: int = 60000      # Average execution time
    cost_per_execution: float = 0.0  # Cost in credits/currency
    total_executions: int = 0        # Total number of executions
    success_count: int = 0           # Number of successful executions

    @property
    def success_rate(self) -> float:
        """Calculate success rate from execution counts."""
        if self.total_executions == 0:
            return 0.0
        return self.success_count / self.total_executions

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillMetrics":
        """Create SkillMetrics from a dictionary."""
        return cls(
            quality_score=float(data.get("quality_score", 0.70)),
            reliability_score=float(data.get("reliability_score", 0.80)),
            avg_latency_ms=data.get("avg_latency_ms", 60000),
            cost_per_execution=float(data.get("cost_per_execution", 0.0)),
            total_executions=data.get("total_executions", 0),
            success_count=data.get("success_count", 0),
        )


@dataclass
class Skill:
    """
    A skill represents a single capability that can be executed.
    Skills are atomic units that can be composed for video generation.
    """
    id: str
    name: str
    display_name: str
    category: SkillCategory
    provider: SkillProvider
    workflow_id: Optional[str] = None
    version: str = "1.0.0"

    # Configuration
    capabilities: SkillCapabilities = field(default_factory=SkillCapabilities)
    node_mappings: Dict[str, Any] = field(default_factory=dict)
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)

    # Metrics (updated from execution history)
    metrics: SkillMetrics = field(default_factory=SkillMetrics)

    # Selection configuration
    is_enabled: bool = True
    priority: int = 100  # Lower = higher priority
    requires_upload: bool = False
    api_base_url: Optional[str] = None

    # Metadata
    description: str = ""
    tags: List[str] = field(default_factory=list)
    pipeline: Optional[str] = None  # Groups co-dependent skills (e.g., "sora2" bundles T2I+I2V)

    def __post_init__(self):
        """Ensure category and provider are enum types."""
        if isinstance(self.category, str):
            self.category = SkillCategory(self.category)
        if isinstance(self.provider, str):
            self.provider = SkillProvider(self.provider)

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "Skill":
        """Create a Skill from a database row."""
        return cls(
            id=str(row["id"]),
            name=row["name"],
            display_name=row["display_name"],
            category=SkillCategory(row["category"]),
            provider=SkillProvider(row["provider"]),
            workflow_id=row.get("workflow_id"),
            version=row.get("version", "1.0.0"),
            capabilities=SkillCapabilities.from_dict(row.get("capabilities", {})),
            node_mappings=row.get("node_mappings", {}),
            input_schema=row.get("input_schema", {}),
            output_schema=row.get("output_schema", {}),
            metrics=SkillMetrics(
                quality_score=float(row.get("quality_score", 0.7)),
                reliability_score=float(row.get("reliability_score", 0.8)),
                avg_latency_ms=row.get("avg_latency_ms", 60000),
                cost_per_execution=float(row.get("cost_per_execution", 0)),
            ),
            is_enabled=row.get("is_enabled", True),
            priority=row.get("priority", 100),
            requires_upload=row.get("requires_upload", False),
            api_base_url=row.get("api_base_url"),
            description=row.get("description", ""),
            tags=row.get("tags", []),
            pipeline=row.get("pipeline"),
        )

    def matches_requirements(self, requirements: Dict[str, Any]) -> bool:
        """Check if this skill matches the given requirements."""
        caps = self.capabilities

        # Duration check
        if "duration" in requirements:
            duration = requirements["duration"]
            if duration > caps.max_duration or duration < caps.min_duration:
                return False

        # Orientation check
        if "orientation" in requirements and requirements["orientation"]:
            orientation = requirements["orientation"].lower()
            # Normalize orientation names
            if "横" in orientation or "horizontal" in orientation:
                orientation = "landscape"
            elif "竖" in orientation or "vertical" in orientation:
                orientation = "portrait"
            if orientation not in [o.lower() for o in caps.orientations]:
                return False

        # Image reference check
        if requirements.get("requires_image") and not caps.supports_image_ref:
            return False

        # Audio check
        if requirements.get("requires_audio") and not caps.supports_audio:
            return False

        return True


@dataclass
class Pipeline:
    """
    A pipeline bundles co-dependent skills that MUST be used together.

    For example, the "sora2" pipeline requires:
    - A specific T2I skill (Qwen scene image generation) for storyboard rendering
    - A specific I2V skill (Sora2 video generation) for clip production

    These skills cannot be mixed with skills from other pipelines because
    different video models have different image requirements (resolution,
    style, face handling, etc.).
    """
    name: str                          # Pipeline identifier, e.g. "sora2"
    display_name: str                  # Human-readable name
    description: str = ""

    # Bundled skill names — resolved via SkillsRegistry at runtime
    t2i_skill_name: Optional[str] = None   # Text-to-Image skill
    i2v_skill_name: Optional[str] = None   # Image-to-Video skill
    t2v_skill_name: Optional[str] = None   # Text-to-Video skill (optional)
    audio_skill_name: Optional[str] = None # Audio skill (optional)

    # Selection metadata
    is_enabled: bool = True
    priority: int = 100      # Lower = higher priority
    tags: List[str] = field(default_factory=list)
    suitable_for: List[str] = field(default_factory=list)  # 适用场景标注

    def get_skill_names(self) -> List[str]:
        """Return all non-None skill names in this pipeline."""
        names = []
        for attr in (self.t2i_skill_name, self.i2v_skill_name,
                     self.t2v_skill_name, self.audio_skill_name):
            if attr:
                names.append(attr)
        return names


@dataclass
class SkillExecutionRequest:
    """Request to execute a skill."""
    skill_id: str
    run_id: str
    params: Dict[str, Any]  # prompt, image_url, duration, orientation, etc.
    clip_idx: Optional[int] = None
    priority: int = 0
    timeout_seconds: int = 300
    async_mode: bool = True  # Return immediately with pending status


@dataclass
class SkillExecutionResult:
    """Result of a skill execution."""
    execution_id: str
    skill_id: str
    skill_name: str
    status: Literal["pending", "submitted", "processing", "succeeded", "failed", "timeout", "cancelled"]
    task_id: Optional[str] = None  # Provider-specific task ID
    output_url: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) status."""
        return self.status in ("succeeded", "failed", "timeout", "cancelled")

    @property
    def is_success(self) -> bool:
        """Check if execution succeeded."""
        return self.status == "succeeded"


@dataclass
class UserPreferences:
    """User preferences for skill selection."""
    user_id: str
    quality_weight: float = 0.4
    speed_weight: float = 0.3
    cost_weight: float = 0.3
    preferred_skills: Dict[str, List[str]] = field(default_factory=dict)  # {"i2v": ["skill_name"]}
    blocked_skills: List[str] = field(default_factory=list)
    max_cost_per_video: Optional[float] = None
    max_latency_seconds: Optional[int] = None

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "UserPreferences":
        """Create UserPreferences from a database row."""
        return cls(
            user_id=row["user_id"],
            quality_weight=float(row.get("quality_weight", 0.4)),
            speed_weight=float(row.get("speed_weight", 0.3)),
            cost_weight=float(row.get("cost_weight", 0.3)),
            preferred_skills=row.get("preferred_skills", {}),
            blocked_skills=row.get("blocked_skills", []),
            max_cost_per_video=row.get("max_cost_per_video"),
            max_latency_seconds=row.get("max_latency_seconds"),
        )

    @classmethod
    def default(cls, user_id: str = "default") -> "UserPreferences":
        """Create default preferences."""
        return cls(user_id=user_id)
