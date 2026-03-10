"""
REST API routes for the form-driven video generation workflow.

Provides endpoints for project CRUD, storyboard generation, image/video
generation, status polling, final rendering, batch creation, and an AI
assistant chat endpoint.
"""

import asyncio
import os
import uuid
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field, field_validator
from supabase import create_client, Client

from src.auth import get_current_user, AuthUser

logger = logging.getLogger("api_routes")

# ---------------------------------------------------------------------------
# Supabase client (module-level singleton)
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY")
)

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("[api_routes] Supabase client initialised")
    except Exception as exc:
        logger.warning(f"[api_routes] Failed to create Supabase client: {exc}")

# ---------------------------------------------------------------------------
# Service / client singletons (lazy – imported at call-sites that need them)
# ---------------------------------------------------------------------------
_project_service = None


def _get_project_service():
    """Lazily import and cache the ProjectService singleton."""
    global _project_service
    if _project_service is None:
        from src.project_service import ProjectService
        _project_service = ProjectService()
    return _project_service


_openrouter_client = None


def _get_openrouter_client():
    """Lazily import and cache the OpenRouterClient singleton."""
    global _openrouter_client
    if _openrouter_client is None:
        from src.openrouter_client import OpenRouterClient
        _openrouter_client = OpenRouterClient()
    return _openrouter_client


def _require_supabase() -> Client:
    """Return the Supabase client or raise 503."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    return supabase


def _ensure_queue_worker(reason: str) -> None:
    """Best-effort queue worker keepalive for long-running background video tasks."""
    try:
        from src.video_task_queue_supabase import ensure_supabase_queue_worker

        snapshot = ensure_supabase_queue_worker(reason)
        logger.debug(f"[queue_worker] {reason}: {snapshot}")
    except Exception as exc:
        logger.warning(f"[queue_worker] Failed to ensure worker ({reason}): {exc}")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/api/v1", tags=["Video Projects"])

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _validate_url(v: Optional[str]) -> Optional[str]:
    """Accept http/https URLs only — reject javascript:, data:, file:, etc."""
    if v is None:
        return v
    v = v.strip()
    if not v:
        return None
    if not v.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    if len(v) > 2048:
        raise ValueError("URL too long (max 2048 chars)")
    return v


# ---------------------------------------------------------------------------
# Pydantic request / response models (with strict validation)
# ---------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    template_id: str = Field(default="product-ad", max_length=64)
    theme: str = Field(..., min_length=1, max_length=500)  # Video topic / goal
    product_image_url: Optional[str] = Field(default=None, max_length=2048)
    style: str = Field(default="现代简约", max_length=100)
    duration: int = Field(default=30, ge=5, le=3600)  # seconds
    orientation: str = Field(default="竖屏", max_length=20)
    video_type: Optional[str] = Field(default=None, max_length=64)
    aspect_ratio: str = Field(default="9:16", max_length=10)
    # Digital Human specific params
    audio_url: Optional[str] = Field(default=None, max_length=2048)
    voice_mode: Optional[int] = Field(default=None, ge=0, le=1)
    voice_text: Optional[str] = Field(default=None, max_length=10000)
    motion_prompt: Optional[str] = Field(default=None, max_length=500)

    @field_validator("product_image_url", "audio_url", mode="before")
    @classmethod
    def check_urls(cls, v: Optional[str]) -> Optional[str]:
        return _validate_url(v)


class UpdateSceneRequest(BaseModel):
    description: Optional[str] = Field(default=None, max_length=2000)
    narration: Optional[str] = Field(default=None, max_length=5000)


class RegenerateImageRequest(BaseModel):
    new_prompt: Optional[str] = Field(default=None, max_length=1000)


class RegenerateVideoRequest(BaseModel):
    new_prompt: Optional[str] = Field(default=None, max_length=1000)


class BatchCreateRequest(BaseModel):
    template_id: str = Field(default="product-ad", max_length=64)
    product_images: List[str] = Field(..., min_length=1, max_length=20)
    theme: str = Field(..., min_length=1, max_length=500)
    style: str = Field(default="现代简约", max_length=100)
    duration: int = Field(default=30, ge=5, le=3600)
    orientation: str = Field(default="竖屏", max_length=20)
    aspect_ratio: str = Field(default="9:16", max_length=10)

    @field_validator("product_images", mode="before")
    @classmethod
    def check_image_urls(cls, v: List[str]) -> List[str]:
        return [_validate_url(url) or "" for url in v]


class AIAssistantRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    project_context: Optional[dict] = None


# ---------------------------------------------------------------------------
# 1. POST /projects — Create a new project
# ---------------------------------------------------------------------------


@router.post("/projects", summary="Create project", description="Create a new video project with template, theme, and configuration. Returns project metadata with run_id.")
async def create_project(body: CreateProjectRequest, user: AuthUser = Depends(get_current_user)):
    """Create a new video project and return its metadata including *run_id*."""
    try:
        svc = _get_project_service()
        params: Dict[str, Any] = {
            "theme": body.theme,
            "product_image_url": body.product_image_url,
            "style": body.style,
            "duration": body.duration,
            "orientation": body.orientation,
            "video_type": body.video_type,
            "aspect_ratio": body.aspect_ratio,
        }
        # Digital human params
        if body.audio_url:
            params["audio_url"] = body.audio_url
        if body.voice_mode is not None:
            params["voice_mode"] = body.voice_mode
        if body.voice_text:
            params["voice_text"] = body.voice_text
        if body.motion_prompt:
            params["motion_prompt"] = body.motion_prompt

        project = await svc.create_project(
            template_id=body.template_id,
            params=params,
        )
        return project
    except Exception as exc:
        logger.error(f"[create_project] {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 2. GET /projects — List all projects
# ---------------------------------------------------------------------------


@router.get("/projects")
async def list_projects(limit: int = 40, user: AuthUser = Depends(get_current_user)):
    """Return the most recent projects from the *autoviralvid_jobs* table."""
    sb = _require_supabase()
    try:
        res = (
            sb.table("autoviralvid_jobs")
            .select(
                "run_id, slogan, cover_url, video_url, share_slug, "
                "status, storyboards, created_at, updated_at"
            )
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {"projects": res.data or []}
    except Exception as exc:
        logger.error(f"[list_projects] {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 3. GET /projects/{run_id} — Get project details
# ---------------------------------------------------------------------------


@router.get("/projects/{run_id}")
async def get_project(run_id: str, user: AuthUser = Depends(get_current_user)):
    """Return full project details including storyboard and video tasks."""
    sb = _require_supabase()
    try:
        # Fetch job metadata
        job_res = (
            sb.table("autoviralvid_jobs")
            .select("*")
            .eq("run_id", run_id)
            .single()
            .execute()
        )
        if not job_res.data:
            raise HTTPException(status_code=404, detail=f"Project {run_id} not found")

        project = job_res.data

        # Attach video tasks
        tasks_res = (
            sb.table("autoviralvid_video_tasks")
            .select("*")
            .eq("run_id", run_id)
            .order("clip_idx", desc=False)
            .execute()
        )
        project["video_tasks"] = tasks_res.data or []

        # Attach crew session context if available
        try:
            session_res = (
                sb.table("autoviralvid_crew_sessions")
                .select("status, context")
                .eq("run_id", run_id)
                .limit(1)
                .execute()
            )
            if session_res.data:
                project["session"] = session_res.data[0]
        except Exception:
            pass

        return project
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[get_project] {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 4. POST /projects/{run_id}/storyboard — Generate storyboard
# ---------------------------------------------------------------------------


@router.post("/projects/{run_id}/storyboard")
async def generate_storyboard(run_id: str, background_tasks: BackgroundTasks, user: AuthUser = Depends(get_current_user)):
    """Kick off storyboard generation as a background task."""
    sb = _require_supabase()

    # Verify the project exists
    job_res = (
        sb.table("autoviralvid_jobs")
        .select("run_id")
        .eq("run_id", run_id)
        .limit(1)
        .execute()
    )
    if not job_res.data:
        raise HTTPException(status_code=404, detail=f"Project {run_id} not found")

    # Update status immediately
    sb.table("autoviralvid_jobs").update(
        {"status": "generating_storyboard", "updated_at": datetime.utcnow().isoformat()}
    ).eq("run_id", run_id).execute()

    async def _bg_generate_storyboard():
        try:
            svc = _get_project_service()
            await svc.generate_storyboard(run_id)
        except Exception as exc:
            logger.error(f"[generate_storyboard bg] {exc}", exc_info=True)
            sb.table("autoviralvid_jobs").update(
                {"status": "storyboard_failed", "updated_at": datetime.utcnow().isoformat()}
            ).eq("run_id", run_id).execute()

    background_tasks.add_task(_bg_generate_storyboard)
    return {"run_id": run_id, "status": "generating_storyboard"}


# ---------------------------------------------------------------------------
# 5. PUT /projects/{run_id}/storyboard/scenes/{scene_idx} — Update scene
# ---------------------------------------------------------------------------


@router.put("/projects/{run_id}/storyboard/scenes/{scene_idx}")
async def update_scene(run_id: str, scene_idx: int, body: UpdateSceneRequest, user: AuthUser = Depends(get_current_user)):
    """Update a single scene's description and/or narration in the storyboard JSON."""
    sb = _require_supabase()
    try:
        job_res = (
            sb.table("autoviralvid_jobs")
            .select("storyboards")
            .eq("run_id", run_id)
            .single()
            .execute()
        )
        if not job_res.data:
            raise HTTPException(status_code=404, detail=f"Project {run_id} not found")

        storyboards = job_res.data.get("storyboards")
        if not storyboards or not isinstance(storyboards, list):
            raise HTTPException(status_code=400, detail="No storyboard data available")

        if scene_idx < 0 or scene_idx >= len(storyboards):
            raise HTTPException(
                status_code=400,
                detail=f"scene_idx {scene_idx} out of range (0-{len(storyboards) - 1})",
            )

        # Patch the requested fields
        scene = storyboards[scene_idx]
        if body.description is not None:
            scene["description"] = body.description
        if body.narration is not None:
            scene["narration"] = body.narration

        storyboards[scene_idx] = scene

        sb.table("autoviralvid_jobs").update(
            {"storyboards": storyboards, "updated_at": datetime.utcnow().isoformat()}
        ).eq("run_id", run_id).execute()

        return {"run_id": run_id, "scene_idx": scene_idx, "scene": scene}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[update_scene] {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 6. POST /projects/{run_id}/images — Generate storyboard images
# ---------------------------------------------------------------------------


@router.post("/projects/{run_id}/images")
async def generate_images(run_id: str, background_tasks: BackgroundTasks, user: AuthUser = Depends(get_current_user)):
    """Start generating images for all storyboard scenes."""
    sb = _require_supabase()

    job_res = (
        sb.table("autoviralvid_jobs")
        .select("run_id")
        .eq("run_id", run_id)
        .limit(1)
        .execute()
    )
    if not job_res.data:
        raise HTTPException(status_code=404, detail=f"Project {run_id} not found")

    sb.table("autoviralvid_jobs").update(
        {"status": "generating_images", "updated_at": datetime.utcnow().isoformat()}
    ).eq("run_id", run_id).execute()

    async def _bg_generate_images():
        try:
            svc = _get_project_service()
            await svc.generate_images(run_id)
        except Exception as exc:
            logger.error(f"[generate_images bg] {exc}", exc_info=True)
            sb.table("autoviralvid_jobs").update(
                {"status": "images_failed", "updated_at": datetime.utcnow().isoformat()}
            ).eq("run_id", run_id).execute()

    background_tasks.add_task(_bg_generate_images)
    return {"run_id": run_id, "status": "generating_images"}


# ---------------------------------------------------------------------------
# 7. POST /projects/{run_id}/images/{scene_idx}/regenerate — Regen one image
# ---------------------------------------------------------------------------


@router.post("/projects/{run_id}/images/{scene_idx}/regenerate")
async def regenerate_image(
    run_id: str,
    scene_idx: int,
    body: RegenerateImageRequest,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
):
    """Regenerate the image for a specific scene."""
    sb = _require_supabase()

    job_res = (
        sb.table("autoviralvid_jobs")
        .select("storyboards")
        .eq("run_id", run_id)
        .single()
        .execute()
    )
    if not job_res.data:
        raise HTTPException(status_code=404, detail=f"Project {run_id} not found")

    storyboards = job_res.data.get("storyboards")
    if not storyboards or scene_idx < 0 or scene_idx >= len(storyboards):
        raise HTTPException(status_code=400, detail="Invalid scene_idx")

    async def _bg_regenerate_image():
        try:
            svc = _get_project_service()
            await svc.regenerate_image(run_id, scene_idx, new_prompt=body.new_prompt)
        except Exception as exc:
            logger.error(f"[regenerate_image bg] {exc}", exc_info=True)

    background_tasks.add_task(_bg_regenerate_image)
    return {"run_id": run_id, "scene_idx": scene_idx, "status": "regenerating_image"}


# ---------------------------------------------------------------------------
# 8. POST /projects/{run_id}/videos — Submit video generation
# ---------------------------------------------------------------------------


@router.post("/projects/{run_id}/videos")
async def submit_videos(run_id: str, background_tasks: BackgroundTasks, user: AuthUser = Depends(get_current_user)):
    """Submit all clips for video generation."""
    sb = _require_supabase()

    job_res = (
        sb.table("autoviralvid_jobs")
        .select("run_id")
        .eq("run_id", run_id)
        .limit(1)
        .execute()
    )
    if not job_res.data:
        raise HTTPException(status_code=404, detail=f"Project {run_id} not found")

    sb.table("autoviralvid_jobs").update(
        {"status": "generating_videos", "updated_at": datetime.utcnow().isoformat()}
    ).eq("run_id", run_id).execute()

    async def _bg_submit_videos():
        try:
            svc = _get_project_service()
            await svc.submit_videos(run_id)
        except Exception as exc:
            logger.error(f"[submit_videos bg] {exc}", exc_info=True)
            sb.table("autoviralvid_jobs").update(
                {"status": "videos_failed", "updated_at": datetime.utcnow().isoformat()}
            ).eq("run_id", run_id).execute()

    background_tasks.add_task(_bg_submit_videos)
    return {"run_id": run_id, "status": "generating_videos"}


# ---------------------------------------------------------------------------
# 8b. POST /projects/{run_id}/digital-human — Submit digital human video
# ---------------------------------------------------------------------------


@router.post("/projects/{run_id}/digital-human")
async def submit_digital_human(run_id: str, background_tasks: BackgroundTasks, user: AuthUser = Depends(get_current_user)):
    """Submit a digital human video generation task.

    This bypasses storyboard/image generation — the user directly provides
    a person image and audio, and the system creates a single video task
    that drives the digital human.
    """
    sb = _require_supabase()

    job_res = (
        sb.table("autoviralvid_jobs")
        .select("run_id")
        .eq("run_id", run_id)
        .limit(1)
        .execute()
    )
    if not job_res.data:
        raise HTTPException(status_code=404, detail=f"Project {run_id} not found")

    _ensure_queue_worker("submit_digital_human")

    sb.table("autoviralvid_jobs").update(
        {"status": "generating_videos", "updated_at": datetime.utcnow().isoformat()}
    ).eq("run_id", run_id).execute()

    async def _bg_submit_dh():
        try:
            logger.info(f"[submit_digital_human bg] Starting for run_id={run_id}")
            svc = _get_project_service()
            result = await svc.submit_digital_human(run_id)
            logger.info(f"[submit_digital_human bg] Result: {result}")

            # submit_digital_human catches its own exceptions and returns
            # [{"error": "..."}] instead of raising — detect that here.
            all_failed = (
                isinstance(result, list)
                and len(result) > 0
                and all(isinstance(r, dict) and "error" in r for r in result)
            )
            if all_failed:
                error_msg = result[0].get("error", "unknown error")
                logger.error(
                    f"[submit_digital_human bg] All tasks failed for "
                    f"run_id={run_id}: {error_msg}"
                )
                sb.table("autoviralvid_jobs").update({
                    "status": "videos_failed",
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("run_id", run_id).execute()
        except Exception as exc:
            logger.error(
                f"[submit_digital_human bg] Unhandled error for "
                f"run_id={run_id}: {exc}",
                exc_info=True,
            )
            sb.table("autoviralvid_jobs").update({
                "status": "videos_failed",
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("run_id", run_id).execute()

    background_tasks.add_task(_bg_submit_dh)
    return {"run_id": run_id, "status": "generating_digital_human"}


# ---------------------------------------------------------------------------
# 9. POST /projects/{run_id}/videos/{clip_idx}/regenerate — Regen one clip
# ---------------------------------------------------------------------------


@router.post("/projects/{run_id}/videos/{clip_idx}/regenerate")
async def regenerate_video(
    run_id: str,
    clip_idx: int,
    body: RegenerateVideoRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Reset a single video task to *pending* so it gets re-processed."""
    sb = _require_supabase()
    try:
        # Find the matching task
        task_res = (
            sb.table("autoviralvid_video_tasks")
            .select("id, status")
            .eq("run_id", run_id)
            .eq("clip_idx", clip_idx)
            .limit(1)
            .execute()
        )
        if not task_res.data:
            raise HTTPException(
                status_code=404,
                detail=f"Video task not found for run_id={run_id}, clip_idx={clip_idx}",
            )

        task = task_res.data[0]
        update_payload: Dict[str, Any] = {
            "status": "pending",
            "provider_task_id": None,
            "video_url": None,
            "error": None,
            "retry_count": 0,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if body.new_prompt is not None:
            update_payload["prompt"] = body.new_prompt

        sb.table("autoviralvid_video_tasks").update(update_payload).eq(
            "id", task["id"]
        ).execute()

        return {
            "run_id": run_id,
            "clip_idx": clip_idx,
            "task_id": task["id"],
            "status": "pending",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[regenerate_video] {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 10. GET /projects/{run_id}/status — Get generation status
# ---------------------------------------------------------------------------


@router.get("/projects/{run_id}/status")
async def get_project_status(run_id: str, user: AuthUser = Depends(get_current_user)):
    """Return detailed generation status with per-task breakdown."""
    sb = _require_supabase()
    _ensure_queue_worker("get_project_status")
    try:
        # Job-level status
        job_res = (
            sb.table("autoviralvid_jobs")
            .select("run_id, status, updated_at, video_url")
            .eq("run_id", run_id)
            .single()
            .execute()
        )
        if not job_res.data:
            raise HTTPException(status_code=404, detail=f"Project {run_id} not found")

        job = job_res.data

        # Task-level breakdown
        tasks_res = (
            sb.table("autoviralvid_video_tasks")
            .select("id, clip_idx, status, video_url, error, retry_count, updated_at")
            .eq("run_id", run_id)
            .order("clip_idx", desc=False)
            .execute()
        )
        tasks = tasks_res.data or []

        # Compute summary counts
        total = len(tasks)
        counts: Dict[str, int] = {}
        for t in tasks:
            s = t.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1

        all_succeeded = total > 0 and counts.get("succeeded", 0) == total
        has_failed = counts.get("failed", 0) > 0

        if all_succeeded and not job.get("video_url") and job.get("status") != "completed":
            try:
                from src.video_task_queue_supabase import (
                    ensure_supabase_queue_worker,
                    get_supabase_queue,
                )

                ensure_supabase_queue_worker("project_status")
                queue = get_supabase_queue()
                if queue:
                    asyncio.create_task(queue.check_and_trigger_stitch(run_id))
                    logger.info(
                        f"[get_project_status] Triggered stitch self-heal for run_id={run_id}"
                    )
            except Exception as stitch_exc:
                logger.warning(
                    f"[get_project_status] Failed to trigger stitch self-heal for {run_id}: {stitch_exc}",
                    exc_info=True,
                )

        # Try to also get service-level status if available
        service_status = None
        try:
            svc = _get_project_service()
            service_status = await svc.get_status(run_id)
        except Exception:
            pass

        return {
            "run_id": run_id,
            "project_status": job.get("status"),
            "updated_at": job.get("updated_at"),
            "tasks_total": total,
            "tasks_summary": counts,
            "all_succeeded": all_succeeded,
            "has_failed": has_failed,
            "tasks": tasks,
            "service_status": service_status,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[get_project_status] {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 11. POST /projects/{run_id}/render — Trigger final render
# ---------------------------------------------------------------------------


@router.post("/projects/{run_id}/render")
async def render_final(run_id: str, background_tasks: BackgroundTasks, user: AuthUser = Depends(get_current_user)):
    """Trigger the final video render (stitch clips, overlay audio, etc.)."""
    sb = _require_supabase()

    job_res = (
        sb.table("autoviralvid_jobs")
        .select("run_id")
        .eq("run_id", run_id)
        .limit(1)
        .execute()
    )
    if not job_res.data:
        raise HTTPException(status_code=404, detail=f"Project {run_id} not found")

    sb.table("autoviralvid_jobs").update(
        {"status": "rendering", "updated_at": datetime.utcnow().isoformat()}
    ).eq("run_id", run_id).execute()

    async def _bg_render():
        try:
            svc = _get_project_service()
            await svc.render_final(run_id)
        except Exception as exc:
            logger.error(f"[render_final bg] {exc}", exc_info=True)
            sb.table("autoviralvid_jobs").update(
                {"status": "render_failed", "updated_at": datetime.utcnow().isoformat()}
            ).eq("run_id", run_id).execute()

    background_tasks.add_task(_bg_render)
    return {"run_id": run_id, "status": "rendering"}


# ---------------------------------------------------------------------------
# 12. POST /projects/batch — Create batch projects
# ---------------------------------------------------------------------------


@router.post("/projects/batch")
async def create_batch(body: BatchCreateRequest, user: AuthUser = Depends(get_current_user)):
    """Create multiple projects from a list of product images."""
    try:
        svc = _get_project_service()
        results = await svc.create_batch(
            template_id=body.template_id,
            product_images=body.product_images,
            params={
                "theme": body.theme,
                "style": body.style,
                "duration": body.duration,
                "orientation": body.orientation,
                "aspect_ratio": body.aspect_ratio,
            },
        )
        return {"projects": results}
    except Exception as exc:
        logger.error(f"[create_batch] {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 13. POST /ai/chat — AI assistant endpoint
# ---------------------------------------------------------------------------

AI_CHAT_MODEL = os.getenv("AI_CHAT_MODEL", "openai/gpt-4o-mini")


@router.post("/ai/chat")
async def ai_chat(body: AIAssistantRequest, user: AuthUser = Depends(get_current_user)):
    """Simple LLM call via OpenRouter for creative assistance."""
    try:
        client = _get_openrouter_client()

        system_prompt = (
            "你是一个专业的短视频创意助手。帮助用户优化视频主题、文案、分镜脚本。"
            "回答简洁实用，直接给出建议。如果用户提供了项目上下文，请参考。"
        )

        messages: List[Dict[str, Any]] = []
        if body.project_context:
            context_str = json.dumps(body.project_context, ensure_ascii=False, default=str)
            messages.append(
                {
                    "role": "system",
                    "content": f"{system_prompt}\n\n当前项目上下文：\n{context_str}",
                }
            )
        else:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": body.message})

        response_text = await client.chat_completions(
            model=AI_CHAT_MODEL,
            messages=messages,
            temperature=0.8,
            max_tokens=1024,
        )

        return {"reply": response_text}
    except Exception as exc:
        logger.error(f"[ai_chat] {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
