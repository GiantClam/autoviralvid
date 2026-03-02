"""
Skill Adapter Base - Protocol and abstract base class for skill implementations.
"""

from typing import Protocol, Dict, Any, Optional, Tuple, runtime_checkable
from abc import ABC, abstractmethod

from .models import Skill, SkillExecutionRequest, SkillExecutionResult


@runtime_checkable
class SkillAdapter(Protocol):
    """
    Protocol defining the interface for all skill adapters.

    Each adapter wraps a specific provider (RunningHub, TokenEngine, etc.)
    and provides a unified interface for skill execution.
    """

    @property
    def skill(self) -> Skill:
        """The skill this adapter executes."""
        ...

    @property
    def skill_name(self) -> str:
        """Unique identifier for this skill."""
        ...

    async def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """
        Execute the skill with the given parameters.

        For async operations (async_mode=True in request), returns immediately
        with status="pending" or "submitted". The task_id can be used to poll
        for completion via get_status().

        Args:
            request: Execution request with params and configuration

        Returns:
            SkillExecutionResult with status and optional output_url
        """
        ...

    async def get_status(self, task_id: str) -> SkillExecutionResult:
        """
        Check the status of an async execution.

        Args:
            task_id: Provider-specific task ID from execute() result

        Returns:
            SkillExecutionResult with current status
        """
        ...

    async def validate_params(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate input parameters before execution.

        Args:
            params: Parameters to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        ...

    def estimate_cost(self, params: Dict[str, Any]) -> float:
        """
        Estimate execution cost based on parameters.

        Args:
            params: Execution parameters

        Returns:
            Estimated cost in credits/currency
        """
        ...

    def estimate_duration(self, params: Dict[str, Any]) -> int:
        """
        Estimate execution duration based on parameters.

        Args:
            params: Execution parameters

        Returns:
            Estimated duration in milliseconds
        """
        ...


class BaseSkillAdapter(ABC):
    """
    Abstract base class providing common functionality for skill adapters.

    Subclasses must implement the abstract methods for provider-specific logic.
    """

    def __init__(self, skill: Skill):
        """
        Initialize the adapter with a skill definition.

        Args:
            skill: The Skill this adapter will execute
        """
        self._skill = skill

    @property
    def skill(self) -> Skill:
        """The skill this adapter executes."""
        return self._skill

    @property
    def skill_name(self) -> str:
        """Unique identifier for this skill."""
        return self._skill.name

    @abstractmethod
    async def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """Execute the skill. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def get_status(self, task_id: str) -> SkillExecutionResult:
        """Check execution status. Must be implemented by subclasses."""
        pass

    async def validate_params(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Default parameter validation based on skill configuration.

        Can be overridden by subclasses for provider-specific validation.
        """
        node_mappings = self._skill.node_mappings

        # Check required prompt
        if "prompt" in node_mappings and not params.get("prompt"):
            return False, "Prompt is required"

        # Check image requirement
        if "image" in node_mappings and self._skill.capabilities.supports_image_ref:
            if not params.get("image_url"):
                return False, "Image URL is required for this skill"

        # Check duration
        if "duration" in params:
            duration = params["duration"]
            caps = self._skill.capabilities
            if duration < caps.min_duration:
                return False, f"Duration must be at least {caps.min_duration}s"
            if duration > caps.max_duration:
                return False, f"Duration must be at most {caps.max_duration}s"

        return True, None

    def estimate_cost(self, params: Dict[str, Any]) -> float:
        """
        Default cost estimation based on skill metrics.

        Can be overridden for more sophisticated cost calculation.
        """
        return self._skill.metrics.cost_per_execution

    def estimate_duration(self, params: Dict[str, Any]) -> int:
        """
        Default duration estimation based on skill metrics.

        Can be overridden for more sophisticated duration calculation.
        """
        base_duration = self._skill.metrics.avg_latency_ms

        # Adjust for video duration if applicable
        if "duration" in params:
            video_duration = params["duration"]
            # Longer videos typically take proportionally longer
            default_duration = 10
            scale_factor = video_duration / default_duration
            base_duration = int(base_duration * scale_factor)

        return base_duration

    def _create_result(
        self,
        request: SkillExecutionRequest,
        status: str,
        task_id: Optional[str] = None,
        output_url: Optional[str] = None,
        error: Optional[str] = None,
        error_code: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SkillExecutionResult:
        """
        Helper to create a SkillExecutionResult with common fields populated.
        """
        return SkillExecutionResult(
            execution_id=f"{request.run_id}_{request.clip_idx or 0}",
            skill_id=self._skill.id,
            skill_name=self._skill.name,
            status=status,
            task_id=task_id,
            output_url=output_url,
            error=error,
            error_code=error_code,
            duration_ms=duration_ms,
            metadata=metadata or {
                "provider": self._skill.provider.value,
                "workflow_id": self._skill.workflow_id,
            },
        )

    def _create_status_result(
        self,
        task_id: str,
        status: str,
        output_url: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> SkillExecutionResult:
        """
        Helper to create a SkillExecutionResult for status checks.
        """
        return SkillExecutionResult(
            execution_id="",  # Not known during status check
            skill_id=self._skill.id,
            skill_name=self._skill.name,
            status=status,
            task_id=task_id,
            output_url=output_url,
            error=error,
            duration_ms=duration_ms,
            metadata={"provider": self._skill.provider.value},
        )
