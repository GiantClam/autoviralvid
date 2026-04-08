"""PPT API routes: Feature A (PPT generation) + Feature B (PPT/PDF video render)."""

from __future__ import annotations

import logging
import json
import uuid
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
from src.schemas.ppt_plan import PresentationPlanRequest
from src.schemas.ppt_research import ResearchRequest
from src.schemas.ppt_ai_prompt import (
    AIPromptPPTRequest,
    AIPromptPPTResult,
)

logger = logging.getLogger("ppt_routes")

router = APIRouter(prefix="/api/v1/ppt", tags=["PPT"])

# 閳光偓閳光偓 閹虫帒濮炴潪鑺ユ箛閸?閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓

_ppt_service = None


def _get_service():
    global _ppt_service
    if _ppt_service is None:
        from src.ppt_service_v2 import PPTService

        _ppt_service = PPTService()
    return _ppt_service


def _request_id(request: Request) -> str:
    """閼惧嘲褰囬幋鏍晸閹存劘濮逛痉D閻劋绨弮銉ョ箶鏉╁€熼嚋"""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    return rid



# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜
# Feature A: PPT 閻㈢喐鍨?# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜


@router.post("/outline", response_model=ApiResponse, status_code=200)
async def generate_outline(
    req: OutlineRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """閻㈢喐鍨歅PT婢堆呯堪 (Stage 1)"""
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
    """缂傛牞绶?閺囧瓨鏌婃径褏缈?(閻劍鍩涚涵閸撳秳鎱ㄩ弨?"""
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
    """婵夊帠楠炶崵浼呴悧鍥у敶鐎?(Stage 2, 楠炴儼閻㈢喐鍨?"""
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
    """鐎电厧鍤璓PTX閺傚洣娆?(Stage 3)"""
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


# 閳光偓閳光偓 TTS 閸氬牊鍨?閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓


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
        logger.info(
            f"[ppt_routes:{rid}] render start user={user.id} slides={len(req.slides)}"
        )
        svc = _get_service()
        job = await svc.start_video_render(req.slides, req.config)
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
# 鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣


@router.post("/generate-from-prompt", response_model=ApiResponse)
async def generate_ppt_from_prompt(
    req: AIPromptPPTRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """Generate PPT from AI prompt using ppt-master workflow"""
    rid = _request_id(request)
    try:
        logger.info(
            f"[ppt_routes:{rid}] ai_prompt_gen user={user.id} prompt={req.prompt[:80]} pages={req.total_pages}"
        )

        from src.ppt_master_service import PPTMasterService

        service = PPTMasterService()
        result = await service.generate_from_prompt(
            prompt=req.prompt,
            total_pages=req.total_pages,
            style=req.style,
            color_scheme=req.color_scheme,
            language=req.language,
            template_family=req.template_family,
            include_images=req.include_images,
        )

        if result.get("success"):
            return ApiResponse(success=True, data=result)
        else:
            return ApiResponse(
                success=False, error=result.get("error", "Unknown error"), data=result
            )
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] ai_prompt_gen failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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




