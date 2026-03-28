import logging
from typing import Dict, Any, Optional
from src.generators.base import BaseGenerator

logger = logging.getLogger("avatar_agent")

class AvatarAgent:
    """
    Agent specialized in Digital Human (Avatar) synthesis.
    """
    def __init__(self, provider: Optional[BaseGenerator] = None):
        self.provider = provider

    async def synthesize(self, video_url: str, audio_url: str, **kwargs) -> Dict[str, Any]:
        """
        Merges a video of a person with a specific audio track to create a digital human performance.
        """
        logger.info(f"[AvatarAgent] Synthesizing avatar performance for video: {video_url}")

        if not self.provider:
            raise RuntimeError(
                "Avatar synthesis provider is not configured. Mock behavior is disabled."
            )

        result = await self.provider.generate(
            video_url=video_url,
            audio_url=audio_url,
            **kwargs,
        )

        if result.get("status") != "success" or not result.get("url"):
            raise RuntimeError(f"Avatar synthesis failed: {result}")

        return {
            "status": "success",
            "avatar_video_url": result["url"],
            "message": "Avatar synthesis completed",
        }

async def avatar_node(state: Dict[str, Any]):
    """
    Workflow node for avatar synthesis.
    """
    if not state.get("use_avatar", False):
        return state

    agent = AvatarAgent()
    video_url = state.get("final_video_url")
    audio_url = state.get("final_audio_url")
    
    new_state = {}
    if video_url:
        result = await agent.synthesize(video_url, audio_url)
        new_state["final_video_url"] = result.get("avatar_video_url")
        new_state["status"] = "completed" # Transition to completed
        
    return new_state
