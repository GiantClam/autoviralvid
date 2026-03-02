"""
Mock Skill Adapter - Simulates video generation for development and testing.

Used as a stand-in for providers whose APIs are not yet available (e.g., Seedance 2.0).
Returns a placeholder video URL after a simulated delay.
"""

import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, Tuple

from ..models import SkillExecutionRequest, SkillExecutionResult
from ..base import BaseSkillAdapter

logger = logging.getLogger("skills.adapters.mock")

# A set of sample video URLs for realistic mock responses
MOCK_VIDEO_URLS = [
    "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
    "https://www.w3schools.com/html/mov_bbb.mp4",
    "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
]

MOCK_AUDIO_URLS = [
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
]


class MockAdapter(BaseSkillAdapter):
    """
    Mock adapter that simulates video/audio generation.

    - In sync mode: waits `delay_seconds` then returns a mock URL.
    - In async mode: returns immediately with status='pending' and a mock task_id.
      Subsequent get_status() calls will return 'succeeded' after the delay.
    """

    def __init__(self, skill, delay_seconds: float = 3.0):
        super().__init__(skill)
        self.delay_seconds = delay_seconds
        self._pending_tasks: Dict[str, float] = {}  # task_id -> created_at timestamp

    async def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """Execute the mock skill."""
        prompt = request.params.get("prompt", "")
        logger.info(f"[MockAdapter] Executing '{self.skill_name}' with prompt: {prompt[:80]}...")

        task_id = f"mock_{uuid.uuid4().hex[:12]}"

        if request.async_mode:
            # Return pending immediately
            import time
            self._pending_tasks[task_id] = time.time()
            logger.info(f"[MockAdapter] Async mode: returning pending task_id={task_id}")
            return self._create_result(
                request,
                status="submitted",
                task_id=task_id,
                metadata={
                    "provider": "mock",
                    "mock_delay": self.delay_seconds,
                },
            )

        # Sync mode: wait and return
        await asyncio.sleep(self.delay_seconds)
        mock_url = self._get_mock_url()
        return self._create_result(
            request,
            status="succeeded",
            task_id=task_id,
            output_url=mock_url,
            duration_ms=int(self.delay_seconds * 1000),
        )

    async def get_status(self, task_id: str) -> SkillExecutionResult:
        """Check mock task status. Always returns succeeded after delay."""
        import time
        created_at = self._pending_tasks.get(task_id, 0)
        elapsed = time.time() - created_at if created_at else 999

        if elapsed < self.delay_seconds:
            return self._create_status_result(
                task_id,
                status="processing",
            )

        # Done
        mock_url = self._get_mock_url()
        return self._create_status_result(
            task_id,
            status="succeeded",
            output_url=mock_url,
            duration_ms=int(elapsed * 1000),
        )

    async def validate_params(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Mock validation: always passes."""
        if not params.get("prompt"):
            return False, "Prompt is required"
        return True, None

    def _get_mock_url(self) -> str:
        """Return a mock video/audio URL based on skill category."""
        from ..models import SkillCategory
        if self._skill.category == SkillCategory.AUDIO:
            idx = hash(self._skill.name) % len(MOCK_AUDIO_URLS)
            return MOCK_AUDIO_URLS[idx]
        idx = hash(self._skill.name) % len(MOCK_VIDEO_URLS)
        return MOCK_VIDEO_URLS[idx]
