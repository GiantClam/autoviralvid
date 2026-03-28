import json
import os
from typing import Protocol

from dotenv import load_dotenv

from src.generators.comfyui import ComfyUIGenerator
from src.generators.fallback import MultiGenerator
from src.generators.token_engine import TokenEngineGenerator

# Load env on import so provider selection can read runtime flags immediately.
load_dotenv()


class ImageProvider(Protocol):
    async def generate(self, prompt: str) -> str: ...


class VideoProvider(Protocol):
    async def generate(
        self, prompt: str, image_url: str, duration: int = 6
    ) -> str: ...


def get_image_provider() -> ImageProvider:
    """Select image provider from PROVIDER_IMAGE env var."""
    provider_name = os.getenv("PROVIDER_IMAGE")
    if not provider_name:
        raise ValueError("Missing required env var: PROVIDER_IMAGE")

    provider = provider_name.lower()

    if provider == "qwen_runninghub":
        from src.providers_image_scene_runninghub import SceneRunningHubImageProvider

        return SceneRunningHubImageProvider()
    if provider == "seedream":
        from src.providers_image_seedream import SeedreamImageProvider

        return SeedreamImageProvider()
    if provider == "nanobanana":
        from src.providers_image_nanobanana import NanoBananaImageProvider

        return NanoBananaImageProvider()

    raise ValueError(f"Unsupported image provider: {provider}")


def _load_workflow_config():
    config_path = os.path.join(os.path.dirname(__file__), "configs", "workflows.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_video_provider() -> VideoProvider:
    """
    Returns a MultiGenerator configured with prioritized video providers.
    """
    provider_env = (os.getenv("PROVIDER_VIDEO") or "runninghub").lower()

    if provider_env in {"mock", "seedance"}:
        raise RuntimeError(
            f"PROVIDER_VIDEO={provider_env} is disabled. Mock-like providers are not allowed in any environment."
        )

    config = _load_workflow_config()
    generators = []

    # Primary: RunningHub
    rh_key = os.getenv("RUNNINGHUB_API_KEY")
    rh_workflow = config.get("runninghub", {}).get("workflows", {}).get("sora2")
    if rh_key and rh_workflow:
        generators.append(
            ComfyUIGenerator(
                "RunningHub",
                rh_key,
                rh_workflow["workflow_id"],
                rh_workflow["nodes"],
                config["runninghub"]["base_url"],
            )
        )

    # Backup 1: Liblib.art
    ll_key = os.getenv("LIBLIB_API_KEY")
    ll_workflow = config.get("liblib", {}).get("workflows", {}).get("standard")
    if ll_key and ll_workflow:
        generators.append(
            ComfyUIGenerator(
                "Liblib",
                ll_key,
                ll_workflow["workflow_id"],
                ll_workflow["nodes"],
                config["liblib"]["base_url"],
            )
        )

    # Backup 2: Token Engine (Sora2)
    te_key = os.getenv("SORA2_TOKEN_ENGINE_KEY")
    if te_key:
        generators.append(TokenEngineGenerator(te_key))

    if not generators:
        raise RuntimeError(
            "No real video generators configured. Mock fallback is disabled."
        )

    return MultiGenerator(generators)
