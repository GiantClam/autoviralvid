"""渲染器 — 支持本地渲染 + Lambda 分布式渲染"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("lambda_renderer")

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
REMOTION_LAMBDA_FUNCTION = os.getenv("REMOTION_LAMBDA_FUNCTION", "")
REMOTION_SERVE_URL = os.getenv("REMOTION_SERVE_URL", "")

_RENDER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _local_tmp_root() -> str:
    root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "renders", "tmp"))
    os.makedirs(root, exist_ok=True)
    return root
_SUBPROCESS_TIMEOUT = 600  # 10分钟


# ════════════════════════════════════════════════════════════════════
# 统一入口
# ════════════════════════════════════════════════════════════════════


async def start_render(
    slides: List[Dict[str, Any]],
    config: Dict[str, Any],
    webhook_url: Optional[str] = None,
    prefer_local: bool = False,
) -> Dict[str, Any]:
    """
    启动渲染，自动选择后端:
    - prefer_local=True 或 Lambda 未配置 → 本机 Chrome + FFmpeg 渲染
    - Lambda 已配置 → AWS Lambda 分布式渲染

    Returns: {"render_id", "video_url", "cost", "mode"}
    """
    lambda_ok = bool(REMOTION_LAMBDA_FUNCTION and REMOTION_SERVE_URL)

    if prefer_local or not lambda_ok:
        if not lambda_ok and not prefer_local:
            logger.info("[renderer] Lambda not configured, using local render")
        return await start_local_render(slides, config)
    else:
        return await start_lambda_render(slides, config, webhook_url)


# ════════════════════════════════════════════════════════════════════
# 本地渲染 (本机 Chrome + FFmpeg)
# ════════════════════════════════════════════════════════════════════


async def start_local_render(
    slides: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    本地渲染 — @remotion/renderer 本机 Chrome 渲染帧 + FFmpeg 编码
    不依赖 AWS Lambda，适合开发测试和无 Lambda 环境
    """
    import uuid

    rid = uuid.uuid4().hex[:12]
    tmp_root = _local_tmp_root()
    input_path = os.path.join(tmp_root, f"render_input_{rid}.json")
    with open(input_path, "w", encoding="utf-8") as f:
        json.dump({"slides": slides, "config": config}, f, ensure_ascii=False)

    output_path = os.path.join(tmp_root, f"remotion_{rid}.mp4")

    try:
        script = os.path.join(
            os.path.dirname(__file__), "..", "..", "scripts", "render-local.mjs"
        )
        if not os.path.exists(script):
            raise RuntimeError(f"Local render script missing: {script}")

        logger.info(f"[renderer] LOCAL render: {len(slides)} slides")

        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                [
                    "node",
                    script,
                    "--input",
                    input_path,
                    "--output",
                    output_path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_SUBPROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Local render timed out after {_SUBPROCESS_TIMEOUT}s")

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "Unknown error")[:2000]
            if "eperm" in err.lower():
                logger.warning(
                    "[renderer] local remotion EPERM, fallback to screenshot+ffmpeg"
                )
                try:
                    await asyncio.to_thread(
                        _render_fallback_video,
                        slides=slides,
                        config=config,
                        output_path=output_path,
                    )
                except Exception as fb_exc:
                    raise RuntimeError(
                        f"Local render failed: {err}\nFallback failed: {fb_exc}"
                    ) from fb_exc
            else:
                raise RuntimeError(f"Local render failed: {err}")

        # 尝试上传 R2
        video_url = output_path
        try:
            from src.r2 import upload_bytes_to_r2

            with open(output_path, "rb") as f:
                data = f.read()
            key = f"projects/{uuid.uuid4().hex[:12]}/video/final.mp4"
            video_url = await upload_bytes_to_r2(data, key, content_type="video/mp4")
            logger.info(f"[renderer] Uploaded to R2: {video_url}")
        except Exception as e:
            logger.warning(f"[renderer] R2 upload skipped: {e}")

        render_id = uuid.uuid4().hex[:12]
        logger.info(f"[renderer] LOCAL render done: {render_id}")

        return {
            "render_id": render_id,
            "video_url": video_url,
            "cost": 0,
            "mode": "local",
        }
    finally:
        try:
            os.unlink(input_path)
        except Exception:
            pass


def _to_plain_text(value: Any) -> str:
    txt = str(value or "")
    txt = _HTML_TAG_RE.sub(" ", txt)
    txt = (
        txt.replace("&nbsp;", " ")
        .replace("&bull;", " ")
        .replace("•", " ")
        .replace("<br/>", "\n")
        .replace("<br>", "\n")
    )
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def _extract_slide_lines(slide: Dict[str, Any], idx: int) -> tuple[str, List[str]]:
    title = _to_plain_text(slide.get("title") or f"Slide {idx + 1}")
    lines: List[str] = []
    for el in slide.get("elements") or []:
        if isinstance(el, dict) and str(el.get("type")) == "text":
            txt = _to_plain_text(el.get("content"))
            if txt:
                parts = re.split(r"[\n?]", txt)
                for part in parts:
                    line = _to_plain_text(part)
                    if line:
                        lines.append(line)
    if not lines:
        md = _to_plain_text(slide.get("markdown"))
        if md:
            lines.append(md)
    if not lines:
        lines.append(title)
    return title, lines[:8]


def _is_image_slide(slide: Dict[str, Any]) -> bool:
    return bool(str(slide.get("imageUrl") or slide.get("image_url") or "").strip())


def _render_fallback_video(
    slides: List[Dict[str, Any]],
    config: Dict[str, Any],
    output_path: str,
) -> None:
    width = int(config.get("width", 1280))
    height = int(config.get("height", 720))
    fps = int(config.get("fps", 30))

    tmpdir = os.path.join(
        _local_tmp_root(), f"fallback_{os.getpid()}_{int(time.time() * 1000)}"
    )
    os.makedirs(tmpdir, exist_ok=True)
    try:
        clip_paths: List[str] = []
        image_mode = len(slides) > 0 and all(_is_image_slide(s) for s in slides)
        font = "C\\:/Windows/Fonts/msyh.ttc"
        for i, slide in enumerate(slides):
            dur = max(1.5, float(slide.get("duration") or 6))
            clip = os.path.join(tmpdir, f"clip_{i:03d}.mp4")
            if image_mode:
                image_url = str(slide.get("imageUrl") or slide.get("image_url") or "").strip()
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    image_url,
                    "-t",
                    f"{dur:.2f}",
                    "-vf",
                    (
                        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                        f"crop={width}:{height},zoompan=z='min(zoom+0.0006,1.06)':d=1:s={width}x{height}"
                    ),
                    "-r",
                    str(fps),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    clip,
                ]
            else:
                title, lines = _extract_slide_lines(slide, i)
                text_path = os.path.join(tmpdir, f"slide_{i:03d}.txt")
                text_content = title + "\n\n" + "\n".join(f"- {line}" for line in lines[:6])
                with open(text_path, "w", encoding="utf-8") as tf:
                    tf.write(text_content)

                cmd = [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=0x0f172a:s={width}x{height}:d={dur:.2f}",
                    "-vf",
                    f"drawtext=fontfile='{font}':textfile='slide_{i:03d}.txt':fontcolor=white:fontsize=38:line_spacing=12:x=72:y=72",
                    "-r",
                    str(fps),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    clip,
                ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                cwd=tmpdir,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg clip failed: {proc.stderr[:500]}")
            clip_paths.append(clip)

        concat_list = os.path.join(tmpdir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for clip in clip_paths:
                escaped = clip.replace("'", "''")
                f.write(f"file '{escaped}'\n")

        merge = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            output_path,
        ]
        merge_proc = subprocess.run(
            merge,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if merge_proc.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {merge_proc.stderr[:500]}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


async def start_lambda_render(
    slides: List[Dict[str, Any]],
    config: Dict[str, Any],
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """AWS Lambda 分布式渲染"""
    import uuid

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"slides": slides, "config": config}, f)
        input_path = f.name

    try:
        script = os.path.join(
            os.path.dirname(__file__), "..", "..", "scripts", "render-presentation.mjs"
        )
        cmd = ["node", script, "--input", input_path]
        if webhook_url:
            cmd.extend(["--webhook", webhook_url])

        env = {
            **os.environ,
            "REMOTION_LAMBDA_FUNCTION": REMOTION_LAMBDA_FUNCTION,
            "AWS_REGION": AWS_REGION,
            "REMOTION_SERVE_URL": REMOTION_SERVE_URL,
        }

        logger.info(f"[renderer] LAMBDA render: {len(slides)} slides")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_SUBPROCESS_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"Lambda render timed out after {_SUBPROCESS_TIMEOUT}s")

        if proc.returncode != 0:
            err = stderr.decode()[:2000] if stderr else "Unknown error"
            raise RuntimeError(f"Lambda render failed: {err}")

        result = json.loads(stdout.decode())
        return {
            "render_id": result.get("renderId"),
            "video_url": result.get("videoUrl"),
            "cost": result.get("costsInDollars", 0),
            "mode": "lambda",
        }
    finally:
        try:
            os.unlink(input_path)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════
# 进度查询
# ════════════════════════════════════════════════════════════════════


async def get_render_progress(render_id: str) -> Dict[str, Any]:
    if not _RENDER_ID_PATTERN.match(render_id):
        return {
            "render_id": render_id,
            "status": "invalid",
            "progress": 0,
            "output_url": None,
        }

    # Supabase 回退
    try:
        from supabase import create_client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv(
            "SUPABASE_SERVICE_KEY"
        )
        if url and key:
            sb = create_client(url, key)
            res = (
                sb.table("ppt_render_jobs")
                .select("*")
                .eq("lambda_job_id", render_id)
                .limit(1)
                .execute()
            )
            if res.data:
                row = res.data[0]
                return {
                    "render_id": render_id,
                    "status": row.get("status", "unknown"),
                    "progress": row.get("progress", 0),
                    "output_url": row.get("output_url"),
                    "error": row.get("error"),
                }
    except Exception:
        pass

    return {
        "render_id": render_id,
        "status": "unknown",
        "progress": 0,
        "output_url": None,
    }
