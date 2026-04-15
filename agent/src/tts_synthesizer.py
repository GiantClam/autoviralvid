"""TTS合成器 — 使用 Minimax API 将讲解文本转为音频"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
from typing import List, Optional

import httpx

from src.r2 import upload_bytes_to_r2

logger = logging.getLogger("tts_synthesizer")

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_SPEECH_MODEL = os.getenv("MINIMAX_SPEECH_MODEL", "speech-2.6-turbo")
MINIMAX_TTS_URL = "https://api.minimaxi.com/v1/t2a_v2"

# 全局并发控制 (跨所有请求)
_GLOBAL_TTS_SEMAPHORE = asyncio.Semaphore(
    int(os.getenv("TTS_GLOBAL_CONCURRENCY", "10"))
)

# 重试配置
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2  # 指数退避基数


def _voice_id_for_style(style: str) -> str:
    """根据声音风格返回 Minimax voice_id"""
    mapping = {
        "zh-CN-female": "female-shaonv",
        "zh-CN-male": "male-qn-qingse",
        "en-US-female": "female-en-us",
        "en-US-male": "male-en-us",
        "professional-female": "female-yujie",
        "professional-male": "male-dongbei",
        "education-female": "female-shaonv",
        "education-male": "male-qn-qingse",
    }
    return mapping.get(style, "male-qn-qingse")


async def _call_minimax_tts(
    text: str, voice_id: str, client: httpx.AsyncClient
) -> bytes:
    """调用Minimax TTS API，带重试"""
    payload = {
        "model": MINIMAX_SPEECH_MODEL,
        "text": text,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
            "emotion": "neutral",
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 2,
        },
        "stream": False,
    }

    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            r = await client.post(
                MINIMAX_TTS_URL,
                headers={
                    "Authorization": f"Bearer {MINIMAX_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            # 429 限流: 指数退避重试
            if r.status_code == 429:
                wait = _RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    f"[tts] Rate limited, retry in {wait}s (attempt {attempt + 1})"
                )
                await asyncio.sleep(wait)
                continue

            r.raise_for_status()
            data = r.json()

            # 检查业务错误
            br = data.get("base_resp") or {}
            status_code = br.get("status_code")
            if status_code and status_code != 0:
                raise RuntimeError(
                    f"Minimax TTS error code={status_code}: {br.get('status_msg', 'unknown')}"
                )

            # 提取音频
            audio_url = (
                data.get("audio_url")
                or (data.get("data") or {}).get("audio_url")
                or ((data.get("audio_file") or {}).get("url"))
            )
            if audio_url:
                ra = await client.get(audio_url)
                ra.raise_for_status()
                return ra.content

            audio_raw = data.get("audio") or (data.get("data") or {}).get("audio")
            if audio_raw:
                s = str(audio_raw).strip()
                if s.startswith("http"):
                    ra = await client.get(s)
                    ra.raise_for_status()
                    return ra.content
                try:
                    return bytes.fromhex(s)
                except ValueError:
                    return base64.b64decode(s)

            raise RuntimeError("Minimax TTS 未返回音频内容")

        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    f"[tts] HTTP error: {e}, retry in {wait}s (attempt {attempt + 1})"
                )
                await asyncio.sleep(wait)
                continue
            raise

    raise last_error or RuntimeError("TTS failed after retries")


async def synthesize_single(
    text: str,
    voice_style: str = "zh-CN-female",
    scene_index: int = 0,
) -> tuple[str, float]:
    """
    将单段文本合成为音频并上传到 R2。

    Returns:
        (R2 CDN URL, 音频时长秒数)
    """
    if not MINIMAX_API_KEY:
        raise RuntimeError("未配置 MINIMAX_API_KEY")

    meaningful = re.sub(r"\s+", "", text)
    if len(meaningful) < 5:
        raise RuntimeError(f"文本过短 ({len(meaningful)}字)，无法合成")

    voice_id = _voice_id_for_style(voice_style)

    async with _GLOBAL_TTS_SEMAPHORE:
        logger.info(
            f"[tts] Synthesizing scene {scene_index}: voice={voice_id}, text_len={len(text)}"
        )

        async with httpx.AsyncClient(timeout=300) as client:
            audio_bytes = await _call_minimax_tts(text, voice_id, client)

    # 获取音频时长 (ffprobe)
    duration = await _get_audio_duration(audio_bytes)
    logger.info(f"[tts] Scene {scene_index} duration: {duration:.1f}s")

    # 上传到 R2
    import uuid

    audio_key = f"projects/ppt-audio/tts_{uuid.uuid4().hex[:12]}_{scene_index}.mp3"
    url = await upload_bytes_to_r2(audio_bytes, audio_key, content_type="audio/mpeg")

    logger.info(f"[tts] Scene {scene_index} uploaded: {url}")
    return url, duration


async def _get_audio_duration(audio_bytes: bytes) -> float:
    """通过 ffprobe 获取音频时长"""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            raise FileNotFoundError("ffprobe not found in PATH")
        proc = await asyncio.create_subprocess_exec(
            ffprobe_bin,
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            duration_text = stdout.decode(errors="ignore").strip()
            if duration_text:
                return float(duration_text)
            raise RuntimeError("ffprobe returned empty duration output")
        stderr_text = (stderr.decode(errors="ignore") if stderr else "").strip()
        raise RuntimeError(f"ffprobe returncode={proc.returncode} stderr={stderr_text[:200]}")
    except Exception as e:
        logger.warning("[tts] ffprobe failed (%r), estimating from file size", e)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # 降级: 按 MP3 比特率估算 (128kbps)
    return len(audio_bytes) / (128 * 1024 / 8)


async def synthesize_batch(
    texts: List[str],
    voice_style: str = "zh-CN-female",
    max_concurrency: int = 3,
) -> tuple[List[str], List[float]]:
    """
    批量合成TTS音频 (并行)。

    Returns:
        (URL列表, 音频时长列表)
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _limited(idx: int, text: str) -> tuple[int, str, float]:
        async with semaphore:
            url, dur = await synthesize_single(text, voice_style, idx)
            return idx, url, dur

    tasks = [_limited(i, t) for i, t in enumerate(texts) if t.strip()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    urls: List[str] = [""] * len(texts)
    durations: List[float] = [0.0] * len(texts)
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"[tts] Batch item failed: {result}")
            continue
        idx, url, dur = result
        urls[idx] = url
        durations[idx] = dur

    succeeded = sum(1 for u in urls if u)
    logger.info(f"[tts] Batch complete: {succeeded}/{len(texts)} succeeded")
    return urls, durations
