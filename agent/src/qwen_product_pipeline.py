from __future__ import annotations

import asyncio
import logging
import os

import httpx

from src.runninghub_client import RunningHubClient


logger = logging.getLogger("qwen_product_pipeline")


async def batch_t2i(product_image_url: str, prompt: str, timeout: int = 600):
    """
    Run the Qwen product storyboard workflow and return generated images plus
    the parsed per-scene descriptions.
    """
    client = RunningHubClient(os.getenv("RUNNINGHUB_API_KEY"))
    t2i_workflow_id = os.getenv(
        "RUNNINGHUB_QWEN_STORYBOARD_WORKFLOW_ID", "2021433434782044162"
    )

    image_ref = product_image_url
    if product_image_url.startswith("http"):
        try:
            async with httpx.AsyncClient(timeout=60) as hc:
                resp = await hc.get(product_image_url)
                if resp.status_code == 200 and resp.content:
                    fname = product_image_url.split("/")[-1] or "product.png"
                    image_ref = await client.upload_bytes(
                        resp.content, fname, file_type="input"
                    )
                    logger.info("[BATCH_T2I] Uploaded product image: %s", image_ref)
        except Exception as exc:
            logger.warning("[BATCH_T2I] Upload failed, using raw URL: %s", exc)

    node_info_list = [
        {"nodeId": "74", "fieldName": "image", "fieldValue": image_ref},
        {"nodeId": "103", "fieldName": "text", "fieldValue": prompt},
    ]
    task_id = await client.create_task(t2i_workflow_id, node_info_list)
    logger.info("[BATCH_T2I] Task submitted: %s", task_id)

    poll_interval = 5
    max_iters = timeout // poll_interval
    for i in range(max_iters):
        status = await client.get_status(task_id)
        if i % 12 == 0:
            logger.info(
                "[BATCH_T2I] Task %s: status=%s, elapsed=%ss",
                task_id,
                status,
                i * poll_interval,
            )
        if status == "SUCCESS":
            outputs = await client.get_outputs(task_id)
            break
        if status in ("FAILED", "ERROR"):
            raise RuntimeError(f"T2I batch task failed: task_id={task_id}")
        await asyncio.sleep(poll_interval)
    else:
        raise RuntimeError(f"T2I batch task timed out: task_id={task_id}")

    image_urls = []
    desc_text = None
    for item in outputs:
        url = None
        for field in ("fileUrl", "url", "ossUrl", "value"):
            val = item.get(field)
            if val and isinstance(val, str) and val.startswith("http"):
                url = val.strip()
                break
        if not url:
            continue
        url_path = url.split("?")[0].lower()
        file_type = (item.get("fileType") or "").lower()
        if file_type in ("png", "jpg", "jpeg", "webp") or any(
            url_path.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")
        ):
            image_urls.append(url)
        elif file_type in ("txt", "json") or any(
            url_path.endswith(ext) for ext in (".txt", ".json")
        ):
            try:
                async with httpx.AsyncClient(timeout=30) as hc:
                    response = await hc.get(url)
                    if response.status_code == 200:
                        desc_text = response.text
            except Exception:
                pass

    descriptions = []
    if desc_text:
        for part in desc_text.split("Next Scene:"):
            part = part.strip()
            if part:
                descriptions.append(part)

    while len(descriptions) < len(image_urls):
        descriptions.append(f"Product scene {len(descriptions) + 1}")

    logger.info(
        "[BATCH_T2I] Result: %s images, %s descriptions",
        len(image_urls),
        len(descriptions),
    )
    await client.aclose()
    return image_urls, descriptions
