import os
import asyncio
import httpx
import logging
import json
from typing import Dict, Any, Optional, List
from .base import BaseGenerator

logger = logging.getLogger("workflow")

class ComfyUIGenerator(BaseGenerator):
    """
    Standard generator for platforms using ComfyUI Open API (e.g., RunningHub, Liblib.art).
    """
    def __init__(self, 
                 platform_name: str,
                 api_key: str,
                 workflow_id: str,
                 node_mappings: Dict[str, Any],
                 base_url: str):
        self.platform_name = platform_name
        self.api_key = api_key
        self.workflow_id = workflow_id
        self.node_mappings = node_mappings
        self.base_url = base_url
        
        # Determine if we need specialized RunningHub logic
        self.is_runninghub = "runninghub" in base_url or platform_name.lower() == "runninghub"

    async def _maybe_upload_image(self, url: str) -> str:
        """If on RunningHub and URL is external, upload it first."""
        import logging
        logger = logging.getLogger("workflow")
        
        if not url:
            logger.debug("[ComfyUI] No image URL provided, skipping upload.")
            return ""
            
        if not self.is_runninghub or not url.startswith("http"):
            logger.debug(f"[ComfyUI] Skipping upload (is_runninghub={self.is_runninghub}, url={url[:50]}...)")
            return url
            
        try:
            from src.runninghub_client import RunningHubClient
            client = RunningHubClient(self.api_key)
            
            # Simple check to see if it's already a RH internal name
            if "rh-images.xiaoyaoyou.com" in url or "runninghub.cn" in url:
                # If it's already on their OSS but we have the full URL, 
                # we might still need the fileName. But usually internal workflow 
                # nodes want the specific 'api/...' format.
                pass

            async with httpx.AsyncClient(timeout=60) as c:
                resp = await c.get(url)
                if resp.status_code == 200:
                    ext = url.split(".")[-1].split("?")[0] or "png"
                    if len(ext) > 4: ext = "png"
                    fname = f"input_{os.urandom(4).hex()}.{ext}"
                    internal_name = await client.upload_bytes(resp.content, fname)
                    logger.info(f"[{self.platform_name}] Uploaded image {url} -> {internal_name}")
                    return internal_name
        except Exception as e:
            logger.warning(f"[{self.platform_name}] Failed to upload image, falling back to URL: {e}")
        
        return url

    async def generate(self, **kwargs) -> Dict[str, Any]:
        """
        Translates generic parameters (prompt, image_url) into ComfyUI nodeInfoList.
        """
        node_info_list = []
        
        # Map prompt
        if "prompt" in kwargs and "prompt" in self.node_mappings:
            mapping = self.node_mappings["prompt"]
            node_info_list.append({
                "nodeId": mapping["nodeId"],
                "fieldName": mapping["fieldName"],
                "fieldValue": kwargs["prompt"]
            })
            
        # Map image
        if ("image_url" in kwargs or "image" in kwargs) and "image" in self.node_mappings:
            mapping = self.node_mappings["image"]
            url = kwargs.get("image_url") or kwargs.get("image")
            # CRITICAL: For RunningHub, we MUST upload the image first
            final_image_v = await self._maybe_upload_image(url)
            node_info_list.append({
                "nodeId": mapping["nodeId"],
                "fieldName": mapping["fieldName"],
                "fieldValue": final_image_v
            })

        try:
            headers = {"Content-Type": "application/json"}
            if self.is_runninghub:
                headers["Host"] = "www.runninghub.cn"
                
            async with httpx.AsyncClient(timeout=60) as client:
                logger.info(f"[{self.platform_name}] Submitting task to {self.base_url}")
                payload = {
                    "apiKey": self.api_key,
                    "workflowId": self.workflow_id,
                    "nodeInfoList": node_info_list
                }
                
                resp = await client.post(f"{self.base_url}/task/openapi/create", json=payload, headers=headers)
                data = resp.json()
                
                if resp.status_code != 200 or data.get("code") != 0:
                    err_msg = data.get("msg") or data.get("message") or f"HTTP {resp.status_code}"
                    logger.error(f"[{self.platform_name}] Create FAILED: {err_msg} | Payload: {payload}")
                    return {"status": "failed", "error": err_msg}
                
                task_id = data.get("data", {}).get("taskId") or data.get("data", {}).get("id")
                return {"status": "pending", "task_id": str(task_id)}
                
        except Exception as e:
            logger.error(f"[{self.platform_name}] Submit exception: {e}")
            return {"status": "failed", "error": str(e)}

    async def get_status(self, task_id: str) -> Dict[str, Any]:
        try:
            headers = {}
            if self.is_runninghub:
                headers["Host"] = "www.runninghub.cn"
                
            async with httpx.AsyncClient(timeout=30) as client:
                payload = {"apiKey": self.api_key, "taskId": task_id}
                resp = await client.post(f"{self.base_url}/task/openapi/status", json=payload, headers=headers)
                data = resp.json()
                
                status = str(data.get("data") or "").upper()
                if status == "SUCCESS":
                    # Fetch outputs
                    res_resp = await client.post(f"{self.base_url}/task/openapi/outputs", json=payload, headers=headers)
                    res_data = res_resp.json()
                    outputs = res_data.get("data") or []
                    
                    # Search for video URL
                    video_url = None
                    for item in outputs:
                        url = item.get("fileUrl") or item.get("url")
                        if not url: continue
                        
                        # Check extensions or type
                        url_lower = str(url).lower()
                        ftype = str(item.get("fileType") or "").lower()
                        if "mp4" in url_lower or ftype == "mp4" or "video" in ftype:
                            video_url = url
                            break
                    
                    if not video_url and outputs:
                        # Fallback to first URL found if no mp4 detected
                        video_url = outputs[0].get("fileUrl") or outputs[0].get("url")

                    return {"status": "success", "url": video_url}
                elif status in ("FAILED", "ERROR"):
                    return {"status": "failed", "error": f"Platform reported failure: {data.get('msg')}"}
                else:
                    return {"status": "pending"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
