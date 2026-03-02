"""
RunningHub Skill Adapter - Adapter for RunningHub ComfyUI-based workflows.
"""

import os
import logging
from typing import Dict, Any, Optional, Tuple, List

from ..base import BaseSkillAdapter
from ..models import Skill, SkillExecutionRequest, SkillExecutionResult

logger = logging.getLogger("skills.adapters.runninghub")


class RunningHubAdapter(BaseSkillAdapter):
    """
    Adapter for RunningHub ComfyUI-based workflows.

    Handles:
    - Node mapping from semantic params to workflow-specific node IDs
    - Image upload for external URLs
    - Task creation and status polling
    """

    def __init__(self, skill: Skill):
        super().__init__(skill)
        self.api_key = os.getenv("RUNNINGHUB_API_KEY")
        self.base_url = skill.api_base_url or "https://www.runninghub.cn"

    async def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """
        Execute the skill by submitting a task to RunningHub.

        Args:
            request: Execution request with params

        Returns:
            SkillExecutionResult with status="pending" or "submitted" and task_id
        """
        if not self.api_key:
            return self._create_result(
                request,
                status="failed",
                error="RUNNINGHUB_API_KEY not configured",
                error_code="CONFIG_ERROR",
            )

        if not self._skill.workflow_id:
            return self._create_result(
                request,
                status="failed",
                error="Skill has no workflow_id configured",
                error_code="CONFIG_ERROR",
            )

        # Validate params
        is_valid, error_msg = await self.validate_params(request.params)
        if not is_valid:
            return self._create_result(
                request,
                status="failed",
                error=error_msg,
                error_code="VALIDATION_ERROR",
            )

        try:
            # Import here to avoid circular imports
            from src.runninghub_client import RunningHubClient, RunningHubError

            client = RunningHubClient(self.api_key)

            # Build node info list from skill mappings
            node_info_list = await self._build_node_info(request.params, client)

            logger.info(
                f"[RunningHubAdapter] Submitting task: "
                f"skill={self.skill_name}, "
                f"workflow_id={self._skill.workflow_id}, "
                f"nodes={len(node_info_list)}"
            )

            # Submit task
            task_id = await client.create_task(
                workflow_id=self._skill.workflow_id,
                node_info_list=node_info_list,
            )

            logger.info(f"[RunningHubAdapter] Task submitted: {task_id}")

            return self._create_result(
                request,
                status="submitted",
                task_id=task_id,
                metadata={
                    "provider": "runninghub",
                    "workflow_id": self._skill.workflow_id,
                    "node_count": len(node_info_list),
                },
            )

        except Exception as e:
            error_msg = str(e)
            error_code = "RUNNINGHUB_ERROR"

            # Check for specific error types
            if "TOKEN_INVALID" in error_msg or "api key" in error_msg.lower():
                error_code = "AUTH_ERROR"
            elif "TASK_QUEUE_MAXED" in error_msg or "队列" in error_msg:
                error_code = "QUEUE_FULL"
            elif "workflow" in error_msg.lower():
                error_code = "WORKFLOW_ERROR"

            logger.error(f"[RunningHubAdapter] Execution failed: {error_msg}")

            return self._create_result(
                request,
                status="failed",
                error=error_msg,
                error_code=error_code,
            )

    async def get_status(self, task_id: str) -> SkillExecutionResult:
        """
        Check the status of a RunningHub task.

        Args:
            task_id: RunningHub task ID

        Returns:
            SkillExecutionResult with current status
        """
        if not self.api_key:
            return self._create_status_result(
                task_id,
                status="failed",
                error="RUNNINGHUB_API_KEY not configured",
            )

        try:
            from src.runninghub_client import RunningHubClient

            client = RunningHubClient(self.api_key)
            status = await client.get_status(task_id)

            if status == "SUCCESS":
                # Get outputs
                outputs = await client.get_outputs(task_id)
                video_url = self._extract_video_url(outputs)

                if video_url:
                    return self._create_status_result(
                        task_id,
                        status="succeeded",
                        output_url=video_url,
                    )
                else:
                    return self._create_status_result(
                        task_id,
                        status="failed",
                        error="No video URL in outputs",
                    )

            elif status in ("FAILED", "ERROR"):
                return self._create_status_result(
                    task_id,
                    status="failed",
                    error=f"RunningHub task failed: {status}",
                )

            elif status in ("QUEUED", "RUNNING"):
                return self._create_status_result(
                    task_id,
                    status="processing",
                )

            else:
                # Unknown status, treat as processing
                return self._create_status_result(
                    task_id,
                    status="processing",
                )

        except Exception as e:
            logger.error(f"[RunningHubAdapter] Status check failed: {e}")
            return self._create_status_result(
                task_id,
                status="failed",
                error=str(e),
            )

    # Keys in node_mappings that hold image URLs and need upload handling
    _IMAGE_PARAM_KEYS = {"image", "first_frame", "last_frame"}

    # Map from node_mapping key → params key (where the URL value comes from)
    _IMAGE_PARAM_MAP: Dict[str, str] = {
        "image": "image_url",
        "first_frame": "first_frame_url",
        "last_frame": "last_frame_url",
    }

    # Keys in node_mappings that hold audio URLs and need upload handling
    _AUDIO_PARAM_KEYS = {"audio"}

    # Map from node_mapping key → params key (where the audio URL comes from)
    _AUDIO_PARAM_MAP: Dict[str, str] = {
        "audio": "audio_url",
    }

    async def _build_node_info(
        self,
        params: Dict[str, Any],
        client: Any,
    ) -> List[Dict[str, Any]]:
        """
        Build nodeInfoList from skill mappings and execution params.

        Supports:
        - prompt: text prompt
        - image: single reference image (sora2 pipeline)
        - first_frame / last_frame: paired images (qwen_product pipeline)
        - width / height / duration: numeric parameters
        - Any other custom keys defined in node_mappings

        Args:
            params: Execution parameters (prompt, image_url, first_frame_url, etc.)
            client: RunningHubClient for image upload

        Returns:
            List of node info dicts for RunningHub API
        """
        node_info_list = []
        mappings = self._skill.node_mappings
        handled_keys: set = set()

        # --- 1. Map prompt ---
        if "prompt" in mappings and params.get("prompt"):
            mapping = mappings["prompt"]
            node_info_list.append({
                "nodeId": str(mapping["nodeId"]),
                "fieldName": mapping.get("fieldName", "text"),
                "fieldValue": params["prompt"],
            })
            handled_keys.add("prompt")

        # --- 2. Map image fields (with upload if needed) ---
        for mapping_key in self._IMAGE_PARAM_KEYS:
            if mapping_key not in mappings:
                continue
            # Resolve param value: use specific key first, fallback to image_url
            param_key = self._IMAGE_PARAM_MAP.get(mapping_key, "image_url")
            image_value = params.get(param_key) or (params.get("image_url") if mapping_key == "image" else None)
            if not image_value:
                continue

            mapping = mappings[mapping_key]
            # Upload external URLs if required
            if self._skill.requires_upload and isinstance(image_value, str) and image_value.startswith("http"):
                try:
                    uploaded_path = await self._upload_image(image_value, client)
                    if uploaded_path:
                        image_value = uploaded_path
                except Exception as e:
                    logger.warning(f"[RunningHubAdapter] Image upload failed for {mapping_key}, using URL: {e}")

            node_info_list.append({
                "nodeId": str(mapping["nodeId"]),
                "fieldName": mapping.get("fieldName", "image"),
                "fieldValue": image_value,
            })
            handled_keys.add(mapping_key)

        # --- 3. Map audio fields (with upload if needed) ---
        for mapping_key in self._AUDIO_PARAM_KEYS:
            if mapping_key not in mappings:
                continue
            param_key = self._AUDIO_PARAM_MAP.get(mapping_key, "audio_url")
            audio_value = params.get(param_key)
            if not audio_value:
                continue

            mapping = mappings[mapping_key]
            # Upload external audio URLs if required
            if self._skill.requires_upload and isinstance(audio_value, str) and audio_value.startswith("http"):
                try:
                    uploaded_path = await self._upload_file(audio_value, client, file_type="audio")
                    if uploaded_path:
                        audio_value = uploaded_path
                except Exception as e:
                    logger.warning(f"[RunningHubAdapter] Audio upload failed for {mapping_key}, using URL: {e}")

            node_info_list.append({
                "nodeId": str(mapping["nodeId"]),
                "fieldName": mapping.get("fieldName", "audio"),
                "fieldValue": audio_value,
            })
            handled_keys.add(mapping_key)

        # --- 4. Map remaining parameters (width, height, duration, voice_mode, voice_text, etc.) ---
        for param_name, mapping in mappings.items():
            if param_name in handled_keys:
                continue

            # Try to get value from params — keys match directly
            value = params.get(param_name)

            # For node_mappings with a "default" field, use it when param is absent
            if value is None and isinstance(mapping, dict) and "default" in mapping:
                value = mapping["default"]

            if value is not None:
                node_info_list.append({
                    "nodeId": str(mapping["nodeId"]),
                    "fieldName": mapping.get("fieldName", param_name),
                    "fieldValue": str(value),
                })

        return node_info_list

    async def _upload_image(self, url: str, client: Any) -> Optional[str]:
        """
        Download and upload an external image to RunningHub.
        """
        return await self._upload_file(url, client, file_type="image")

    @staticmethod
    def _is_r2_url(url: str) -> bool:
        """Check if a URL is a Cloudflare R2 URL (including custom domains)."""
        if ".r2.dev/" in url or "r2.cloudflarestorage.com/" in url:
            return True
        # Also match the R2_PUBLIC_BASE custom domain
        import os
        public_base = os.getenv("R2_PUBLIC_BASE", "")
        if public_base and url.startswith(public_base):
            return True
        return False

    @staticmethod
    def _download_from_r2(url: str) -> Optional[bytes]:
        """Download file content from R2 using S3 client (bypasses public access 401)."""
        import os
        from urllib.parse import urlparse

        try:
            from src.r2 import get_r2_client

            r2 = get_r2_client()
            if not r2:
                return None

            parsed = urlparse(url)
            key = parsed.path.lstrip("/")

            # Also check R2_PUBLIC_BASE for custom domain URLs
            public_base = os.getenv("R2_PUBLIC_BASE", "")
            if public_base and url.startswith(public_base):
                key = url[len(public_base.rstrip("/")):].lstrip("/")

            bucket = os.getenv("R2_BUCKET", "video")
            resp = r2.get_object(Bucket=bucket, Key=key)
            content = resp["Body"].read()
            logger.info(f"[RunningHubAdapter] Downloaded from R2 (S3): key={key} ({len(content)} bytes)")
            return content
        except Exception as exc:
            logger.warning(f"[RunningHubAdapter] R2 S3 download failed: {exc}")
            return None

    async def _upload_file(
        self,
        url: str,
        client: Any,
        file_type: str = "image",
    ) -> Optional[str]:
        """
        Download and upload an external file (image or audio) to RunningHub.

        Supports R2 URLs via direct S3 download (avoids 401 on pub-*.r2.dev).

        Args:
            url: External file URL
            client: RunningHubClient
            file_type: "image" or "audio"

        Returns:
            RunningHub internal path (api/filename.ext) or None on failure
        """
        import httpx
        import asyncio

        # Default extensions per file type
        default_ext = "png" if file_type == "image" else "mp3"
        valid_exts = {
            "image": {"png", "jpg", "jpeg", "webp", "bmp"},
            "audio": {"mp3", "wav", "m4a", "aac", "flac", "ogg"},
        }.get(file_type, {"bin"})

        try:
            content: Optional[bytes] = None

            # Try R2 S3 download first for R2 URLs (avoids pub-*.r2.dev 401)
            if self._is_r2_url(url):
                content = await asyncio.to_thread(self._download_from_r2, url)

            # Fallback to HTTP download
            if content is None:
                async with httpx.AsyncClient(timeout=120) as http:
                    resp = await http.get(url)
                    if resp.status_code != 200:
                        logger.warning(f"[RunningHubAdapter] Failed to download {file_type}: HTTP {resp.status_code}")
                        return None
                    content = resp.content

            if len(content) < 100:
                logger.warning(f"[RunningHubAdapter] Downloaded content too small: {len(content)} bytes")
                return None

            # Extract extension from URL
            ext = default_ext
            if "." in url:
                url_ext = url.split(".")[-1].split("?")[0].lower()
                if url_ext in valid_exts:
                    ext = url_ext

            # Generate unique filename
            import uuid
            filename = f"input_{uuid.uuid4().hex[:8]}.{ext}"

            # Upload to RunningHub
            uploaded_path = await client.upload_bytes(content, filename)
            logger.info(f"[RunningHubAdapter] {file_type.capitalize()} uploaded: {uploaded_path}")
            return uploaded_path

        except Exception as e:
            logger.warning(f"[RunningHubAdapter] {file_type.capitalize()} upload failed: {e}")
            return None

    def _extract_video_url(self, outputs: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract video URL from RunningHub outputs.

        Tries multiple field names for compatibility.
        """
        for item in outputs:
            # Try various field names
            for field in ("fileUrl", "url", "ossUrl", "downloadUrl", "value"):
                url = item.get(field)
                if url:
                    # Check if it looks like a video
                    file_type = item.get("fileType", "").lower()
                    if "mp4" in url.lower() or file_type == "mp4" or file_type == "video":
                        return url
                    # If no file type info, still return if it's a URL
                    if url.startswith("http"):
                        return url

        # Fallback: return first output with any URL
        if outputs and outputs[0]:
            for field in ("fileUrl", "url", "ossUrl", "downloadUrl", "value"):
                url = outputs[0].get(field)
                if url and url.startswith("http"):
                    return url

        return None
