import os
import httpx
import logging
from typing import Dict, Any, Optional, List
from .base import BaseGenerator

logger = logging.getLogger("workflow")


class ZhenZhenGenerator(BaseGenerator):
    """
    ZhenZhen (贞贞) Sora2 image-to-video API.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("ZHENZHEN_API_KEY")
        self.base_url = base_url or os.getenv("ZHENZHEN_API_BASE", "https://ai.t8star.cn")
        if not self.api_key:
            logger.warning("ZHENZHEN_API_KEY not configured")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _map_orientation(orientation: Optional[str]) -> Optional[str]:
        if not orientation:
            return None
        o = orientation.lower()
        if "landscape" in o or "horizontal" in o or "\u6a2a" in o:
            return "16:9"
        if "portrait" in o or "vertical" in o or "\u7ad6" in o:
            return "9:16"
        return None

    async def generate(
        self,
        prompt: str,
        images: Optional[List[str]] = None,
        image_url: Optional[str] = None,
        model: str = "sora-2",
        duration: int = 10,
        orientation: Optional[str] = None,
        hd: Optional[bool] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if not self.api_key:
            return {"status": "failed", "error": "API Key missing"}

        imgs = images or ([image_url] if image_url else [])
        if not imgs:
            return {"status": "failed", "error": "images missing"}

        # Enforce platform constraints: model sora-2, duration 10s
        model = "sora-2"
        duration = 10
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "model": model,
            "images": imgs,
        }

        aspect_ratio = self._map_orientation(orientation)
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio
        if duration:
            payload["duration"] = str(int(duration))
        if hd is not None:
            payload["hd"] = bool(hd)

        notify_hook = os.getenv("ZHENZHEN_NOTIFY_HOOK")
        if notify_hook:
            payload["notify_hook"] = notify_hook

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                url = f"{self.base_url}/v2/videos/generations"
                logger.info(f"[ZhenZhen] Submitting task to {url}")
                resp = await client.post(url, json=payload, headers=self._headers())
                data = resp.json()

                if resp.status_code != 200 or not data.get("task_id"):
                    err = (
                        data.get("message")
                        or data.get("error")
                        or data.get("fail_reason")
                        or f"HTTP {resp.status_code}"
                    )
                    return {"status": "failed", "error": err}

                return {"status": "pending", "task_id": data.get("task_id")}
        except Exception as e:
            logger.error(f"[ZhenZhen] Submit exception: {e}")
            return {"status": "failed", "error": str(e)}

    async def get_status(self, task_id: str) -> Dict[str, Any]:
        if not self.api_key:
            return {"status": "failed", "error": "API Key missing"}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                url = f"{self.base_url}/v2/videos/generations/{task_id}"
                resp = await client.get(url, headers=self._headers())
                data = resp.json()

                if resp.status_code != 200:
                    err = data.get("message") or data.get("error") or f"HTTP {resp.status_code}"
                    return {"status": "failed", "error": err}

                raw_status = (data.get("status") or data.get("state") or "")
                status_upper = raw_status.upper()
                if status_upper in {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE"}:
                    video_url = (
                        data.get("video_url")
                        or data.get("url")
                        or (data.get("result") or {}).get("video_url")
                        or (data.get("result") or {}).get("url")
                        or (data.get("data") or {}).get("output")
                    )
                    return {"status": "success", "url": video_url}
                if status_upper in {"FAILURE", "FAILED", "ERROR"}:
                    return {
                        "status": "failed",
                        "error": data.get("message") or data.get("error") or data.get("fail_reason")
                    }

                return {"status": "pending", "progress": data.get("progress")}
        except Exception as e:
            logger.error(f"[ZhenZhen] Status check failed: {e}")
            return {"status": "failed", "error": str(e)}
