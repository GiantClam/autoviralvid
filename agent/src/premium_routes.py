"""Premium PPT API 路由"""

from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException

from src.auth import get_current_user, AuthUser
from src.schemas.ppt_v3 import ApiResponse

logger = logging.getLogger("premium_routes")
router = APIRouter(prefix="/api/v1/premium", tags=["Premium"])


@router.post("/generate", response_model=ApiResponse)
async def generate(req: dict, user: AuthUser = Depends(get_current_user)):
    """生成 premium PPT 数据 (7种模板+丰富内容)"""
    try:
        from src.premium_generator import generate

        slides = await generate(
            requirement=req.get("requirement", ""),
            num_slides=req.get("num_slides", 10),
            language=req.get("language", "zh-CN"),
        )
        return ApiResponse(success=True, data=slides)
    except Exception as e:
        logger.error(f"premium generate failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tts", response_model=ApiResponse)
async def synthesize_tts(req: dict, user: AuthUser = Depends(get_current_user)):
    """为 premium slides 合成 TTS (v3 格式: script[].text)"""
    try:
        from src.tts_synthesizer import synthesize_batch

        slides = req.get("slides", [])

        # 收集所有台词
        all_texts = []
        for s in slides:
            for line in s.get("script", []):
                text = line.get("text", "") if isinstance(line, dict) else str(line)
                if text:
                    all_texts.append(text)

        if not all_texts:
            return ApiResponse(success=True, data={"slides": slides})

        urls, durations = await synthesize_batch(all_texts, "zh-CN-male")

        # 回填到 script 行
        idx = 0
        for s in slides:
            total_dur = 0
            for line in s.get("script", []):
                if isinstance(line, dict) and line.get("text"):
                    if idx < len(urls) and urls[idx]:
                        line["audio_url"] = urls[idx]
                        line["audio_duration"] = (
                            durations[idx] if idx < len(durations) else 10
                        )
                    total_dur += line.get("audio_duration", 0)
                    idx += 1
            s["duration"] = max(2, total_dur + 1)

        return ApiResponse(success=True, data={"slides": slides})
    except Exception as e:
        logger.error(f"premium tts failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
