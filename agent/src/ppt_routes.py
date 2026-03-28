"""PPT API路由 — Feature A (PPT生成) + Feature B (PPT/PDF视频生成)"""

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
from src.schemas.ppt_pipeline import PPTPipelineRequest
from src.schemas.ppt_plan import PresentationPlanRequest
from src.schemas.ppt_research import ResearchRequest

logger = logging.getLogger("ppt_routes")

router = APIRouter(prefix="/api/v1/ppt", tags=["PPT"])

# ── 懒加载服务 ──────────────────────────────────────────────────────

_ppt_service = None


def _get_service():
    global _ppt_service
    if _ppt_service is None:
        from src.ppt_service import PPTService

        _ppt_service = PPTService()
    return _ppt_service


def _request_id(request: Request) -> str:
    """获取或生成请求ID用于日志追踪"""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    return rid


# ════════════════════════════════════════════════════════════════════
# Feature A: PPT 生成
# ════════════════════════════════════════════════════════════════════


@router.post("/outline", response_model=ApiResponse, status_code=200)
async def generate_outline(
    req: OutlineRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """生成PPT大纲 (Stage 1)"""
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
    """编辑/更新大纲 (用户确认前修改)"""
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
    """填充幻灯片内容 (Stage 2, 并行生成)"""
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
        result = await svc.run_ppt_pipeline(req)
        return ApiResponse(success=True, data=result.model_dump())
    except Exception as e:
        logger.error(f"[ppt_routes:{rid}] pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export", response_model=ApiResponse)
async def export_pptx(
    req: ExportRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """导出PPTX文件 (Stage 3)"""
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


# ── TTS 合成 ────────────────────────────────────────────────────────


class TTSRequest(BaseModel):
    """TTS合成请求"""

    texts: List[str] = Field(default_factory=list, max_length=50)
    voice_style: str = "zh-CN-female"


@router.post("/tts", response_model=ApiResponse)
async def synthesize_tts(
    req: TTSRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """批量TTS合成 → R2音频URL列表"""
    rid = _request_id(request)
    try:
        # 文本长度校验
        for i, text in enumerate(req.texts):
            if len(text) > 5000:
                raise HTTPException(
                    status_code=400, detail=f"texts[{i}] 超过5000字限制"
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


# ════════════════════════════════════════════════════════════════════
# Feature B: PPT/PDF 视频生成
# ════════════════════════════════════════════════════════════════════


@router.post("/parse", response_model=ApiResponse)
async def parse_document(
    req: ParseRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """解析PPT/PDF文件 → SlideContent[]"""
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


# ── 内容增强 ─────────────────────────────────────────────────────────


class EnhanceRequest(BaseModel):
    """讲解文本增强请求"""

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
    """增强讲解内容: LLM优化 + TTS合成"""
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


# ── 渲染 ─────────────────────────────────────────────────────────────

# 幂等性键存储 (内存级, 生产应用Redis)
_idempotency_cache: dict = {}


@router.post("/render", response_model=ApiResponse, status_code=200)
async def start_render(
    req: VideoRenderRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """启动Remotion Lambda视频渲染"""
    rid = _request_id(request)

    # 幂等性检查
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

        # 缓存幂等性结果
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
    """查询渲染状态"""
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
        raise HTTPException(status_code=400, detail="无效的任务ID格式")
    try:
        svc = _get_service()
        status = await svc.get_render_status(job_id)
        if status.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"任务不存在: {job_id}")
        return ApiResponse(success=True, data=status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 下载 ─────────────────────────────────────────────────────────────


@router.get("/download/{job_id}", response_model=ApiResponse)
async def get_download_url(
    job_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """获取渲染视频的下载链接 (R2 presigned URL)"""
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
        raise HTTPException(status_code=400, detail="无效的任务ID格式")
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
