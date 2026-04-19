"""PPT API routes: Feature A (PPT generation) + Feature B (PPT/PDF video render)."""

from __future__ import annotations

import asyncio
import logging
import json
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from supabase import Client, create_client

from src.auth import get_current_user, AuthUser
from src.schemas.ppt import (
    ApiResponse,
    ContentRequest,
    ExportRequest,
    OutlineRequest,
    ParseRequest,
    PresentationOutline,
    SlideContent,
    VideoRenderRequest,
)
from src.schemas.ppt_outline import OutlinePlanRequest
from src.schemas.ppt_plan import PresentationPlanRequest
from src.schemas.ppt_research import ResearchRequest
from src.schemas.ppt_ai_prompt import (
    AIPromptPPTRequest,
)

logger = logging.getLogger("ppt_routes")

router = APIRouter(prefix="/api/v1/ppt", tags=["PPT"])


_ppt_service = None


def _get_service():
    global _ppt_service
    if _ppt_service is None:
        from src.ppt_service_v2 import PPTService

        _ppt_service = PPTService()
    return _ppt_service


_ppt_job_store: Optional[Client] = None
_ppt_job_store_disabled = False
_PPT_PROMPT_JOB_TABLE = "autoviralvid_ppt_export_tasks"


def _runtime_role() -> str:
    explicit = str(os.getenv("PPT_EXECUTION_ROLE", "auto") or "auto").strip().lower()
    if explicit in {"web", "worker"}:
        return explicit
    if str(os.getenv("VERCEL", "") or "").strip() or str(os.getenv("VERCEL_ENV", "") or "").strip():
        return "web"
    return "worker"


def _dispatch_tokens() -> List[str]:
    out: List[str] = []
    for key in (
        "PPT_PROMPT_DISPATCH_TOKEN",
        "PPT_EXPORT_WORKER_TOKEN",
        "BILLING_RECONCILE_TOKEN",
        "CRON_SECRET",
    ):
        token = str(os.getenv(key) or "").strip()
        if token and token not in out:
            out.append(token)
    return out


def _dispatch_token() -> str:
    tokens = _dispatch_tokens()
    return tokens[0] if tokens else ""


def _worker_base_url() -> str:
    return str(os.getenv("PPT_EXPORT_WORKER_BASE_URL") or "").strip().rstrip("/")


def _is_likely_garbled_prompt(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    replacement_hits = text.count("�")
    question_hits = text.count("?")
    total_hits = replacement_hits + question_hits
    if total_hits == 0:
        return False
    ratio = float(total_hits) / float(max(len(text), 1))
    if text.replace("?", "").strip() == "":
        return True
    return total_hits >= 6 and ratio >= 0.35


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _get_ppt_job_store() -> Optional[Client]:
    global _ppt_job_store
    global _ppt_job_store_disabled
    if _ppt_job_store_disabled:
        return None
    if _ppt_job_store is not None:
        return _ppt_job_store

    supabase_url = str(os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (
        str(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        or str(os.getenv("SUPABASE_SERVICE_KEY") or "").strip()
    )
    if not supabase_url or not supabase_key:
        return None
    try:
        _ppt_job_store = create_client(supabase_url, supabase_key)
    except Exception as exc:
        logger.warning(f"[ppt_routes] failed to init job store: {exc}")
        _ppt_job_store = None
    return _ppt_job_store


def _build_prompt_job_meta(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "project_name": str(row.get("project_name") or ""),
        "project_path": str(row.get("project_path") or ""),
        "output_base": str(row.get("output_base") or ""),
        "total_pages": int(row.get("total_pages") or 10),
        "request": row.get("request") if isinstance(row.get("request"), dict) else {},
        "poll_url": str(row.get("poll_url") or ""),
    }


def _normalize_prompt_job_row(db_row: Dict[str, Any]) -> Dict[str, Any]:
    request_meta = db_row.get("request_meta")
    meta = request_meta if isinstance(request_meta, dict) else {}
    total_pages_raw = meta.get("total_pages")
    try:
        total_pages = int(total_pages_raw or 10)
    except Exception:
        total_pages = 10
    request_payload = meta.get("request")
    request_payload = request_payload if isinstance(request_payload, dict) else {}
    return {
        "job_id": str(db_row.get("task_id") or ""),
        "user_id": str(db_row.get("user_id") or ""),
        "status": str(db_row.get("status") or "queued"),
        "created_at": db_row.get("created_at"),
        "started_at": db_row.get("started_at"),
        "updated_at": db_row.get("updated_at"),
        "finished_at": db_row.get("finished_at"),
        "project_name": str(meta.get("project_name") or ""),
        "project_path": str(meta.get("project_path") or ""),
        "output_base": str(meta.get("output_base") or ""),
        "poll_url": str(meta.get("poll_url") or ""),
        "total_pages": total_pages,
        "request": request_payload,
        "request_meta": meta,
        "result": db_row.get("result") if isinstance(db_row.get("result"), dict) else None,
        "error": str(db_row.get("error") or ""),
    }


def _persist_prompt_job_create(job_id: str, row: Dict[str, Any]) -> None:
    global _ppt_job_store_disabled
    sb = _get_ppt_job_store()
    if sb is None:
        return
    payload = {
        "task_id": job_id,
        "status": str(row.get("status") or "queued"),
        "mode": "prompt_async",
        "runtime_role": _runtime_role(),
        "user_id": str(row.get("user_id") or ""),
        "request_meta": _build_prompt_job_meta(row),
        "result": row.get("result") if isinstance(row.get("result"), dict) else None,
        "error": str(row.get("error") or "") or None,
        "created_at": row.get("created_at"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "updated_at": row.get("updated_at"),
    }
    try:
        sb.table(_PPT_PROMPT_JOB_TABLE).upsert(payload, on_conflict="task_id").execute()
    except Exception as exc:
        err_text = str(exc).lower()
        if "relation" in err_text and _PPT_PROMPT_JOB_TABLE.lower() in err_text:
            _ppt_job_store_disabled = True
            logger.warning(
                "[ppt_routes] prompt job table %s not found; fallback to in-memory only",
                _PPT_PROMPT_JOB_TABLE,
            )
        else:
            logger.warning(f"[ppt_routes] create prompt job persist failed: {exc}")


def _load_persisted_prompt_job(job_id: str) -> Optional[Dict[str, Any]]:
    global _ppt_job_store_disabled
    sb = _get_ppt_job_store()
    if sb is None:
        return None
    try:
        result = (
            sb.table(_PPT_PROMPT_JOB_TABLE)
            .select("*")
            .eq("task_id", job_id)
            .limit(1)
            .execute()
        )
        row = (result.data or [None])[0]
        if not isinstance(row, dict):
            return None
        return _normalize_prompt_job_row(row)
    except Exception as exc:
        err_text = str(exc).lower()
        if "relation" in err_text and _PPT_PROMPT_JOB_TABLE.lower() in err_text:
            _ppt_job_store_disabled = True
            logger.warning(
                "[ppt_routes] prompt job table %s not found; fallback to in-memory only",
                _PPT_PROMPT_JOB_TABLE,
            )
        else:
            logger.warning(f"[ppt_routes] load prompt job failed: {exc}")
        return None


def _persist_prompt_job_patch(job_id: str, **patch: Any) -> None:
    sb = _get_ppt_job_store()
    if sb is None:
        return

    existing = _load_persisted_prompt_job(job_id) or {}
    if not existing:
        # If missing, attempt create using patch as a seed.
        seed = {
            "job_id": job_id,
            "user_id": str(patch.get("user_id") or ""),
            "status": str(patch.get("status") or "queued"),
            "created_at": patch.get("created_at") or _now_iso(),
            "started_at": patch.get("started_at"),
            "finished_at": patch.get("finished_at"),
            "updated_at": _now_iso(),
            "project_name": str(patch.get("project_name") or ""),
            "project_path": str(patch.get("project_path") or ""),
            "output_base": str(patch.get("output_base") or ""),
            "total_pages": int(patch.get("total_pages") or 10),
            "request": patch.get("request") if isinstance(patch.get("request"), dict) else {},
            "poll_url": str(patch.get("poll_url") or ""),
            "result": patch.get("result") if isinstance(patch.get("result"), dict) else None,
            "error": str(patch.get("error") or ""),
        }
        _persist_prompt_job_create(job_id, seed)
        return

    request_meta = dict(existing.get("request_meta") or {})
    for key in ("project_name", "project_path", "output_base", "total_pages", "request", "poll_url"):
        if key in patch:
            request_meta[key] = patch.get(key)

    update_data: Dict[str, Any] = {"request_meta": request_meta}
    for key in ("status", "started_at", "finished_at", "error", "result", "user_id"):
        if key in patch:
            update_data[key] = patch.get(key)
    update_data["updated_at"] = _now_iso()

    try:
        (
            sb.table(_PPT_PROMPT_JOB_TABLE)
            .update(update_data)
            .eq("task_id", job_id)
            .execute()
        )
    except Exception as exc:
        logger.warning(f"[ppt_routes] patch prompt job persist failed: {exc}")


def _list_queued_prompt_job_ids(limit: int = 1) -> List[str]:
    sb = _get_ppt_job_store()
    if sb is None:
        return []
    safe_limit = max(1, min(20, int(limit or 1)))
    try:
        result = (
            sb.table(_PPT_PROMPT_JOB_TABLE)
            .select("task_id")
            .eq("status", "queued")
            .order("created_at", desc=False)
            .limit(safe_limit)
            .execute()
        )
    except Exception as exc:
        logger.warning(f"[ppt_routes] list queued prompt jobs failed: {exc}")
        return []
    out: List[str] = []
    for row in result.data or []:
        if not isinstance(row, dict):
            continue
        job_id = str(row.get("task_id") or "").strip()
        if job_id:
            out.append(job_id)
    return out


def _claim_prompt_job_for_run(job_id: str, started_at: str) -> Optional[Dict[str, Any]]:
    """Try to atomically claim a queued job for execution."""
    sb = _get_ppt_job_store()
    if sb is None:
        return None
    try:
        result = (
            sb.table(_PPT_PROMPT_JOB_TABLE)
            .update(
                {
                    "status": "running",
                    "started_at": started_at,
                    "updated_at": started_at,
                }
            )
            .eq("task_id", job_id)
            .eq("status", "queued")
            .execute()
        )
        row = (result.data or [None])[0]
        if not isinstance(row, dict):
            return None
        return _normalize_prompt_job_row(row)
    except Exception as exc:
        logger.warning(f"[ppt_routes] claim prompt job failed: {exc}")
        return None


def _internal_request_authorized(request: Request) -> bool:
    expected_tokens = _dispatch_tokens()
    if not expected_tokens:
        return False
    auth_header = str(request.headers.get("authorization") or "")
    bearer = ""
    if auth_header.lower().startswith("bearer "):
        bearer = auth_header[7:].strip()
    header_token = str(request.headers.get("x-internal-token") or "").strip()
    query_token = str(request.query_params.get("token") or "").strip()
    return (
        bearer in expected_tokens
        or header_token in expected_tokens
        or query_token in expected_tokens
    )


async def _trigger_prompt_job_dispatch(job_id: str, rid: str) -> None:
    worker_base = _worker_base_url()
    role = _runtime_role()

    if role == "web" and worker_base:
        dispatch_url = f"{worker_base}/api/v1/ppt/internal/prompt-jobs/dispatch"
        headers: Dict[str, str] = {"content-type": "application/json"}
        token = _dispatch_token()
        if token:
            headers["x-internal-token"] = token
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(dispatch_url, json={"job_id": job_id}, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    "[ppt_routes:%s] worker dispatch request failed status=%s body=%s",
                    rid,
                    resp.status_code,
                    str(resp.text or "")[:300],
                )
            else:
                logger.info(
                    "[ppt_routes:%s] worker dispatch accepted job=%s status=%s",
                    rid,
                    job_id,
                    resp.status_code,
                )
            return
        except Exception as exc:
            logger.warning(
                f"[ppt_routes:{rid}] worker dispatch exception for job={job_id}: {exc}"
            )
            return

    asyncio.create_task(_run_ppt_prompt_job(job_id=job_id, rid=rid))


def _request_id(request: Request) -> str:
    """Return or generate request id."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    return rid


_ppt_prompt_jobs: Dict[str, Dict[str, Any]] = {}
_ppt_prompt_jobs_lock = Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_ppt_prompt_job(job_id: str, **patch: Any) -> None:
    with _ppt_prompt_jobs_lock:
        row = dict(_ppt_prompt_jobs.get(job_id) or {})
        row.update(patch)
        row["updated_at"] = _now_iso()
        _ppt_prompt_jobs[job_id] = row


def _get_ppt_prompt_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _ppt_prompt_jobs_lock:
        row = _ppt_prompt_jobs.get(job_id)
        if not isinstance(row, dict):
            return None
        return deepcopy(row)


def _get_prompt_job(job_id: str) -> Optional[Dict[str, Any]]:
    row = _load_persisted_prompt_job(job_id)
    if row:
        return row
    return _get_ppt_prompt_job(job_id)


def _list_memory_queued_prompt_job_ids(limit: int = 1) -> List[str]:
    safe_limit = max(1, min(20, int(limit or 1)))
    out: List[str] = []
    with _ppt_prompt_jobs_lock:
        for job_id, row in _ppt_prompt_jobs.items():
            if not isinstance(row, dict):
                continue
            if str(row.get("status") or "") != "queued":
                continue
            out.append(str(job_id))
            if len(out) >= safe_limit:
                break
    return out


def _resolve_project_path_from_job(job: Dict[str, Any]) -> Optional[Path]:
    raw_path = str(job.get("project_path") or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if candidate.exists() and candidate.is_dir():
            return candidate

    output_base_raw = str(job.get("output_base") or "").strip()
    project_name = str(job.get("project_name") or "").strip()
    if not (output_base_raw and project_name):
        return None

    output_base = Path(output_base_raw)
    if not output_base.exists() or not output_base.is_dir():
        return None

    try:
        candidates = sorted(
            [
                row
                for row in output_base.iterdir()
                if row.is_dir()
                and (row.name == project_name or row.name.startswith(f"{project_name}_"))
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return None

    return candidates[0] if candidates else None


def _parse_total_pages(project_path: Optional[Path], fallback: int) -> int:
    if project_path is None:
        return max(3, min(50, int(fallback or 10)))
    req_file = project_path / "runtime_request.json"
    if not req_file.exists():
        return max(3, min(50, int(fallback or 10)))
    try:
        payload = json.loads(req_file.read_text(encoding="utf-8", errors="ignore"))
        pages = int(payload.get("total_pages") or fallback or 10)
        return max(3, min(50, pages))
    except Exception:
        return max(3, min(50, int(fallback or 10)))


def _scan_executor_progress(project_path: Optional[Path]) -> Tuple[int, int, int]:
    if project_path is None:
        return 0, 0, 0
    executor_dir = project_path / "_runtime_inputs" / "executor_raw"
    if not executor_dir.exists():
        return 0, 0, 0
    plan_max = 0
    render_max = 0
    try:
        for row in executor_dir.glob("page_*_plan.txt"):
            m = re.search(r"page_(\d+)_plan\.txt$", row.name)
            if m:
                plan_max = max(plan_max, int(m.group(1)))
        for row in executor_dir.glob("page_*_render_1.txt"):
            m = re.search(r"page_(\d+)_render_1\.txt$", row.name)
            if m:
                render_max = max(render_max, int(m.group(1)))
    except Exception:
        pass
    svg_output_count = 0
    try:
        svg_output_count = len(list((project_path / "svg_output").glob("*.svg")))
    except Exception:
        svg_output_count = 0
    return plan_max, render_max, svg_output_count


def _read_runtime_progress_hint(project_path: Optional[Path]) -> Dict[str, Any]:
    if project_path is None:
        return {}
    hint_path = project_path / "_runtime_inputs" / "runtime_progress.json"
    if not hint_path.exists():
        return {}
    try:
        payload = json.loads(hint_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _infer_ppt_prompt_job_progress(job: Dict[str, Any]) -> Dict[str, Any]:
    status = str(job.get("status") or "queued")
    project_path = _resolve_project_path_from_job(job)
    total_pages = _parse_total_pages(project_path, int(job.get("total_pages") or 10))
    progress: Dict[str, Any] = {
        "stage": "queued",
        "detail": "Queued",
        "percent": 0.0,
        "current_page": 0,
        "total_pages": total_pages,
        "generated_slides": 0,
    }

    if status == "succeeded":
        progress.update(
            {
                "stage": "completed",
                "detail": "Generation completed",
                "percent": 100.0,
                "current_page": total_pages,
                "generated_slides": total_pages,
            }
        )
        return progress

    if status == "failed":
        progress.update(
            {
                "stage": "failed",
                "detail": str(job.get("error") or "Generation failed"),
                "percent": 100.0,
            }
        )
        return progress

    if project_path is None:
        progress.update(
            {
                "stage": "queued",
                "detail": "Waiting for worker to initialize project",
                "percent": 1.0,
            }
        )
        return progress

    skill_result = project_path / "skill_result.json"
    runtime_result = project_path / "runtime_result.json"
    if skill_result.exists():
        progress.update(
            {
                "stage": "completed",
                "detail": "Generation completed",
                "percent": 99.0,
                "current_page": total_pages,
                "generated_slides": total_pages,
            }
        )
        return progress

    if runtime_result.exists():
        progress.update(
            {
                "stage": "step7",
                "detail": "Finalizing and packaging PPTX",
                "percent": 96.0,
                "current_page": total_pages,
            }
        )
        return progress

    runtime_hint = _read_runtime_progress_hint(project_path)
    hint_stage = str(runtime_hint.get("stage") or "").strip().lower()
    hint_detail = str(runtime_hint.get("detail") or "").strip()
    hint_substage = str(runtime_hint.get("substage") or "").strip().lower()
    hint_percent = runtime_hint.get("percent")
    try:
        hint_percent_value = float(hint_percent)
    except Exception:
        hint_percent_value = None
    hint_current_page = runtime_hint.get("current_page")
    try:
        hint_page_value = int(hint_current_page)
    except Exception:
        hint_page_value = 0

    if hint_stage == "step4":
        step4_detail_map = {
            "research": "Collecting research context",
            "confirmations": "Generating confirmation checklist",
            "design_spec": "Generating design specification",
            "completed": "Design specification ready",
        }
        progress.update(
            {
                "stage": "step4",
                "detail": hint_detail
                or step4_detail_map.get(hint_substage, "Building strategy and design specification"),
                "percent": round(
                    min(
                        24.0,
                        max(14.0, hint_percent_value if hint_percent_value is not None else 18.0),
                    ),
                    1,
                ),
            }
        )
        return progress

    plan_max, render_max, svg_output_count = _scan_executor_progress(project_path)
    current_page = max(plan_max, render_max, svg_output_count, max(0, hint_page_value))
    if current_page > 0:
        current_page = min(total_pages, current_page)
        percent = 25.0 + (float(current_page) / float(max(total_pages, 1))) * 65.0
        if hint_percent_value is not None:
            percent = max(percent, hint_percent_value)
        progress.update(
            {
                "stage": "step6",
                "detail": hint_detail or f"Generating slides {current_page}/{total_pages}",
                "percent": round(min(92.0, percent), 1),
                "current_page": current_page,
                "generated_slides": min(total_pages, svg_output_count),
            }
        )
        return progress

    if hint_stage == "step5":
        progress.update(
            {
                "stage": "step5",
                "detail": hint_detail or "Preparing assets for rendering",
                "percent": round(
                    max(24.0, hint_percent_value if hint_percent_value is not None else 25.0),
                    1,
                ),
            }
        )
        return progress

    if hint_stage == "step3":
        progress.update(
            {
                "stage": "step3",
                "detail": hint_detail or "Template selected, preparing strategy",
                "percent": round(
                    max(10.0, hint_percent_value if hint_percent_value is not None else 12.0),
                    1,
                ),
            }
        )
        return progress

    strategist_dir = project_path / "_runtime_inputs" / "strategist_raw"
    if (project_path / "design_spec.md").exists() or strategist_dir.exists():
        progress.update(
            {
                "stage": "step4",
                "detail": "Building strategy and design specification",
                "percent": 18.0,
            }
        )
        return progress

    if (project_path / "sources").exists():
        progress.update(
            {
                "stage": "step2",
                "detail": "Preparing source and selecting template",
                "percent": 8.0,
            }
        )
        return progress

    progress.update(
        {
            "stage": "step1",
            "detail": "Initializing generation workspace",
            "percent": 3.0,
        }
    )
    return progress


def _prompt_preflight_enabled() -> bool:
    return _env_bool("PPT_PROMPT_PREFLIGHT_ENABLED", True)


def _prompt_preflight_model() -> str:
    model = str(
        os.getenv("PPT_PROMPT_PREFLIGHT_MODEL")
        or os.getenv("CONTENT_LLM_MODEL")
        or "openai/gpt-5.3-codex"
    ).strip()
    return model or "openai/gpt-5.3-codex"


async def _run_prompt_llm_preflight(req_payload: Dict[str, Any], rid: str) -> Optional[str]:
    if not _prompt_preflight_enabled():
        return None
    try:
        from src.openrouter_client import OpenRouterClient

        model = _prompt_preflight_model()
        timeout_sec = max(6.0, min(45.0, _env_float("PPT_PROMPT_PREFLIGHT_TIMEOUT_SECONDS", 18.0)))
        prompt = str(req_payload.get("prompt") or "").strip()
        probe_prompt = f"Health probe for prompt-to-ppt. Topic: {prompt[:140]}"
        client = OpenRouterClient()
        _ = await client.preflight_chat(
            model=model,
            prompt=probe_prompt,
            timeout_seconds=timeout_sec,
        )
        logger.info(
            "[ppt_routes:%s] llm preflight ok model=%s timeout=%.1fs",
            rid,
            model,
            timeout_sec,
        )
        return None
    except Exception as exc:
        err_text = f"llm_preflight_failed:{str(exc)[:240]}"
        logger.warning("[ppt_routes:%s] %s", rid, err_text)
        return err_text


async def _run_ppt_prompt_job(
    *,
    job_id: str,
    user_id: Optional[str] = None,
    req_payload: Optional[Dict[str, Any]] = None,
    rid: str,
) -> None:
    from src.ppt_master_service import PPTMasterService

    seed_job = _get_prompt_job(job_id) or {}
    seed_status = str(seed_job.get("status") or "")
    if seed_status in {"succeeded", "failed"}:
        logger.info(f"[ppt_routes:{rid}] skip terminal prompt job_id={job_id} status={seed_status}")
        return

    effective_user_id = str(user_id or seed_job.get("user_id") or "")
    effective_req_payload = dict(seed_job.get("request") or {})
    if isinstance(req_payload, dict):
        effective_req_payload.update(req_payload)

    if not isinstance(effective_req_payload, dict) or not str(effective_req_payload.get("prompt") or "").strip():
        _set_ppt_prompt_job(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            error="Prompt payload missing for async job",
        )
        _persist_prompt_job_patch(
            job_id,
            status="failed",
            finished_at=_now_iso(),
            error="Prompt payload missing for async job",
        )
        logger.error(f"[ppt_routes:{rid}] prompt job missing payload job_id={job_id}")
        return

    started_at = _now_iso()
    claimed_row = _claim_prompt_job_for_run(job_id, started_at)
    if claimed_row is not None:
        seed_job = claimed_row
    else:
        refreshed = _get_prompt_job(job_id) or seed_job
        refreshed_status = str(refreshed.get("status") or "")
        if refreshed_status in {"running", "succeeded", "failed"}:
            logger.info(
                f"[ppt_routes:{rid}] skip claimed prompt job_id={job_id} status={refreshed_status}"
            )
            return

    _set_ppt_prompt_job(job_id, status="running", started_at=started_at)
    _persist_prompt_job_patch(
        job_id,
        status="running",
        started_at=started_at,
        user_id=effective_user_id,
        request=effective_req_payload,
    )
    try:
        service = PPTMasterService()
        job = _get_prompt_job(job_id) or seed_job
        project_name = str(job.get("project_name") or "").strip() or None
        preflight_error = await _run_prompt_llm_preflight(effective_req_payload, rid)
        if preflight_error:
            finished_at = _now_iso()
            _set_ppt_prompt_job(
                job_id,
                status="failed",
                finished_at=finished_at,
                error=preflight_error,
            )
            _persist_prompt_job_patch(
                job_id,
                status="failed",
                finished_at=finished_at,
                error=preflight_error,
            )
            return
        result = await service.generate_from_prompt(
            prompt=str(effective_req_payload.get("prompt") or ""),
            total_pages=int(effective_req_payload.get("total_pages") or 10),
            style=str(effective_req_payload.get("style") or "professional"),
            color_scheme=effective_req_payload.get("color_scheme"),
            language=str(effective_req_payload.get("language") or "zh-CN"),
            template_family=effective_req_payload.get("template_family"),
            include_images=bool(effective_req_payload.get("include_images")),
            web_enrichment=bool(effective_req_payload.get("web_enrichment")),
            image_asset_enrichment=bool(effective_req_payload.get("image_asset_enrichment")),
            project_name=project_name,
        )
        if bool(result.get("success")):
            finished_at = _now_iso()
            next_project_name = str(result.get("project_name") or job.get("project_name") or "")
            next_project_path = str(result.get("project_path") or job.get("project_path") or "")
            _set_ppt_prompt_job(
                job_id,
                status="succeeded",
                finished_at=finished_at,
                result=result,
                project_name=next_project_name,
                project_path=next_project_path,
            )
            _persist_prompt_job_patch(
                job_id,
                status="succeeded",
                finished_at=finished_at,
                result=result,
                project_name=next_project_name,
                project_path=next_project_path,
            )
            logger.info(
                f"[ppt_routes:{rid}] prompt job succeeded job_id={job_id} user={effective_user_id}"
            )
        else:
            finished_at = _now_iso()
            err_text = str(result.get("error") or "Unknown error")
            next_project_name = str(result.get("project_name") or job.get("project_name") or "")
            next_project_path = str(result.get("project_path") or job.get("project_path") or "")
            _set_ppt_prompt_job(
                job_id,
                status="failed",
                finished_at=finished_at,
                error=err_text,
                project_name=next_project_name,
                project_path=next_project_path,
            )
            _persist_prompt_job_patch(
                job_id,
                status="failed",
                finished_at=finished_at,
                error=err_text,
                project_name=next_project_name,
                project_path=next_project_path,
            )
            logger.warning(
                f"[ppt_routes:{rid}] prompt job failed job_id={job_id} user={effective_user_id} err={result.get('error')}"
            )
    except Exception as exc:
        finished_at = _now_iso()
        _set_ppt_prompt_job(
            job_id,
            status="failed",
            finished_at=finished_at,
            error=str(exc),
        )
        _persist_prompt_job_patch(
            job_id,
            status="failed",
            finished_at=finished_at,
            error=str(exc),
        )
        logger.error(
            f"[ppt_routes:{rid}] prompt job exception job_id={job_id} user={effective_user_id}: {exc}",
            exc_info=True,
        )




@router.post("/outline", response_model=ApiResponse, status_code=200)
async def generate_outline(
    req: OutlineRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Generate presentation outline (Stage 1)."""
    rid = _request_id(request)
    try:
        logger.info(
            f"[ppt_routes:{rid}] outline gen user={user.id} req={req.requirement[:80]}"
        )
        svc = _get_service()
        outline = await svc.generate_outline(req)
        return ApiResponse(success=True, data=outline.model_dump())
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] outline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/outline", response_model=ApiResponse)
async def update_outline(
    req: PresentationOutline,
    user: AuthUser = Depends(get_current_user),
):
    """Update outline content and recompute duration."""
    try:
        req.total_duration = sum(s.estimated_duration for s in req.slides)
        return ApiResponse(success=True, data=req.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/content", response_model=ApiResponse)
async def generate_content(
    req: ContentRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Generate slide content (Stage 2)."""
    rid = _request_id(request)
    try:
        logger.info(
            f"[ppt_routes:{rid}] content gen user={user.id} slides={len(req.outline.slides)}"
        )
        svc = _get_service()
        slides = await svc.generate_content(req)
        return ApiResponse(success=True, data=[s.model_dump() for s in slides])
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] content failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/research", response_model=ApiResponse)
async def generate_research_context(
    req: ResearchRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Generate research context before outline planning."""
    rid = _request_id(request)
    try:
        logger.info(
            f"[ppt_routes:{rid}] research gen user={user.id} topic={req.topic[:80]}"
        )
        svc = _get_service()
        result = await svc.generate_research_context(req)
        return ApiResponse(success=True, data=result.model_dump())
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] research failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/outline-plan", response_model=ApiResponse)
async def generate_outline_plan(
    req: OutlinePlanRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Generate sticky-note outline plan from research context."""
    rid = _request_id(request)
    try:
        logger.info(
            f"[ppt_routes:{rid}] outline plan gen user={user.id} topic={req.research.topic[:80]}"
        )
        svc = _get_service()
        result = await svc.generate_outline_plan(req)
        return ApiResponse(success=True, data=result.model_dump())
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] outline plan failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/presentation-plan", response_model=ApiResponse)
async def generate_presentation_plan(
    req: PresentationPlanRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Generate wireframe-level presentation plan from outline."""
    rid = _request_id(request)
    try:
        logger.info(
            f"[ppt_routes:{rid}] presentation plan gen user={user.id} title={req.outline.title[:80]}"
        )
        svc = _get_service()
        result = await svc.generate_presentation_plan(req)
        return ApiResponse(success=True, data=result.model_dump())
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] presentation plan failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/export", response_model=ApiResponse)
async def export_pptx(
    req: ExportRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Export PPTX (Stage 3)."""
    rid = _request_id(request)
    try:
        logger.info(
            f"[ppt_routes:{rid}] pptx export user={user.id} slides={len(req.slides)}"
        )
        svc = _get_service()
        export_data = await svc.export_pptx(req)
        return ApiResponse(success=True, data=export_data)
    except Exception as e:
        from src.minimax_exporter import MiniMaxExportError

        if isinstance(e, MiniMaxExportError):
            logger.error(
                f"[ppt_routes:{rid}] export failed classified: {e}", exc_info=True
            )
            detail = e.to_dict()
            return ApiResponse(
                success=False,
                error=json.dumps(detail, ensure_ascii=False),
                data={"failure": detail},
            )
        logger.error(f"[ppt_routes:{rid}] export failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))




class TTSRequest(BaseModel):
    """TTS request payload."""

    texts: List[str] = Field(default_factory=list, max_length=50)
    voice_style: str = "zh-CN-female"


@router.post("/tts", response_model=ApiResponse)
async def synthesize_tts(
    req: TTSRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Synthesize TTS audio and return URL list plus durations."""
    rid = _request_id(request)
    try:
        for i, text in enumerate(req.texts):
            if len(text) > 5000:
                raise HTTPException(
                    status_code=400, detail=f"texts[{i}] exceeds 5000 chars"
                )

        logger.info(
            f"[ppt_routes:{rid}] tts batch user={user.id} count={len(req.texts)}"
        )
        from src.tts_synthesizer import synthesize_batch

        urls, durations = await synthesize_batch(
            texts=req.texts,
            voice_style=req.voice_style,
        )
        return ApiResponse(
            success=True, data={"audio_urls": urls, "audio_durations": durations}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] TTS failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse", response_model=ApiResponse)
async def parse_document(
    req: ParseRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Parse PPT/PDF into SlideContent list."""
    rid = _request_id(request)
    try:
        logger.info(
            f"[ppt_routes:{rid}] parse user={user.id} type={req.file_type} url={req.file_url[:100]}"
        )
        svc = _get_service()
        doc = await svc.parse_document(req.file_url, req.file_type)
        return ApiResponse(success=True, data=doc.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] parse failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class EnhanceRequest(BaseModel):
    """Request model for slide enhancement."""

    slides: List[SlideContent] = Field(..., max_length=50)
    language: str = "zh-CN"
    enhance_narration: bool = True
    generate_tts: bool = True
    voice_style: str = "zh-CN-female"


@router.post("/enhance", response_model=ApiResponse)
async def enhance_content(
    req: EnhanceRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Enhance slide content with LLM and optional TTS."""
    rid = _request_id(request)
    try:
        logger.info(
            f"[ppt_routes:{rid}] enhance user={user.id} slides={len(req.slides)}"
        )
        svc = _get_service()
        slides = await svc.enhance_slides(
            slides=req.slides,
            language=req.language,
            enhance_narration=req.enhance_narration,
            generate_tts=req.generate_tts,
            voice_style=req.voice_style,
        )
        return ApiResponse(success=True, data=[s.model_dump() for s in slides])
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] enhance failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Render idempotency cache (in-memory fallback when Redis unavailable)
_idempotency_cache: dict = {}


@router.post("/render", response_model=ApiResponse, status_code=200)
async def start_render(
    req: VideoRenderRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Start Remotion Lambda render job."""
    rid = _request_id(request)

    if req.idempotency_key:
        cached = _idempotency_cache.get(req.idempotency_key)
        if cached and cached.get("user_id") == user.id:
            logger.info(
                f"[ppt_routes:{rid}] render idempotent hit key={req.idempotency_key}"
            )
            return ApiResponse(success=True, data=cached["result"])

    try:
        slide_count = len(req.slides or [])
        has_pptx = bool(str(req.pptx_url or "").strip())
        logger.info(
            f"[ppt_routes:{rid}] render start user={user.id} slides={slide_count} has_pptx={has_pptx}"
        )
        svc = _get_service()
        job = await svc.start_video_render(
            req.slides or [],
            req.config,
            pptx_url=req.pptx_url,
            audio_urls=req.audio_urls,
        )
        result = job.model_dump()

        if req.idempotency_key:
            _idempotency_cache[req.idempotency_key] = {
                "user_id": user.id,
                "result": result,
            }

        return ApiResponse(success=True, data=result)
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] render failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/render/{job_id}", response_model=ApiResponse)
async def get_render_status(
    job_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """Query render job status."""
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
        raise HTTPException(status_code=400, detail="invalid job_id format")
    try:
        svc = _get_service()
        status = await svc.get_render_status(job_id)
        if status.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
        return ApiResponse(success=True, data=status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{job_id}", response_model=ApiResponse)
async def get_download_url(
    job_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """Get video download URL (R2 presigned URL)."""
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
        raise HTTPException(status_code=400, detail="invalid job_id format")
    try:
        svc = _get_service()
        download = await svc.get_download_url(job_id)
        return ApiResponse(success=True, data=download)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"[ppt_routes] download failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Feature C: AI Prompt-based PPT Generation (ppt-master integration)


class PromptJobDispatchRequest(BaseModel):
    """Internal dispatch request for queued prompt jobs."""

    job_id: Optional[str] = None
    limit: int = 1


@router.post("/internal/prompt-jobs/dispatch", response_model=ApiResponse)
async def dispatch_prompt_jobs(
    req: PromptJobDispatchRequest,
    request: Request,
):
    """Dispatch queued prompt jobs (for worker runtime or Vercel cron)."""
    rid = _request_id(request)
    if not _dispatch_token():
        raise HTTPException(status_code=503, detail="PPT dispatch token is not configured")
    if not _internal_request_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    requested_job = str(req.job_id or "").strip()
    if requested_job and not re.match(r"^[a-zA-Z0-9_-]+$", requested_job):
        raise HTTPException(status_code=400, detail="invalid job_id format")

    if requested_job:
        queued_job_ids = [requested_job]
    else:
        queued_job_ids = _list_queued_prompt_job_ids(limit=req.limit)
        if not queued_job_ids:
            queued_job_ids = _list_memory_queued_prompt_job_ids(limit=req.limit)

    if not queued_job_ids:
        return ApiResponse(
            success=True,
            data={"accepted": 0, "job_ids": [], "message": "no queued prompt jobs"},
        )

    for job_id in queued_job_ids:
        asyncio.create_task(_run_ppt_prompt_job(job_id=job_id, rid=rid))

    logger.info(
        f"[ppt_routes:{rid}] dispatched prompt jobs count={len(queued_job_ids)} ids={queued_job_ids}"
    )
    return ApiResponse(
        success=True,
        data={
            "accepted": len(queued_job_ids),
            "job_ids": queued_job_ids,
            "runtime_role": _runtime_role(),
        },
    )


@router.post("/generate-from-prompt", response_model=ApiResponse)
async def generate_ppt_from_prompt(
    req: AIPromptPPTRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Submit async prompt-to-ppt job and return job id immediately."""
    rid = _request_id(request)
    try:
        if _is_likely_garbled_prompt(req.prompt):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Prompt appears garbled (possible encoding issue). "
                    "Please retry with UTF-8 input and avoid corrupted question-mark text."
                ),
            )
        logger.info(
            f"[ppt_routes:{rid}] ai_prompt_gen user={user.id} prompt={req.prompt[:80]} pages={req.total_pages}"
        )

        from src.ppt_master_service import PPTMasterService

        service = PPTMasterService()
        project_name = f"ai_gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        default_project_path = (
            service.output_base / f"{project_name}_ppt169_{datetime.now().strftime('%Y%m%d')}"
        )
        job_id = f"pptjob_{uuid.uuid4().hex[:12]}"
        created_at = _now_iso()
        poll_url = f"/api/v1/ppt/jobs/{job_id}"
        job_row: Dict[str, Any] = {
            "job_id": job_id,
            "user_id": user.id,
            "status": "queued",
            "created_at": created_at,
            "started_at": None,
            "finished_at": None,
            "project_name": project_name,
            "project_path": str(default_project_path),
            "output_base": str(service.output_base),
            "total_pages": int(req.total_pages),
            "request": req.model_dump(),
            "result": None,
            "error": None,
            "poll_url": poll_url,
        }
        memory_row = dict(job_row)
        memory_row.pop("job_id", None)
        _set_ppt_prompt_job(job_id, **memory_row)
        _persist_prompt_job_create(job_id, job_row)
        await _trigger_prompt_job_dispatch(job_id, rid)

        return ApiResponse(
            success=True,
            data={
                "job_id": job_id,
                "status": "queued",
                "project_name": project_name,
                "project_path": str(default_project_path),
                "poll_url": poll_url,
                "created_at": created_at,
            },
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.error(f"[ppt_routes:{rid}] ai_prompt_gen failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}", response_model=ApiResponse)
async def get_prompt_job_status(
    job_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """Get async prompt-to-ppt generation job status and progress."""
    if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
        raise HTTPException(status_code=400, detail="invalid job_id format")

    job = _get_prompt_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    if str(job.get("user_id") or "") != str(user.id):
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")

    project_path = _resolve_project_path_from_job(job)
    if project_path is not None and str(project_path) != str(job.get("project_path") or ""):
        _set_ppt_prompt_job(job_id, project_path=str(project_path))
        _persist_prompt_job_patch(job_id, project_path=str(project_path))
        job["project_path"] = str(project_path)

    progress = _infer_ppt_prompt_job_progress(job)
    payload: Dict[str, Any] = {
        "job_id": job_id,
        "status": str(job.get("status") or "queued"),
        "project_name": str(job.get("project_name") or ""),
        "project_path": str(job.get("project_path") or ""),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at"),
        "finished_at": job.get("finished_at"),
        "progress": progress,
    }
    if payload["status"] == "succeeded" and isinstance(job.get("result"), dict):
        payload["result"] = job.get("result")
    if payload["status"] == "failed":
        payload["error"] = str(job.get("error") or "Generation failed")
    return ApiResponse(success=True, data=payload)


@router.get("/templates", response_model=ApiResponse)
async def list_templates(
    user: AuthUser = Depends(get_current_user),
):
    """List available ppt-master templates"""
    try:
        from src.ppt_master_service import PPTMasterService

        service = PPTMasterService()
        templates = service.list_available_templates()

        return ApiResponse(success=True, data={"templates": templates})
    except Exception as e:
        logger.error(f"[ppt_routes] list_templates failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview/{project_name}", response_model=ApiResponse)
async def get_prompt_project_preview(
    project_name: str,
    user: AuthUser = Depends(get_current_user),
):
    """Get generated prompt-to-ppt project preview data."""
    if not re.match(r"^[a-zA-Z0-9._-]+$", project_name):
        raise HTTPException(status_code=400, detail="invalid project_name format")
    try:
        from src.ppt_master_service import PPTMasterService

        service = PPTMasterService()
        data = service.get_project_preview(project_name)
        return ApiResponse(success=True, data=data)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[ppt_routes] get prompt project preview failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download-output/{project_name}")
async def download_prompt_output_pptx(
    project_name: str,
    user: AuthUser = Depends(get_current_user),
):
    """Download generated prompt-to-ppt output file."""
    if not re.match(r"^[a-zA-Z0-9._-]+$", project_name):
        raise HTTPException(status_code=400, detail="invalid project_name format")
    try:
        from src.ppt_master_service import PPTMasterService

        service = PPTMasterService()
        output_path = service.resolve_output_pptx_path(project_name)
        return FileResponse(
            str(output_path),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=output_path.name,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[ppt_routes] download prompt output failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))




