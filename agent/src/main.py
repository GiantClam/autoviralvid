import os
import json
import uuid
import asyncio
from datetime import datetime
import random
import re
from dotenv import load_dotenv
import os
import logging
import sys
from logging.handlers import RotatingFileHandler

# 首先加载 .env 文件，确保后续导入的模块能读取环境变量
# 优先查找当前目录 apps/agent/.env，如果不存在则查找项目根目录 .env
local_env = os.path.join(os.path.dirname(__file__), '.env')
root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))

if os.path.exists(local_env):
    load_dotenv(dotenv_path=local_env)
    print(f"[main] Loaded .env from {local_env}")
elif os.path.exists(root_env):
    load_dotenv(dotenv_path=root_env)
    print(f"[main] Loaded .env from {root_env}")
else:
    load_dotenv() # Fallback to default search
    print("[main] Warning: No specific .env found, used default search")

# DEBUG: Verify Env loading
print(f"[main] DEBUG: PROVIDER_IMAGE = {os.getenv('PROVIDER_IMAGE')}")
print(f"[main] DEBUG: RUNNINGHUB_API_KEY IS SET = {bool(os.getenv('RUNNINGHUB_API_KEY'))}")
print(f"[main] DEBUG: RUNNINGHUB_IMAGE_WORKFLOW_ID = {os.getenv('RUNNINGHUB_IMAGE_WORKFLOW_ID')}")

# Add current directory to sys.path to support running as a script
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request, UploadFile, File
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from supabase import create_client
import httpx

# Use absolute imports since we added the directory to sys.path
from providers import get_image_provider, get_video_provider
from r2 import upload_url_to_r2, presign_put_url
from openrouter_client import OpenRouterClient

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Tuple

from langgraph_workflow import start_video_generation, get_workflow_app
from agent_skills import plan_storyboard_impl, generate_video_clip_impl
from agent_skills import synthesize_voice_impl, synthesize_bgm_impl
# Import JobManager
from job_manager import job_manager

from langchain_core.messages import HumanMessage, AIMessage
import logging

# [NEW] CopilotKit Imports (Official Approach)
from copilotkit import LangGraphAGUIAgent
from ag_ui_langgraph import add_langgraph_fastapi_endpoint

# [NEW] Monkeypatch LangGraphAGUIAgent to include dict_repr if missing
if not hasattr(LangGraphAGUIAgent, "dict_repr"):
    def dict_repr(self):
        return {
            "name": self.name,
            "description": self.description,
            "type": "langgraph",
        }
    LangGraphAGUIAgent.dict_repr = dict_repr
    print("[main] Monkeypatched LangGraphAGUIAgent.dict_repr")

logger = logging.getLogger("workflow")


# 事件编码（简化版，与 AG-UI 兼容的数据结构）


# encode_event removed

load_dotenv()
app = FastAPI()

# 应用启动时启动 Supabase 队列 worker
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化配置验证、Supabase 队列 worker 和 Skills Registry"""
    # Validate configuration
    try:
        from configs.settings import validate_config, get_config
        is_valid, errors = validate_config()
        config = get_config()

        if errors:
            for error in errors:
                logger.warning(f"[startup] Config warning: {error}")

        logger.info(
            f"[startup] Configuration loaded: "
            f"poll_interval={config.video_queue.poll_interval_seconds}s, "
            f"max_concurrent={config.video_queue.max_concurrent_tasks}, "
            f"clip_duration={config.workflow.default_clip_duration}s"
        )
    except ImportError as e:
        logger.debug(f"[startup] Config module not available: {e}")
    except Exception as e:
        logger.warning(f"[startup] Config validation failed: {e}")

    # Initialize Skills Registry
    try:
        from src.skills import get_skills_registry
        registry = await get_skills_registry()
        skills_count = len(registry.list_all_skills())
        enabled_count = len(registry.get_enabled_skills())
        logger.info(f"[startup] Skills Registry initialized: {enabled_count}/{skills_count} skills enabled")

        # Log available skills for debugging
        for skill in registry.get_enabled_skills():
            logger.debug(f"[startup]   - {skill.name} ({skill.category.value}): priority={skill.priority}")
    except ImportError as e:
        logger.warning(f"[startup] Skills module not available: {e}")
    except Exception as e:
        logger.warning(f"[startup] Failed to initialize Skills Registry: {e}")

    # Start Supabase queue worker
    try:
        try:
            from video_task_queue_supabase import start_supabase_queue_worker
        except ImportError:
            from video_task_queue_supabase import start_supabase_queue_worker
        start_supabase_queue_worker()
    except Exception as e:
        logger.warning(f"[startup] Failed to start Supabase queue worker: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时停止 Supabase 队列 worker"""
    try:
        try:
            from video_task_queue_supabase import get_supabase_queue
        except ImportError:
            # Fallback if needed, though with sys.path hack it should work
            from video_task_queue_supabase import get_supabase_queue
        
        queue = get_supabase_queue()
        if queue:
            queue.stop()
            # 等待 worker 任务完成取消（最多等待 2 秒）
            if queue._worker_task and not queue._worker_task.done():
                try:
                    await asyncio.wait_for(queue._worker_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    # 任务被取消或超时是正常的，忽略这些错误
                    pass
            logger.info("[shutdown] Supabase queue worker stopped")
    except asyncio.CancelledError:
        # 在 shutdown 期间，CancelledError 是正常的，不需要记录
        pass
    except Exception as e:
        logger.warning(f"[shutdown] Failed to stop Supabase queue worker: {e}")

# CORS 允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGIN", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Vercel-AI-Data-Stream"],
)

# Initialize CopilotKit via official ag_ui_langgraph endpoint
try:
    graph_app = get_workflow_app()
    if graph_app is None:
        logger.error("[main] get_workflow_app() returned None!")
    else:
        logger.info(f"[main] Initializing CopilotKit SDK with graph type: {type(graph_app)}")
    
    agent = LangGraphAGUIAgent(
        name="video_gen",
        description="Agent for generating videos",
        graph=graph_app,
    )
    # [FIX] Ensure messages_in_process is initialized to avoid TypeError
    agent.messages_in_process = {}
    
    add_langgraph_fastapi_endpoint(
        app=app,
        agent=agent,
        path="/", # Use root path to match with-langgraph-fastapi
    )
    logger.info("[main] CopilotKit endpoint added at / using ag_ui_langgraph")
except Exception as e:
    logger.exception(f"[main] Failed to initialize CopilotKit: {e}")
    # Fallback or re-raise
    raise

@app.get("/healthz")
async def healthz():
    return {"ok": True}

# 统一日志配置（stdout + 文件），确保 Railway 上可查看
def _configure_logging():
    logger = logging.getLogger()
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    # stdout
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    # 文件
    import os as _os
    # 本地开发环境下，默认在当前目录创建 logs 文件夹，而非根目录 /app/logs
    log_dir = _os.getenv("LOG_DIR", _os.path.join(_os.getcwd(), "logs"))
    try:
        _os.makedirs(log_dir, exist_ok=True)
        log_file = _os.path.join(log_dir, "app.log")
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        print(f"[main] Logging initialized. File: {log_file}")
    except Exception as e:
        print(f"[main] Warning: Failed to initialize file logging in {log_dir}: {e}")
        pass

_configure_logging()
logger = logging.getLogger("workflow")

# Supabase 客户端（可选）
# 后端服务应使用 SERVICE_ROLE_KEY 以绕过 RLS 策略
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY") 
    or os.getenv("SUPABASE_SERVICE_KEY") 
    or os.getenv("SUPABASE_ANON_KEY")
)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
# OpenRouter 配置（统一管理不同模型服务商）- 优先使用 OPENROUTER_*，兼容旧变量
OPENROUTER_BASE = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBED_REFERER = os.getenv("EMBEDDING_REFERER", os.getenv("SITE_URL", "https://saleagent.app"))
PROMPT_LLM_MODEL = os.getenv("PROMPT_LLM_MODEL", "kimi/k2-think")
CF_WORKER_NOTIFY_URL = os.getenv("CF_WORKER_NOTIFY_URL")
CF_NOTIFY_TOKEN = os.getenv("CF_NOTIFY_TOKEN")


# CrewAI environment shim removed


# Legacy emit, simulate_video, events removed.

# ======================
# 工作流编排 REST 接口
# ======================






# update_scene removed



# confirm_storyboard removed



# regenerate_scene removed




# run_agent removed


@app.post("/webhook/runninghub")
async def webhook_runninghub(request: Request):
    body = await request.json()
    task_id = body.get("taskId") or body.get("id")
    status = (body.get("status") or "").lower()
    outputs = body.get("outputs") or body.get("result") or []
    if not (supabase and task_id):
        return {"ok": True}
    
    # 优先从 video_tasks 表查找（新的队列系统）
    video_task = None
    try:
        # 先尝试用 provider_task_id 查找
        video_task_result = supabase.table("autoviralvid_video_tasks")\
            .select("run_id, clip_idx")\
            .eq("provider_task_id", task_id)\
            .single()\
            .execute()
        if video_task_result.data:
            video_task = video_task_result.data
        else:
            # 如果没找到，尝试用 id 查找（可能是直接提交的任务，provider_task_id 可能还没设置）
            video_task_result = supabase.table("autoviralvid_video_tasks")\
                .select("run_id, clip_idx, provider_task_id")\
                .eq("id", task_id)\
                .single()\
                .execute()
            if video_task_result.data:
                video_task = video_task_result.data
    except Exception as e:
        logger.debug(f"[webhook_runninghub] Error finding video_task: {e}")
        pass
    
    # 如果找到 video_task，使用新的队列系统处理
    if video_task:
        run_id = video_task.get("run_id")
        clip_idx = video_task.get("clip_idx")
        
        if status in {"success", "finished", "done"}:
            # 获取视频 URL
            video_url = None
            for item in outputs:
                url = (
                    item.get("fileUrl") 
                    or item.get("url") 
                    or item.get("ossUrl") 
                    or item.get("downloadUrl")
                    or (item.get("value") if isinstance(item.get("value"), str) else None)
                )
                ftype = (item.get("fileType") or item.get("type") or "").lower()
                if url and isinstance(url, str):
                    url_lower = url.lower()
                    if (
                        "mp4" in url_lower 
                        or url_lower.endswith(".mp4")
                        or ftype in {"mp4", "video", "video/mp4"}
                    ):
                        video_url = url
                        break
            
            if video_url:
                # 上传到 R2
                cdn_url = await upload_url_to_r2(video_url, f"{run_id}_clip{clip_idx}.mp4")
                
                # 更新 video_tasks 表
                supabase.table("autoviralvid_video_tasks")\
                    .update({
                        "status": "succeeded",
                        "video_url": cdn_url,
                        "updated_at": datetime.utcnow().isoformat()
                    })\
                    .eq("provider_task_id", task_id)\
                    .execute()
                
                logger.info(f"[webhook_runninghub] Video task {task_id} completed: {cdn_url}")
                

                # check_and_trigger_stitch skipped; handled by polling in LangGraph
        
        return {"ok": True}
    
    # 降级：使用旧的 jobs 表查找（兼容旧系统）
    job = supabase.table("autoviralvid_jobs").select("run_id, slogan, cover_url").eq("provider_task_id", task_id).single().execute()
    if not job or not job.data:
        return {"ok": True}
    run_id = job.data.get("run_id")
    slogan = job.data.get("slogan")
    cover_url = job.data.get("cover_url")
    # 成功则获取视频链接
    video_url = None
    if status in {"success", "finished", "done"}:
        for item in outputs:
            url = item.get("fileUrl") or item.get("url")
            ftype = (item.get("fileType") or "").lower()
            if url and ("mp4" in url or ftype in {"mp4", "video"}):
                video_url = url
                break
    if video_url:
        cdn_url = await upload_url_to_r2(video_url, f"{run_id}.mp4")
        await persist_success(run_id, slogan or "", cover_url or "", cdn_url)
        j = supabase.table("autoviralvid_jobs").select("user_id").eq("run_id", run_id).single().execute()
        user_id = (j.data or {}).get("user_id") if j and j.data else None
        email = None
        if user_id:
            u = supabase.table("autoviralvid_users").select("email").eq("id", user_id).single().execute()
            email = (u.data or {}).get("email") if u and u.data else None
            if not email:
                p = supabase.table("autoviralvid_profiles").select("email").eq("id", user_id).single().execute()
                email = (p.data or {}).get("email") if p and p.data else None
        await send_email(email, "视频生成完成", f"您的视频已生成：{cdn_url}", f"<p>您的视频已生成：<a href='{cdn_url}'>{cdn_url}</a></p>")
    else:
        await persist_failure(run_id, status or "failed")
        j = supabase.table("autoviralvid_jobs").select("user_id").eq("run_id", run_id).single().execute()
        user_id = (j.data or {}).get("user_id") if j and j.data else None
        email = None
        if user_id:
            u = supabase.table("autoviralvid_users").select("email").eq("id", user_id).single().execute()
            email = (u.data or {}).get("email") if u and u.data else None
            if not email:
                p = supabase.table("autoviralvid_profiles").select("email").eq("id", user_id).single().execute()
                email = (p.data or {}).get("email") if p and p.data else None
        await send_email(email, "视频生成失败", f"任务 {run_id} 失败：{status}")
    return {"ok": True}


@app.get("/public-jobs")
async def public_jobs(page: int = 1, limit: int = 20, q: str | None = None):
    if not supabase:
        # 未配置 Supabase，返回占位数据
        return [{
            "share_slug": "demo",
            "slogan": "示例作业",
            "cover_url": "https://picsum.photos/seed/demo/800/450",
            "video_url": "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
            "created_at": datetime.utcnow().isoformat()
        }]
    query = supabase.table("autoviralvid_jobs").select("run_id, slogan, cover_url, video_url, share_slug, created_at").not_.is_("share_slug", None)
    if q:
        query = query.ilike("slogan", f"%{q}%")
    res = query.order("created_at", desc=True).range((page-1)*limit, (page-1)*limit + limit - 1).execute()
    return res.data or []


@app.get("/my-jobs")
async def my_jobs(user_id: str, page: int = 1, limit: int = 20):
    if not supabase:
        return []
    res = supabase.table("autoviralvid_jobs").select("run_id, slogan, cover_url, video_url, share_slug, status, created_at").eq("user_id", user_id).order("created_at", desc=True).range((page-1)*limit, (page-1)*limit + limit - 1).execute()
    return res.data or []


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip()).strip("-").lower()
    suffix = (uuid.uuid4().hex)[:6]
    return (text[:12] + "-" + suffix) if text else ("j-" + suffix)


async def persist_success(run_id: str, slogan: str, cover_url: str, video_url: str) -> str | None:
    if not supabase:
        return None
    share_slug = _slugify(slogan or run_id)
    # 计算并写入 embedding（用于后续相似推荐）
    embedding = await _get_embedding(slogan or "")
    supabase.table("autoviralvid_jobs").upsert({
        "run_id": run_id,
        "slogan": slogan,
        "cover_url": cover_url,
        "video_url": video_url,
        "status": "succeeded",
        "share_slug": share_slug,
        "updated_at": datetime.utcnow().isoformat()
    }, on_conflict="run_id").execute()
    try:
        if embedding:
            # 将本次 slogan 作为模板候选写入 prompts_library（去重按标题）
            supabase.table("autoviralvid_prompts_library").upsert({
                "title": slogan[:200],
                "prompt": slogan,
                "embedding": embedding,
                "cover_url": cover_url,
                "category": None
            }, on_conflict="title").execute()
    except Exception:
        pass
    return share_slug


async def persist_failure(run_id: str, error: str):
    if not supabase:
        return
    supabase.table("autoviralvid_jobs").upsert({
        "run_id": run_id,
        "status": "failed",
        "updated_at": datetime.utcnow().isoformat()
    }, on_conflict="run_id").execute()


async def send_email(to: str | None, subject: str, text: str, html: str | None = None):
    if not (to and CF_WORKER_NOTIFY_URL and CF_NOTIFY_TOKEN):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                CF_WORKER_NOTIFY_URL,
                headers={"x-signature": CF_NOTIFY_TOKEN, "content-type": "application/json"},
                json={"to": to, "subject": subject, "text": text, "html": html},
            )
    except Exception:
        pass


@app.post("/jobs")
async def create_job(request: Request):
    if not supabase:
        return {"error": "Supabase not configured"}
    body = await request.json()
    slogan = (body.get("slogan") or "").strip()
    user_id = body.get("user_id") or None
    run_id = body.get("run_id") or f"r_{uuid.uuid4().hex[:8]}"
    share_slug = _slugify(slogan or run_id)
    supabase.table("autoviralvid_jobs").insert({
        "run_id": run_id,
        "slogan": slogan,
        "status": "running",
        "user_id": user_id,
        "share_slug": share_slug
    }).execute()
    return {"run_id": run_id, "share_slug": share_slug}


@app.get("/jobs/{run_id}")
async def get_job(run_id: str):
    if not supabase:
        return {"error": "Supabase not configured"}
    res = supabase.table("autoviralvid_jobs").select("run_id, slogan, cover_url, video_url, share_slug, status, storyboards, total_duration, styles, image_control, created_at, updated_at").eq("run_id", run_id).single().execute()
    return res.data or {}


@app.post("/jobs/{run_id}/retry")
async def retry_job(run_id: str):
    if not supabase:
        return {"error": "Supabase not configured"}
    
    # 1. 获取 Job 信息
    job_res = supabase.table("autoviralvid_jobs").select("*").eq("run_id", run_id).single().execute()
    if not job_res or not job_res.data:
        return {"error": "Job not found"}
    job_data = job_res.data

    # 2. 重置失败的任务状态为 pending
    try:
        # 只重置 failed 的任务
        supabase.table("autoviralvid_video_tasks").update({
            "status": "pending",
            "provider_task_id": None, # 清除旧的 provider id 以便重新提交
            "error": None,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("run_id", run_id).eq("status", "failed").execute()
        
        # 也可以选择重置卡住的 processing 任务? 暂时只重置 failed
    except Exception as e:
        logger.error(f"[retry_job] Failed to reset tasks: {e}")
        return {"error": f"Failed to reset tasks: {e}"}

    # 3. 构造 payload 并重启工作流
    # execute_video_generation_workflow 需要: storyboard, thread_id, image_control, total_duration, styles
    # 这些存储在 jobs 表中
    # 注意: jobs 表中的 storyboards 可能是 PlanResponse 格式 (List[ClipSpec]) 或 原始 storyboard json
    # execute_video_generation_workflow 在 line 100 json.dumps(storyboard)
    # 如果 job_data['storyboards'] 已经是 list，可以直接用
    
    payload = {
        "run_id": run_id,
        "thread_id": f"t_{run_id}", # 假设
        "storyboard": {"scenes": []}, # 构造兼容结构
        "image_control": job_data.get("image_control", False),
        "total_duration": job_data.get("total_duration", 10.0),
        "styles": job_data.get("styles", [])
    }
    
    # 尝试还原 storyboard 结构
    sb_data = job_data.get("storyboards")
    if sb_data:
        if isinstance(sb_data, list):
             # 转换为 execute_video_generation_workflow 期望的格式
             # 它期望 payload['storyboard']['scenes']...
             # 但 wait, execute_.. line 102 merge_storyboards_to_video_tasks_impl(storyboard_json)
             # 如果传入的是 list，json.dumps 会生成 list json
             # merge_storyboards... 能处理 list json 吗?
             # See agent_skills.py merge_storyboards_to_video_tasks_impl implementation
             # 假设之前存入 jobs 的 storyboards 是可以直接用的
             payload["storyboard"] = sb_data
        elif isinstance(sb_data, dict):
             payload["storyboard"] = sb_data
    
    # 重新启动后台任务 (它会轮询并等待 pending 任务完成)
    await job_manager.start_job(run_id, execute_video_generation_workflow(run_id, payload))
    
    return {"status": "retrying", "run_id": run_id, "message": "已重置失败任务并重启工作流"}


@app.get("/share/{slug}")
async def get_share(slug: str):
    if not supabase:
        return {"error": "Supabase not configured"}
    res = supabase.table("autoviralvid_jobs").select("run_id, slogan, cover_url, video_url, share_slug, status, storyboards, total_duration, styles, image_control, created_at, updated_at").eq("share_slug", slug).single().execute()
    return res.data or {}


async def _get_embedding(text: str) -> list[float] | None:
    if not (OPENROUTER_BASE and OPENROUTER_KEY and text):
        return None
    try:
        # 构建请求头，支持 OpenRouter
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
        }
        # OpenRouter 需要 HTTP-Referer header
        if "openrouter.ai" in OPENROUTER_BASE:
            headers["HTTP-Referer"] = EMBED_REFERER
            headers["X-Title"] = "SaleAgent"
        # 代理支持（与 OpenRouterClient 保持一致）
        proxy = os.getenv("OPENROUTER_PROXY")
        http_proxy = os.getenv("OPENROUTER_HTTP_PROXY") or os.getenv("HTTP_PROXY")
        https_proxy = os.getenv("OPENROUTER_HTTPS_PROXY") or os.getenv("HTTPS_PROXY")
        proxies = None
        if proxy:
            proxies = {"http://": proxy, "https://": proxy}
        elif http_proxy or https_proxy:
            proxies = {}
            if http_proxy:
                proxies["http://"] = http_proxy
            if https_proxy:
                proxies["https://"] = https_proxy

        async with httpx.AsyncClient(timeout=15, proxies=proxies) as client:
            r = await client.post(
                f"{OPENROUTER_BASE}/embeddings",
                headers=headers,
                json={"input": text, "model": EMBED_MODEL},
            )
            r.raise_for_status()
            data = r.json()
            return data["data"][0]["embedding"]
    except Exception:
        return None


        

    



@app.get("/agent/session/{run_id}")
async def get_agent_session(run_id: str):
    """
    Get the latest agent session state from Supabase for history restoration.
    """
    print(f"\n>>> DEBUG: [Backend] get_agent_session called for run_id: {run_id}")
    logger.info(f"DEBUG: [Backend] get_agent_session called for run_id: {run_id}")
    if not supabase:
        print(">>> DEBUG: [Backend] Supabase not configured")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Supabase not configured")
    
    try:
        # Try finding in crew_sessions first
        res = supabase.table("autoviralvid_crew_sessions").select("*").eq("run_id", run_id).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
            
        # Fallback to jobs table
        job_res = supabase.table("autoviralvid_jobs").select("*").eq("run_id", run_id).limit(1).execute()
        if job_res.data and len(job_res.data) > 0:
            job = job_res.data[0]
            
            # Fetch related video tasks
            tasks_res = supabase.table("autoviralvid_video_tasks").select("*").eq("run_id", run_id).execute()
            video_tasks = tasks_res.data or []
            
            # Ensure 'context' field exists for frontend compatibility
            if "context" not in job:
                job["context"] = {
                    "storyboard": job.get("storyboards"),
                    "video_tasks": video_tasks,
                    "clips": video_tasks,
                    "messages": [], # Empty history for jobs table fallback
                    "collected_info": {}
                }
            return job
            
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Session {run_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching session {run_id}: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agent/sessions")
async def list_agent_sessions(limit: int = 40):
    """
    List recent agent sessions for the sidebar history.
    Queries both 'jobs' and 'crew_sessions' tables and merges them.
    Priority given to 'jobs' table for project metadata.
    """
    if not supabase:
        return {"workflows": []}
    
    try:
        # 1. Fetch from jobs table
        jobs_res = (
            supabase.table("autoviralvid_jobs")
            .select("run_id, created_at, slogan, status")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        
        # 2. Fetch from crew_sessions table
        # We try to get session topics from context if available, or fallback to status
        crew_res = (
            supabase.table("autoviralvid_crew_sessions")
            .select("run_id, created_at, status, context")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        
        # Map to common structure and merge
        merged_map = {} # run_id -> workflow_item
        
        # Process crew_sessions first (might be more recent or experimental)
        for item in (crew_res.data or []):
            rid = item.get("run_id")
            if not rid: continue
            
            # Extract topic/goal from context if possible
            ctx = item.get("context") or {}
            col_info = ctx.get("collected_info") or {}
            topic = col_info.get("topic") or col_info.get("goal") or item.get("status") or "Agent Session"
            
            merged_map[rid] = {
                "run_id": rid,
                "created_at": item.get("created_at"),
                "video_topic": topic,
                "goal": topic,
                "status": item.get("status")
            }
            
        # Process jobs (overwrites or adds)
        for item in (jobs_res.data or []):
            rid = item.get("run_id")
            if not rid: continue
            
            # Jobs have reliable slogans
            merged_map[rid] = {
                "run_id": rid,
                "created_at": item.get("created_at"),
                "video_topic": item.get("slogan") or merged_map.get(rid, {}).get("video_topic", "New Job"),
                "goal": item.get("slogan") or merged_map.get(rid, {}).get("goal", "New Job"),
                "status": item.get("status")
            }
            
        # Sort by created_at descending
        all_workflows = list(merged_map.values())
        all_workflows.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        
        # Final limit
        workflows = all_workflows[:limit]
        
        print(f">>> DEBUG: [Backend] list_agent_sessions returning {len(workflows)} merged workflows")
        logger.info(f"DEBUG: [Backend] list_agent_sessions returning {len(workflows)} merged workflows")
            
        return {"workflows": workflows}
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        return {"workflows": []}


@app.get("/recommend/{slug}")
async def recommend(slug: str, limit: int = 8):
    if not supabase:
        return []
    # 获取当前作业 slogan
    job_res = supabase.table("autoviralvid_jobs").select("slogan").eq("share_slug", slug).single().execute()
    slogan = (job_res.data or {}).get("slogan") if job_res and job_res.data else None
    if not slogan:
        rec = supabase.table("autoviralvid_prompts_library").select("id, title, category").order("created_at", desc=True).limit(limit).execute()
        return rec.data or []

    # 优先尝试向量检索：如果存在 RPC match_prompts 则调用
    emb = await _get_embedding(slogan)
    if emb:
        try:
            rpc = supabase.rpc("match_prompts", {"query": emb, "match_count": limit}).execute()
            if rpc.data:
                # 若 RPC 未返回 cover_url，则补充查询
                if len(rpc.data) > 0 and "cover_url" not in rpc.data[0]:
                    ids = [row.get("id") for row in rpc.data if row.get("id")]
                    if ids:
                        detail = supabase.table("autoviralvid_prompts_library").select("id, title, category, cover_url").in_("id", ids).execute()
                        if detail.data:
                            # 以 id 为键合并 cover_url
                            cover_map = {d["id"]: d.get("cover_url") for d in detail.data}
                            for row in rpc.data:
                                row["cover_url"] = cover_map.get(row.get("id"))
                return rpc.data
        except Exception:
            pass
    q = supabase.table("autoviralvid_prompts_library").select("id, title, category, cover_url").ilike("title", f"%{slogan.split()[0]}%").limit(limit).execute()
    if q.data:
        return q.data
    rec = supabase.table("autoviralvid_prompts_library").select("id, title, category, cover_url").order("created_at", desc=True).limit(limit).execute()
    return rec.data or []



# VideoClipsConfirmRequest and crewai_video_clips_confirm removed.
# Manual/Automatic stitching is now handled by video_task_queue_supabase.py or langgraph_workflow.py.



class UploadPresignRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"

@app.post("/upload/presign")
async def upload_presign(body: UploadPresignRequest):
    try:
        key = f"uploads/{uuid.uuid4().hex[:8]}_{body.filename}"
        res = presign_put_url(key=key, content_type=body.content_type)
        return res
    except Exception as e:
        logger.error(f"[upload_presign] Failed: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# [NEW] Scene Regenerate Endpoint

# SceneRegenerateRequest and crewai_scene_regenerate removed.
# Regeneration is now handled via agent-chat and specific node logic in langgraph_workflow.py.


# [NEW] Video Stitch Endpoint

# VideoStitchRequest and crewai_video_stitch removed.
# Refer to langgraph_workflow.py for modern stitching orchestration.

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

