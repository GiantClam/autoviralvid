"""PPT API routes: Feature A (PPT generation) + Feature B (PPT/PDF video render)."""

from __future__ import annotations

import asyncio
import logging
import json
import uuid
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

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
from src.schemas.ppt_pipeline import PPTPipelineRequest
from src.schemas.ppt_plan import PresentationPlanRequest
from src.schemas.ppt_research import ResearchRequest

logger = logging.getLogger("ppt_routes")

router = APIRouter(prefix="/api/v1/ppt", tags=["PPT"])

# 鈹€鈹€ 鎳掑姞杞芥湇鍔?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

_ppt_service = None


def _get_service():
    global _ppt_service
    if _ppt_service is None:
        from src.ppt_service_v2 import PPTService

        _ppt_service = PPTService()
    return _ppt_service


def _request_id(request: Request) -> str:
    """鑾峰彇鎴栫敓鎴愯姹侷D鐢ㄤ簬鏃ュ織杩借釜"""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    return rid


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
# Feature A: PPT 鐢熸垚
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲


@router.post("/outline", response_model=ApiResponse, status_code=200)
async def generate_outline(
    req: OutlineRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """鐢熸垚PPT澶х翰 (Stage 1)"""
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
    """缂栬緫/鏇存柊澶х翰 (鐢ㄦ埛纭鍓嶄慨鏀?"""
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
    """濉厖骞荤伅鐗囧唴瀹?(Stage 2, 骞惰鐢熸垚)"""
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
        logger.info(f"[ppt_routes:{rid}] research gen user={user.id} topic={req.topic[:80]}")
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


@router.post("/pipeline", response_model=ApiResponse)
async def run_pipeline(
    req: PPTPipelineRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Run full PPT pipeline: research -> outline -> plan -> quality -> optional export."""
    rid = _request_id(request)
    try:
        logger.info(
            f"[ppt_routes:{rid}] pipeline run user={user.id} topic={req.topic[:80]} pages={req.total_pages} export={req.with_export}"
        )
        svc = _get_service()
        timeout_raw = str(os.getenv("PPT_PIPELINE_REQUEST_TIMEOUT_SEC", "570")).strip()
        try:
            request_timeout = max(30, min(1800, int(timeout_raw)))
        except ValueError:
            request_timeout = 570
        try:
            result = await asyncio.wait_for(
                svc.run_ppt_pipeline(req),
                timeout=request_timeout,
            )
        except asyncio.TimeoutError as exc:
            logger.error(
                f"[ppt_routes:{rid}] pipeline timeout after {request_timeout}s",
                exc_info=True,
            )
            raise HTTPException(
                status_code=504,
                detail=f"pipeline timeout after {request_timeout}s",
            ) from exc
        return ApiResponse(success=True, data=result.model_dump())
    except Exception as e:
        from src.minimax_exporter import MiniMaxExportError

        if isinstance(e, MiniMaxExportError):
            logger.error(f"[ppt_routes:{rid}] pipeline failed classified: {e}", exc_info=True)
            detail = e.to_dict()
            return ApiResponse(
                success=False,
                error=json.dumps(detail, ensure_ascii=False),
                data={"failure": detail},
            )
        logger.error(f"[ppt_routes:{rid}] pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export", response_model=ApiResponse)
async def export_pptx(
    req: ExportRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """瀵煎嚭PPTX鏂囦欢 (Stage 3)"""
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
            logger.error(f"[ppt_routes:{rid}] export failed classified: {e}", exc_info=True)
            detail = e.to_dict()
            return ApiResponse(
                success=False,
                error=json.dumps(detail, ensure_ascii=False),
                data={"failure": detail},
            )
        logger.error(f"[ppt_routes:{rid}] export failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# 鈹€鈹€ TTS 鍚堟垚 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


class TTSRequest(BaseModel):
    """TTS鍚堟垚璇锋眰"""

    texts: List[str] = Field(default_factory=list, max_length=50)
    voice_style: str = "zh-CN-female"


@router.post("/tts", response_model=ApiResponse)
async def synthesize_tts(
    req: TTSRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """鎵归噺TTS鍚堟垚 鈫?R2闊抽URL鍒楄〃"""
    rid = _request_id(request)
    try:
        # 鏂囨湰闀垮害鏍￠獙
        for i, text in enumerate(req.texts):
            if len(text) > 5000:
                raise HTTPException(status_code=400, detail=f"texts[{i}] exceeds 5000 chars")

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


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
# Feature B: PPT/PDF 瑙嗛鐢熸垚
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲


@router.post("/parse", response_model=ApiResponse)
async def parse_document(
    req: ParseRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """瑙ｆ瀽PPT/PDF鏂囦欢 鈫?SlideContent[]"""
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


# 鈹€鈹€ 鍐呭澧炲己 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


class EnhanceRequest(BaseModel):
    """璁茶В鏂囨湰澧炲己璇锋眰"""

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
    """澧炲己璁茶В鍐呭: LLM浼樺寲 + TTS鍚堟垚"""
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


# 鈹€鈹€ 娓叉煋 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

# 骞傜瓑鎬ч敭瀛樺偍 (鍐呭瓨绾? 鐢熶骇搴旂敤Redis)
_idempotency_cache: dict = {}


@router.post("/render", response_model=ApiResponse, status_code=200)
async def start_render(
    req: VideoRenderRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """鍚姩Remotion Lambda瑙嗛娓叉煋"""
    rid = _request_id(request)

    # Idempotency check
    if req.idempotency_key:
        cached = _idempotency_cache.get(req.idempotency_key)
        if cached and cached.get("user_id") == user.id:
            logger.info(
                f"[ppt_routes:{rid}] render idempotent hit key={req.idempotency_key}"
            )
            return ApiResponse(success=True, data=cached["result"])

    try:
        logger.info(
            f"[ppt_routes:{rid}] render start user={user.id} slides={len(req.slides)}"
        )
        svc = _get_service()
        job = await svc.start_video_render(req.slides, req.config)
        result = job.model_dump()

        # Cache idempotent result
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


# Download


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



