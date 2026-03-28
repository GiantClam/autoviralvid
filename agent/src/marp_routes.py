"""Marp API 路由 — Markdown 驱动 PPT + 视频"""

from __future__ import annotations
import logging, uuid
from fastapi import APIRouter, Depends, HTTPException

from src.auth import get_current_user, AuthUser
from src.schemas.ppt_marp import ApiResponse, GenerateRequest, ExportRequest, SlideData

logger = logging.getLogger("marp_routes")
router = APIRouter(prefix="/api/v1/marp", tags=["Marp"])


@router.post("/generate", response_model=ApiResponse)
async def generate(req: GenerateRequest, user: AuthUser = Depends(get_current_user)):
    """一次性生成完整 Marp 演示文稿 (Markdown + Script)"""
    try:
        from src.marp_generator import generate_marp

        # 先生成大纲 (获取结构)
        from src.outline_generator import generate_outline

        outline = await generate_outline(
            requirement=req.requirement,
            language=req.language,
            num_slides=req.num_slides,
        )

        # 将完整需求传递给 Marp 生成器 (不只是大纲标题)
        marp_input = {
            "title": outline.title,
            "theme": req.theme,
            "requirement": req.requirement,  # 完整需求
            "slides": [
                {
                    "title": s.title,
                    "description": s.description,
                    "key_points": s.key_points,
                }
                for s in outline.slides
            ],
        }

        presentation = await generate_marp(marp_input, req.language)
        return ApiResponse(success=True, data=presentation.model_dump())
    except Exception as e:
        logger.error(f"marp generate failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export", response_model=ApiResponse)
async def export_pptx(req: ExportRequest, user: AuthUser = Depends(get_current_user)):
    """Marp Markdown → PPTX (via marp-cli)"""
    try:
        from src.marp_service import generate_pptx

        url = await generate_pptx(req.presentation)
        return ApiResponse(success=True, data={"url": url})
    except Exception as e:
        logger.error(f"marp export failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tts", response_model=ApiResponse)
async def synthesize_tts(req: dict, user: AuthUser = Depends(get_current_user)):
    """为 Marp 剧本合成 TTS"""
    try:
        from src.tts_synthesizer import synthesize_batch

        slides_data = req.get("slides", [])
        all_texts = []
        for s in slides_data:
            for line in s.get("script", []):
                all_texts.append(line.get("text", ""))

        if not all_texts:
            return ApiResponse(success=True, data={"slides": slides_data})

        urls, durations = await synthesize_batch(all_texts, "zh-CN-male")

        # 回填到 slides
        idx = 0
        for s in slides_data:
            total_dur = 0
            for line in s.get("script", []):
                if idx < len(urls) and urls[idx]:
                    line["audio_url"] = urls[idx]
                    line["audio_duration"] = (
                        durations[idx] if idx < len(durations) else 10
                    )
                total_dur += line.get("audio_duration", 0)
                idx += 1
            s["duration"] = max(2, total_dur + 1)

        return ApiResponse(success=True, data={"slides": slides_data})
    except Exception as e:
        logger.error(f"marp tts failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
