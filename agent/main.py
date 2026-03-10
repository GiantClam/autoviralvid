import os
import uuid
import json
import logging
import asyncio
import warnings
import re
import shutil
import subprocess
from pathlib import Path
from threading import Lock
from datetime import datetime
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Depends
from starlette.middleware.cors import CORSMiddleware
import uvicorn
from supabase import create_client

from src.r2 import upload_url_to_r2, presign_put_url
from src.api_routes import router as api_v1_router
from src.auth import get_current_user, AuthUser
from src.rate_limiter import RateLimitMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Literal

_ = load_dotenv()
_ = load_dotenv("../.env.local", override=False)

# 统一日志配置
logger = logging.getLogger("workflow")
logger.setLevel(logging.INFO)

# Supabase 客户端
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv(
    "SUPABASE_SERVICE_KEY"
)
supabase = (
    create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
)


# Lifespan event handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        from src.video_task_queue_supabase import start_supabase_queue_worker

        start_supabase_queue_worker()
        logger.info("[startup] Supabase queue worker started")
    except Exception as e:
        logger.warning(f"[startup] Failed to start Supabase queue worker: {e}")

    yield  # Application runs here

    # Shutdown
    try:
        from src.video_task_queue_supabase import get_supabase_queue

        queue = get_supabase_queue()
        if queue:
            queue.stop()
            logger.info("[shutdown] Supabase queue worker stopped")
    except Exception as e:
        logger.warning(f"[shutdown] Failed to stop Supabase queue worker: {e}")


app = FastAPI(
    title="AutoViralVid API",
    description=(
        "Backend API for AutoViralVid — AI-powered short video creation platform.\n\n"
        "## Key Features\n"
        "- **Project Management**: Create and manage video projects with templates\n"
        "- **AI Storyboard Generation**: Generate storyboards from themes using LLMs\n"
        "- **Digital Human Video**: Drive digital human avatars with audio\n"
        "- **Video Rendering**: Stitch clips, add subtitles, export final video\n"
        "- **File Upload**: Presigned URL upload to Cloudflare R2\n\n"
        "## Authentication\n"
        "Most endpoints require a JWT Bearer token in the `Authorization` header.\n"
        "Obtain a token via the frontend's `/api/auth/api-token` endpoint."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — only allow configured frontend origins (no wildcard in production)
_cors_raw = os.getenv("CORS_ORIGIN", "http://localhost:3000")
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
if not _cors_origins:
    _cors_origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)

# Rate limiting — default 120 requests/minute per IP
_rate_limit_rpm = int(os.getenv("RATE_LIMIT_RPM", "120"))
app.add_middleware(RateLimitMiddleware, rpm=_rate_limit_rpm)

# Register v1 REST API routes (form-driven workflow)
app.include_router(api_v1_router)


# ---------------------------------------------------------------------------
# Global exception handlers — return consistent JSON error envelopes
# ---------------------------------------------------------------------------
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    """Return 422 with a clean, machine-parseable error envelope."""
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        errors.append({"field": loc, "message": err.get("msg", "")})
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "details": errors},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    """Normalise HTTPException into a consistent envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_request: Request, exc: Exception):
    """Catch-all for unhandled server errors — never leak tracebacks."""
    logger.error(f"[unhandled] {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


@app.get("/healthz", tags=["System"], summary="Health check")
async def healthz():
    """Returns `{ok: true}` when the server is running. Used by load balancers and Docker health checks."""
    return {"ok": True}


@app.get("/debug/auth", tags=["System"])
async def debug_auth():
    """Debug endpoint to check auth configuration."""
    from src.auth import AUTH_REQUIRED, _DEV_BYPASS, AUTH_SECRET

    return {
        "AUTH_SECRET": AUTH_SECRET,
        "AUTH_REQUIRED": AUTH_REQUIRED,
        "_DEV_BYPASS": _DEV_BYPASS,
    }


@app.post("/webhook/runninghub")
async def webhook_runninghub(request: Request):
    body = await request.json()
    task_id = body.get("taskId") or body.get("id")
    status = (body.get("status") or "").lower()
    outputs = body.get("outputs") or body.get("result") or []
    if not (supabase and task_id):
        return {"ok": True}

    try:
        # Search in video_tasks (new queue system)
        video_task_result = (
            supabase.table("autoviralvid_video_tasks")
            .select("run_id, clip_idx")
            .eq("provider_task_id", task_id)
            .execute()
        )

        if video_task_result.data:
            task = video_task_result.data[0]
            run_id = task.get("run_id")
            clip_idx = task.get("clip_idx")

            if status in {"success", "finished", "done"}:
                video_url = None
                for item in outputs:
                    url = item.get("fileUrl") or item.get("url") or item.get("ossUrl")
                    if url and isinstance(url, str) and "mp4" in url.lower():
                        video_url = url
                        break

                if video_url:
                    cdn_url = await upload_url_to_r2(
                        video_url, f"{run_id}_clip{clip_idx}.mp4"
                    )
                    supabase.table("autoviralvid_video_tasks").update(
                        {
                            "status": "succeeded",
                            "video_url": cdn_url,
                            "updated_at": datetime.utcnow().isoformat(),
                        }
                    ).eq("provider_task_id", task_id).execute()
                    logger.info(
                        f"[webhook_runninghub] Task {task_id} completed: {cdn_url}"
                    )
    except Exception as e:
        logger.error(f"[webhook_runninghub] Error: {e}")

    return {"ok": True}


@app.get("/agent/session/{run_id}")
async def get_agent_session(run_id: str, user: AuthUser = Depends(get_current_user)):
    if not supabase:
        return {"error": "Supabase not configured"}
    try:
        res = (
            supabase.table("autoviralvid_crew_sessions")
            .select("*")
            .eq("run_id", run_id)
            .execute()
        )
        if res.data:
            return res.data[0]

        job_res = (
            supabase.table("autoviralvid_jobs")
            .select("*")
            .eq("run_id", run_id)
            .execute()
        )
        if job_res.data:
            job = job_res.data[0]
            tasks_res = (
                supabase.table("autoviralvid_video_tasks")
                .select("*")
                .eq("run_id", run_id)
                .execute()
            )
            job["context"] = {
                "storyboard": job.get("storyboards"),
                "video_tasks": tasks_res.data or [],
            }
            return job
        return {"error": "Session not found"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/agent/sessions")
async def list_agent_sessions(
    limit: int = 40, user: AuthUser = Depends(get_current_user)
):
    if not supabase:
        return {"workflows": []}
    try:
        jobs_res = (
            supabase.table("autoviralvid_jobs")
            .select("run_id, created_at, slogan, status")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        crew_res = (
            supabase.table("autoviralvid_crew_sessions")
            .select("run_id, created_at, status, context")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        merged_map = {}
        for item in crew_res.data or []:
            rid = item.get("run_id")
            if rid:
                topic = (
                    (item.get("context") or {}).get("collected_info", {}).get("topic")
                    or item.get("status")
                    or "Agent Session"
                )
                merged_map[rid] = {
                    "run_id": rid,
                    "created_at": item.get("created_at"),
                    "video_topic": topic,
                    "status": item.get("status"),
                }

        for item in jobs_res.data or []:
            rid = item.get("run_id")
            if rid:
                merged_map[rid] = {
                    "run_id": rid,
                    "created_at": item.get("created_at"),
                    "video_topic": item.get("slogan")
                    or merged_map.get(rid, {}).get("video_topic", "New Job"),
                    "status": item.get("status"),
                }

        workflows = sorted(
            merged_map.values(), key=lambda x: x.get("created_at") or "", reverse=True
        )[:limit]
        return {"workflows": workflows}
    except Exception:
        return {"workflows": []}


# --- Upload security constants ---
ALLOWED_UPLOAD_TYPES = {
    # Images
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    # Audio
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/aac",
    "audio/m4a",
    "audio/x-m4a",
    # Generic fallback (frontend may send this)
    "application/octet-stream",
}
MAX_FILENAME_LENGTH = 255


class UploadPresignRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"


@app.post("/upload/presign")
async def upload_presign(
    body: UploadPresignRequest, user: AuthUser = Depends(get_current_user)
):
    # --- Validate filename ---
    clean_name = (
        body.filename.strip().replace("..", "").replace("/", "_").replace("\\", "_")
    )
    if not clean_name or len(clean_name) > MAX_FILENAME_LENGTH:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # --- Validate content type ---
    if body.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {body.content_type}",
        )

    try:
        key = f"uploads/{uuid.uuid4().hex[:8]}_{clean_name}"
        res = presign_put_url(key=key, content_type=body.content_type)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------
# Video task management endpoints
# ------------------------------


class RegenerateRequest(BaseModel):
    clip_idx: int
    new_prompt: Optional[str] = None


@app.get("/jobs/{run_id}/tasks")
async def get_tasks_for_run(run_id: str, user: AuthUser = Depends(get_current_user)):
    """Get all video tasks for a given run_id, ordered by clip_idx."""
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    try:
        result = (
            supabase.table("autoviralvid_video_tasks")
            .select("*")
            .eq("run_id", run_id)
            .order("clip_idx", desc=False)
            .execute()
        )
        tasks = result.data or []
        # Compute summary counts
        total = len(tasks)
        succeeded = len([t for t in tasks if t.get("status") == "succeeded"])
        pending = len(
            [
                t
                for t in tasks
                if t.get("status") in ("pending", "processing", "submitted")
            ]
        )
        failed = len([t for t in tasks if t.get("status") == "failed"])
        return {
            "run_id": run_id,
            "tasks": tasks,
            "summary": {
                "total": total,
                "succeeded": succeeded,
                "pending": pending,
                "failed": failed,
                "all_done": succeeded == total and total > 0,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/jobs/{run_id}/regenerate")
async def regenerate_clip(
    run_id: str, body: RegenerateRequest, user: AuthUser = Depends(get_current_user)
):
    """
    Regenerate a specific clip by resetting its task to 'pending'.
    If new_prompt is provided, update the prompt as well.
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    try:
        # Find the task for this clip
        result = (
            supabase.table("autoviralvid_video_tasks")
            .select("*")
            .eq("run_id", run_id)
            .eq("clip_idx", body.clip_idx)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=404, detail=f"No task found for clip_idx={body.clip_idx}"
            )

        task = result.data[0]
        task_id = task.get("id")

        # Build update payload
        update = {
            "status": "pending",
            "provider_task_id": None,
            "video_url": None,
            "error": None,
            "retry_count": 0,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if body.new_prompt:
            update["prompt"] = body.new_prompt

        supabase.table("autoviralvid_video_tasks").update(update).eq(
            "id", task_id
        ).execute()

        logger.info(
            f"[regenerate] Clip {body.clip_idx} for run {run_id} reset to pending"
        )
        return {
            "status": "regenerating",
            "run_id": run_id,
            "clip_idx": body.clip_idx,
            "message": f"Clip {body.clip_idx} has been queued for regeneration",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/jobs/{run_id}/stitch")
async def stitch_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
):
    """
    Trigger video stitching for all completed clips of a run.
    Returns immediately; the stitch runs in background.
    """
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # Check that all tasks are done
    result = (
        supabase.table("autoviralvid_video_tasks")
        .select("status")
        .eq("run_id", run_id)
        .execute()
    )

    tasks = result.data or []
    if not tasks:
        raise HTTPException(status_code=404, detail="No tasks found for this run")

    not_done = [t for t in tasks if t.get("status") != "succeeded"]
    if not_done:
        raise HTTPException(
            status_code=400,
            detail=f"{len(not_done)} clips are not yet completed. Wait for all clips to finish.",
        )

    async def _do_stitch():
        try:
            from src.video_stitcher import stitch_videos_for_run

            final_url = await stitch_videos_for_run(run_id)
            logger.info(f"[stitch] Run {run_id} stitched: {final_url}")
        except Exception as e:
            logger.error(f"[stitch] Failed for run {run_id}: {e}", exc_info=True)

    background_tasks.add_task(_do_stitch)

    return {
        "status": "stitching",
        "run_id": run_id,
        "message": f"Stitching {len(tasks)} clips in background",
    }


# ------------------------------
# FFmpeg renderer service
# ------------------------------
RENDER_OUTPUT_DIR = Path(
    os.getenv("RENDER_OUTPUT_DIR", str(Path(os.getcwd()) / "renders"))
).resolve()
RENDER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RENDER_JOBS: Dict[str, Dict[str, Any]] = {}
RENDER_JOBS_LOCK = Lock()


class RenderLayerStyle(BaseModel):
    fontSize: Optional[float] = None
    color: Optional[str] = None
    backgroundColor: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    opacity: Optional[float] = None
    rotation: Optional[float] = None
    scale: Optional[float] = None


class RenderLayer(BaseModel):
    id: str
    itemType: str = "video"
    type: Literal["video", "image", "text"]
    trackId: int = 0
    name: str = ""
    source: Optional[str] = None
    text: Optional[str] = None
    startFrame: int
    durationInFrames: int
    style: Optional[RenderLayerStyle] = None


class RenderAudioTrack(BaseModel):
    id: str
    trackId: int = 0
    name: str = ""
    source: str
    startFrame: int
    durationInFrames: int
    volume: float = 1.0


class RenderComposition(BaseModel):
    id: str
    width: int
    height: int
    fps: int = 30
    durationInFrames: int
    backgroundColor: str = "#000000"
    layers: List[RenderLayer] = Field(default_factory=list)
    audioTracks: List[RenderAudioTrack] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RenderProjectInfo(BaseModel):
    name: str
    runId: Optional[str] = None
    threadId: Optional[str] = None


class RenderJobRequest(BaseModel):
    engine: str = "remotion"
    project: RenderProjectInfo
    composition: RenderComposition


def _sanitize_filename(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "_", (value or "").strip())
    return text[:80] if text else "render"


def _to_seconds(frame_count: int, fps: int) -> float:
    safe_fps = max(1, int(fps))
    return max(0.0, float(frame_count) / float(safe_fps))


def _escape_drawtext_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    escaped = escaped.replace("%", "\\%").replace("\n", "\\n")
    return escaped


def _ffmpeg_color(color: str) -> str:
    raw = (color or "").strip()
    if not raw:
        return "black"
    if raw.startswith("#") and len(raw) == 7:
        return f"0x{raw[1:]}"
    return raw


def _set_render_job(job_id: str, **updates):
    with RENDER_JOBS_LOCK:
        if job_id not in RENDER_JOBS:
            RENDER_JOBS[job_id] = {}
        RENDER_JOBS[job_id].update(updates)


def _render_summary(payload: RenderJobRequest) -> Dict[str, Any]:
    comp = payload.composition
    fps = max(1, int(comp.fps))
    return {
        "fps": fps,
        "durationInFrames": comp.durationInFrames,
        "durationSeconds": float(comp.durationInFrames) / float(fps),
        "layerCount": len(comp.layers),
        "audioTrackCount": len(comp.audioTracks),
    }


def _build_ffmpeg_command(payload: RenderJobRequest, output_path: Path) -> List[str]:
    comp = payload.composition
    fps = max(1, int(comp.fps))
    width = max(16, int(comp.width))
    height = max(16, int(comp.height))
    total_seconds = max(0.1, _to_seconds(comp.durationInFrames, fps))

    cmd: List[str] = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={_ffmpeg_color(comp.backgroundColor)}:s={width}x{height}:r={fps}:d={total_seconds:.3f}",
    ]

    visual_inputs: List[tuple[RenderLayer, int]] = []
    audio_inputs: List[tuple[RenderAudioTrack, int]] = []
    input_index = 1

    visual_layers = sorted(
        [
            layer
            for layer in comp.layers
            if layer.type in {"video", "image"} and layer.source
        ],
        key=lambda x: (x.trackId, x.startFrame, x.id),
    )
    for layer in visual_layers:
        source = str(layer.source).strip()
        if layer.type == "image":
            cmd.extend(["-loop", "1", "-i", source])
        else:
            cmd.extend(["-i", source])
        visual_inputs.append((layer, input_index))
        input_index += 1

    for track in sorted(
        comp.audioTracks, key=lambda x: (x.trackId, x.startFrame, x.id)
    ):
        source = str(track.source).strip()
        if not source:
            continue
        cmd.extend(["-i", source])
        audio_inputs.append((track, input_index))
        input_index += 1

    filters: List[str] = ["[0:v]format=yuv420p[v0]"]
    current_video = "v0"
    overlay_index = 0

    for layer, idx in visual_inputs:
        start_s = _to_seconds(layer.startFrame, fps)
        dur_s = max(0.033, _to_seconds(layer.durationInFrames, fps))
        end_s = start_s + dur_s
        src_label = f"vs{overlay_index}"
        next_label = f"v{overlay_index + 1}"
        filters.append(
            f"[{idx}:v]scale={width}:{height},format=rgba,trim=duration={dur_s:.3f},"
            f"setpts=PTS-STARTPTS+{start_s:.3f}/TB[{src_label}]"
        )
        filters.append(
            f"[{current_video}][{src_label}]overlay=x=0:y=0:eof_action=pass:"
            f"enable='between(t,{start_s:.3f},{end_s:.3f})'[{next_label}]"
        )
        current_video = next_label
        overlay_index += 1

    text_layers = sorted(
        [layer for layer in comp.layers if layer.type == "text" and layer.text],
        key=lambda x: (x.trackId, x.startFrame, x.id),
    )
    text_index = 0
    for layer in text_layers:
        text_value = str(layer.text or "").strip()
        if not text_value:
            continue
        style = layer.style or RenderLayerStyle()
        font_size = max(8, int(style.fontSize or 42))
        font_color = (style.color or "white").strip() or "white"
        x_pct = float(style.x if style.x is not None else 50.0) / 100.0
        y_pct = float(style.y if style.y is not None else 85.0) / 100.0
        x_expr = f"(w-text_w)*{x_pct:.4f}"
        y_expr = f"(h-text_h)*{y_pct:.4f}"
        start_s = _to_seconds(layer.startFrame, fps)
        end_s = start_s + max(0.033, _to_seconds(layer.durationInFrames, fps))
        escaped_text = _escape_drawtext_value(text_value)
        next_label = f"vt{text_index}_{overlay_index}"
        drawtext = (
            f"[{current_video}]drawtext=text='{escaped_text}':fontcolor={font_color}:"
            f"fontsize={font_size}:x={x_expr}:y={y_expr}:"
            f"enable='between(t,{start_s:.3f},{end_s:.3f})'"
        )
        if style.backgroundColor:
            drawtext += f":box=1:boxcolor={_ffmpeg_color(style.backgroundColor)}@0.45:boxborderw=8"
        drawtext += f"[{next_label}]"
        filters.append(drawtext)
        current_video = next_label
        text_index += 1

    has_audio = len(audio_inputs) > 0
    if has_audio:
        a_labels: List[str] = []
        for a_idx, (track, input_id) in enumerate(audio_inputs):
            start_s = _to_seconds(track.startFrame, fps)
            dur_s = max(0.033, _to_seconds(track.durationInFrames, fps))
            volume = max(0.0, float(track.volume))
            a_label = f"a{a_idx}"
            filters.append(
                f"[{input_id}:a]atrim=duration={dur_s:.3f},asetpts=PTS-STARTPTS+{start_s:.3f}/TB,"
                f"volume={volume:.3f}[{a_label}]"
            )
            a_labels.append(f"[{a_label}]")
        if len(a_labels) == 1:
            filters.append(f"{a_labels[0]}anull[afinal]")
        else:
            filters.append(
                f"{''.join(a_labels)}amix=inputs={len(a_labels)}:normalize=0:dropout_transition=0[afinal]"
            )

    cmd.extend(["-filter_complex", ";".join(filters)])
    cmd.extend(["-map", f"[{current_video}]"])
    if has_audio:
        cmd.extend(["-map", "[afinal]", "-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.append("-an")
    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            os.getenv("RENDER_FFMPEG_PRESET", "veryfast"),
            "-crf",
            os.getenv("RENDER_FFMPEG_CRF", "20"),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return cmd


async def _run_render_job(job_id: str, payload: RenderJobRequest):
    try:
        started_at = datetime.utcnow().isoformat()
        _set_render_job(job_id, status="running", started_at=started_at)

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            _set_render_job(
                job_id,
                status="failed",
                finished_at=datetime.utcnow().isoformat(),
                error="ffmpeg not found in PATH",
            )
            return

        output_dir = RENDER_OUTPUT_DIR / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_project_name = _sanitize_filename(payload.project.name)
        output_file = output_dir / f"{safe_project_name}_{job_id}.mp4"
        request_file = output_dir / "request.json"
        log_file = output_dir / "ffmpeg.log"

        request_file.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
        cmd = _build_ffmpeg_command(payload, output_file)
        cmd[0] = ffmpeg_path

        logger.info(f"[renderer] Starting job {job_id} with ffmpeg")
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        stderr_text = result.stderr or ""
        stdout_text = result.stdout or ""
        log_file.write_text(
            f"STDOUT\n{stdout_text}\n\nSTDERR\n{stderr_text}", encoding="utf-8"
        )

        if result.returncode != 0 or not output_file.exists():
            _set_render_job(
                job_id,
                status="failed",
                finished_at=datetime.utcnow().isoformat(),
                error=f"ffmpeg failed (code={result.returncode}). Check {log_file}",
                ffmpeg_stderr_tail=stderr_text[-1200:],
            )
            return

        uploaded_url = None
        try:
            run_id = payload.project.runId or job_id
            upload_key = f"renders/{_sanitize_filename(run_id)}/{output_file.name}"
            uploaded_url = await upload_url_to_r2(
                f"file://{output_file.as_posix()}", upload_key
            )
        except Exception as upload_error:
            logger.warning(f"[renderer] Upload failed for job {job_id}: {upload_error}")

        _set_render_job(
            job_id,
            status="completed",
            finished_at=datetime.utcnow().isoformat(),
            output_path=str(output_file),
            output_url=uploaded_url,
            log_path=str(log_file),
        )
    except Exception as job_error:
        _set_render_job(
            job_id,
            status="failed",
            finished_at=datetime.utcnow().isoformat(),
            error=f"renderer job exception: {job_error}",
        )


@app.get("/render/health")
async def render_health():
    ffmpeg_path = shutil.which("ffmpeg")
    return {
        "ok": True,
        "service": "ffmpeg-renderer",
        "ffmpeg_available": bool(ffmpeg_path),
        "ffmpeg_path": ffmpeg_path,
        "output_dir": str(RENDER_OUTPUT_DIR),
    }


@app.post("/render/jobs")
async def create_render_job(
    payload: RenderJobRequest,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
):
    invalid_sources = []
    for layer in payload.composition.layers:
        if layer.source and str(layer.source).startswith("blob:"):
            invalid_sources.append(layer.source)
    for track in payload.composition.audioTracks:
        if track.source and str(track.source).startswith("blob:"):
            invalid_sources.append(track.source)
    if invalid_sources:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Render payload contains browser blob URLs. Upload assets to a public URL first.",
                "invalid_sources": invalid_sources[:5],
            },
        )

    job_id = f"render_{uuid.uuid4().hex[:12]}"
    created_at = datetime.utcnow().isoformat()
    _set_render_job(
        job_id,
        status="queued",
        created_at=created_at,
        request=payload.model_dump(),
        summary=_render_summary(payload),
    )

    background_tasks.add_task(_run_render_job, job_id, payload)

    return {
        "status": "accepted",
        "mode": "ffmpeg",
        "job_id": job_id,
        "created_at": created_at,
        "summary": _render_summary(payload),
    }


@app.get("/render/jobs/{job_id}")
async def get_render_job(job_id: str, user: AuthUser = Depends(get_current_user)):
    with RENDER_JOBS_LOCK:
        data = RENDER_JOBS.get(job_id)
    if not data:
        return {"error": "Render job not found", "job_id": job_id}
    return {"job_id": job_id, **data}


@app.get("/render/jobs")
async def list_render_jobs(limit: int = 20, user: AuthUser = Depends(get_current_user)):
    with RENDER_JOBS_LOCK:
        items = list(RENDER_JOBS.items())
    items = sorted(items, key=lambda x: (x[1].get("created_at") or ""), reverse=True)
    output = [
        {"job_id": job_id, **data} for job_id, data in items[: max(1, min(limit, 200))]
    ]
    return {"jobs": output}


def main():
    """Run the uvicorn server."""
    port = int(os.getenv("PORT", "8123"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )


warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
if __name__ == "__main__":
    main()
