"""
音频分割模块：支持长音频自动分段，用于数字人视频生成

功能：
1. 获取音频时长
2. 按最大段时长分割音频（优先在静音点切割）
3. 每段上传到 R2，返回 CDN URL 列表
"""

import os
import asyncio
import tempfile
import logging
from typing import List, Optional
from dataclasses import dataclass

import httpx

logger = logging.getLogger("audio_splitter")

# ---------- 常量 ----------
MAX_SINGLE_SEGMENT_SECONDS = 45       # 单段最大时长（秒）
DEFAULT_SEGMENT_SECONDS = 45          # 默认分割时长
SILENCE_THRESH_DB = -40               # 静音检测阈值 dBFS
MIN_SILENCE_LEN_MS = 300              # 最小静音间隔（毫秒）
SILENCE_SEARCH_WINDOW_MS = 4000       # 切割点前后搜索窗口（毫秒）
MIN_LAST_SEGMENT_MS = int(float(os.getenv("AUDIO_SPLITTER_MIN_LAST_SEGMENT_SECONDS", "10")) * 1000)


@dataclass
class SegmentInfo:
    """音频分段信息"""
    index: int
    url: str
    start_ms: int
    end_ms: int
    duration_s: float


def _is_r2_url(url: str) -> bool:
    """Check if a URL is a Cloudflare R2 public URL (including custom domains)."""
    if ".r2.dev/" in url or "r2.cloudflarestorage.com/" in url:
        return True
    # Also match the R2_PUBLIC_BASE custom domain
    public_base = os.getenv("R2_PUBLIC_BASE", "")
    if public_base and url.startswith(public_base):
        return True
    return False


def _extract_r2_key(url: str) -> Optional[str]:
    """Extract the object key from an R2 URL.

    Handles patterns like:
    - https://pub-{id}.r2.dev/{key}
    - https://{id}.r2.cloudflarestorage.com/{bucket}/{key}
    - https://{custom_domain}/{key}  (with R2_PUBLIC_BASE)
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = parsed.path.lstrip("/")

    # Check if the host matches R2 public bucket format
    if ".r2.dev" in parsed.hostname:
        return path  # path IS the key

    # Check if it matches R2_PUBLIC_BASE
    public_base = os.getenv("R2_PUBLIC_BASE", "")
    if public_base and url.startswith(public_base):
        return url[len(public_base.rstrip("/")):].lstrip("/")

    return path  # fallback: use full path as key


def _download_from_r2_sync(key: str, dest_path: str) -> bool:
    """Download a file directly from R2 using S3 client (bypasses public access).

    This is a synchronous function — call via ``asyncio.to_thread`` from async code.
    Returns True on success, False if R2 is not configured.
    """
    from src.r2 import get_r2_client

    r2 = get_r2_client()
    if not r2:
        return False

    bucket = os.getenv("R2_BUCKET", "video")
    try:
        r2.download_file(bucket, key, dest_path)
        logger.info(
            f"[audio_splitter] Downloaded from R2 (S3): key={key} -> {dest_path} "
            f"({os.path.getsize(dest_path)} bytes)"
        )
        return True
    except Exception as exc:
        logger.warning(f"[audio_splitter] R2 S3 download failed for key={key}: {exc}")
        return False


async def _download_audio(url: str, dest_path: str) -> None:
    """下载远程音频文件到本地。

    优先使用 R2 S3 客户端直接下载（避免公共访问 401 问题），
    如果不是 R2 URL 或 R2 未配置，则回退到 HTTP 下载。
    """
    # If this is an R2 URL, try direct S3 download first (avoids 401 on pub-*.r2.dev)
    if _is_r2_url(url):
        key = _extract_r2_key(url)
        if key:
            downloaded = await asyncio.to_thread(_download_from_r2_sync, key, dest_path)
            if downloaded:
                return
            logger.info(f"[audio_splitter] R2 S3 download unavailable, falling back to HTTP for {url}")

    # Fallback: HTTP download
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(resp.content)
    logger.info(f"[audio_splitter] Downloaded audio (HTTP): {url} -> {dest_path} ({os.path.getsize(dest_path)} bytes)")


def _upload_bytes_to_r2(data: bytes, key: str, content_type: str = "audio/mpeg") -> str:
    """将字节数据上传到 R2，返回公网 URL"""
    from src.r2 import get_r2_client

    bucket = os.getenv("R2_BUCKET", "video")
    r2 = get_r2_client()
    if not r2:
        raise RuntimeError("R2 未配置，无法上传音频分段")

    r2.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

    public_base = os.getenv("R2_PUBLIC_BASE")
    if public_base:
        return f"{public_base.rstrip('/')}/{key}"
    account_id = os.getenv("R2_ACCOUNT_ID")
    return f"https://pub-{account_id}.r2.dev/{key}"


async def get_audio_duration(url: str) -> float:
    """
    获取远程音频文件的时长（秒）

    Args:
        url: 音频文件 URL

    Returns:
        音频时长（秒）
    """
    from pydub import AudioSegment

    tmpdir = tempfile.mkdtemp(prefix="audio_dur_")
    try:
        audio_path = os.path.join(tmpdir, "audio_file")
        await _download_audio(url, audio_path)
        audio = AudioSegment.from_file(audio_path)
        duration_s = len(audio) / 1000.0
        logger.info(f"[audio_splitter] Audio duration: {duration_s:.1f}s")
        return duration_s
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def _find_best_split_point(audio: "AudioSegment", target_ms: int, window_ms: int = SILENCE_SEARCH_WINDOW_MS) -> int:
    """
    在 target_ms 附近寻找最佳分割点（优先静音位置）

    Args:
        audio: 完整音频
        target_ms: 目标切割位置（毫秒）
        window_ms: 前后搜索窗口（毫秒）

    Returns:
        最佳切割位置（毫秒）
    """
    from pydub.silence import detect_silence

    total_ms = len(audio)
    search_start = max(0, target_ms - window_ms // 2)
    search_end = min(total_ms, target_ms + window_ms // 2)

    # 在搜索窗口内检测静音段
    segment = audio[search_start:search_end]
    silences = detect_silence(
        segment,
        min_silence_len=MIN_SILENCE_LEN_MS,
        silence_thresh=SILENCE_THRESH_DB,
    )

    if silences:
        # 选择离 target_ms 最近的静音段中点
        best_silence = min(
            silences,
            key=lambda s: abs((search_start + (s[0] + s[1]) // 2) - target_ms),
        )
        split_point = search_start + (best_silence[0] + best_silence[1]) // 2
        logger.debug(
            f"[audio_splitter] Found silence near {target_ms}ms, "
            f"splitting at {split_point}ms (silence: {best_silence})"
        )
        return split_point

    # 没有找到静音点，使用目标位置
    logger.debug(f"[audio_splitter] No silence found near {target_ms}ms, using target directly")
    return target_ms


async def split_audio(
    url: str,
    run_id: str,
    max_segment_seconds: float = DEFAULT_SEGMENT_SECONDS,
) -> List[SegmentInfo]:
    """
    分割音频为多段，每段上传到 R2

    Args:
        url: 音频文件 URL
        run_id: 运行 ID，用于生成 R2 key
        max_segment_seconds: 每段最大时长（秒），默认 45s

    Returns:
        分段信息列表，按顺序排列
    """
    from pydub import AudioSegment

    tmpdir = tempfile.mkdtemp(prefix=f"audio_split_{run_id}_")
    try:
        # 1. 下载完整音频
        audio_path = os.path.join(tmpdir, "full_audio")
        await _download_audio(url, audio_path)
        audio = AudioSegment.from_file(audio_path)
        total_ms = len(audio)
        total_s = total_ms / 1000.0

        logger.info(
            f"[audio_splitter] Audio loaded: {total_s:.1f}s, "
            f"max_segment={max_segment_seconds}s"
        )

        # 2. 如果不需要分割
        if total_s <= max_segment_seconds:
            logger.info("[audio_splitter] Audio is short enough, no splitting needed")
            return [
                SegmentInfo(
                    index=0,
                    url=url,
                    start_ms=0,
                    end_ms=total_ms,
                    duration_s=total_s,
                )
            ]

        # 3. 计算分割点
        max_seg_ms = int(max_segment_seconds * 1000)
        split_points = [0]  # 起始点
        current_ms = 0

        while current_ms + max_seg_ms < total_ms:
            target = current_ms + max_seg_ms
            # 在目标位置附近寻找静音点
            best_point = _find_best_split_point(audio, target)
            # 确保不会产生过短的最后一段（< 10s 则并入前一段）
            remaining = total_ms - best_point
            if remaining < MIN_LAST_SEGMENT_MS and len(split_points) > 0:
                logger.debug(
                    f"[audio_splitter] Remaining {remaining}ms too short, "
                    f"skipping split at {best_point}ms"
                )
                break
            split_points.append(best_point)
            current_ms = best_point

        split_points.append(total_ms)  # 结束点

        num_segments = len(split_points) - 1
        logger.info(
            f"[audio_splitter] Splitting into {num_segments} segments: "
            f"{[f'{(split_points[i+1]-split_points[i])/1000:.1f}s' for i in range(num_segments)]}"
        )

        # 4. 切割并上传每段
        segments: List[SegmentInfo] = []

        for i in range(num_segments):
            start_ms = split_points[i]
            end_ms = split_points[i + 1]
            segment_audio = audio[start_ms:end_ms]
            duration_s = (end_ms - start_ms) / 1000.0

            # 导出为 mp3
            seg_path = os.path.join(tmpdir, f"segment_{i}.mp3")
            segment_audio.export(seg_path, format="mp3", bitrate="192k")
            seg_size = os.path.getsize(seg_path)

            logger.info(
                f"[audio_splitter] Segment {i}: {start_ms}ms-{end_ms}ms "
                f"({duration_s:.1f}s), size={seg_size} bytes"
            )

            # 上传到 R2
            with open(seg_path, "rb") as f:
                seg_data = f.read()

            r2_key = f"{run_id}_dh_audio_seg_{i}.mp3"
            seg_url = await asyncio.get_event_loop().run_in_executor(
                None, _upload_bytes_to_r2, seg_data, r2_key
            )

            segments.append(
                SegmentInfo(
                    index=i,
                    url=seg_url,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    duration_s=duration_s,
                )
            )

        logger.info(
            f"[audio_splitter] Split complete: {len(segments)} segments, "
            f"total {total_s:.1f}s"
        )
        return segments

    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
