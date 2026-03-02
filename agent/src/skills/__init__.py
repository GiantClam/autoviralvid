"""
Skills Module - Intelligent skill-based orchestration for video generation.

This module provides:
- SkillsRegistry: Central registry for all available skills
- SkillSelector: Intelligent skill selection based on requirements
- SkillAdapter: Unified interface for skill execution
- Adapters: Provider-specific implementations (RunningHub, TokenEngine, ZhenZhen)
"""

from .models import (
    SkillCategory,
    SkillProvider,
    SkillCapabilities,
    SkillMetrics,
    Skill,
    Pipeline,
    SkillExecutionRequest,
    SkillExecutionResult,
    UserPreferences,
)
from .base import SkillAdapter
from .registry import SkillsRegistry, get_skills_registry
from .selector import SkillSelector, get_skill_selector

__all__ = [
    # Models
    "SkillCategory",
    "SkillProvider",
    "SkillCapabilities",
    "SkillMetrics",
    "Skill",
    "Pipeline",
    "SkillExecutionRequest",
    "SkillExecutionResult",
    "UserPreferences",
    # Base
    "SkillAdapter",
    # Registry
    "SkillsRegistry",
    "get_skills_registry",
    # Selector
    "SkillSelector",
    "get_skill_selector",
]
