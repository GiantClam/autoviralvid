"""V7 API routes: schema-first validation + TTS/action alignment + MiniMax export."""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Dict, List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException

from src.auth import AuthUser, get_current_user
from src.schemas.ppt_v3 import ApiResponse
from src.schemas.ppt_v7 import SlideAction, SlideData

logger = logging.getLogger("v7_routes")
router = APIRouter(prefix="/api/v1/v7", tags=["PPT v7"])


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|(?:\d+[.)]))\s+(.+?)\s*$")
_HTML_RE = re.compile(r"<[^>]+>")


def _strip_md_text(text: str) -> str:
    cleaned = _HTML_RE.sub(" ", text or "")
    cleaned = cleaned.replace("`", " ").replace("*", " ").replace("_", " ").replace("#", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_title_and_points(markdown: str, fallback_title: str) -> tuple[str, List[str]]:
    title = fallback_title
    points: List[str] = []
    for raw in (markdown or "").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("<!--"):
            continue
        heading = _HEADING_RE.match(line)
        if heading and title == fallback_title:
            parsed = _strip_md_text(heading.group(1))
            if parsed:
                title = parsed
            continue
        bullet = _LIST_RE.match(line)
        if bullet:
            parsed = _strip_md_text(bullet.group(1))
            if parsed:
                points.append(parsed)
            continue
        plain = _strip_md_text(line)
        if plain and len(plain) >= 3:
            points.append(plain)

    dedup: List[str] = []
    seen = set()
    for item in points:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
        if len(dedup) >= 8:
            break
    return title, dedup


def _slide_to_minimax_source(slide: SlideData) -> Dict[str, Any]:
    fallback_title = f"Slide {slide.page_number}"
    title, points = _extract_title_and_points(slide.markdown, fallback_title)
    script_text = " ".join(line.text.strip() for line in slide.script if line.text.strip()).strip()
    slide_id = slide.slide_id or f"slide-{slide.page_number}"

    table_rows: List[List[str]] = []
    if "|" in (slide.markdown or ""):
        for raw in slide.markdown.splitlines():
            if "|" not in raw:
                continue
            row = [cell.strip() for cell in raw.split("|") if cell.strip()]
            if row and not all(set(cell) <= {"-"} for cell in row):
                table_rows.append(row)
        if len(table_rows) < 2:
            table_rows = []

    elements: List[Dict[str, Any]] = []
    if points:
        elements.append(
            {
                "id": f"{slide_id}-points",
                "block_id": f"{slide_id}-points",
                "type": "text",
                "top": 0,
                "content": "\n".join(points),
            }
        )
    if table_rows:
        elements.append(
            {
                "id": f"{slide_id}-table",
                "block_id": f"{slide_id}-table",
                "type": "table",
                "table_rows": table_rows[:6],
            }
        )

    return {
        "id": slide_id,
        "slide_id": slide_id,
        "title": title,
        "elements": elements,
        "narration": script_text,
        "speaker_notes": script_text,
        "duration": max(3.0, float(slide.duration or 0.0)),
        "narration_audio_url": slide.narration_audio_url or "",
        "slide_type": slide.slide_type,
    }


def _slides_to_minimax_sources(slides: List[SlideData]) -> List[Dict[str, Any]]:
    return [_slide_to_minimax_source(s) for s in slides]


def _build_image_video_slides(
    image_urls: List[str],
    slides: List[SlideData],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, url in enumerate(image_urls):
        src = slides[idx] if idx < len(slides) else None
        duration = 6.0
        audio_url = ""
        if src is not None:
            duration = max(3.0, float(src.duration or 0.0))
            audio_url = str(src.narration_audio_url or "").strip()
        item: Dict[str, Any] = {
            "imageUrl": _presign_r2_get_url_if_needed(url),
            "duration": duration,
        }
        if audio_url:
            item["audioUrl"] = _presign_r2_get_url_if_needed(audio_url)
        out.append(item)
    return out


def _presign_r2_get_url_if_needed(url: str, expires: int = 24 * 3600) -> str:
    raw = str(url or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return raw
    if "X-Amz-Signature=" in raw or "x-amz-signature=" in raw.lower():
        return raw

    configured_public = str(os.getenv("R2_PUBLIC_BASE", "")).strip()
    configured_host = urlparse(configured_public).netloc.lower() if configured_public else ""
    configured_hosts = {
        host.strip().lower()
        for host in str(os.getenv("R2_PUBLIC_HOSTS", "")).split(",")
        if host.strip()
    }
    if configured_host:
        configured_hosts.add(configured_host)
    host = parsed.netloc.lower()
    host_allowed = (
        host in configured_hosts
        if configured_hosts
        else (host.endswith(".r2.dev") or host.endswith(".autoviralvid.com"))
    )
    if not host_allowed:
        return raw

    key = parsed.path.lstrip("/")
    if not key:
        return raw

    try:
        from src.r2 import get_r2_client

        r2 = get_r2_client()
        if not r2:
            return raw
        bucket = os.getenv("R2_BUCKET", "video")
        signed = r2.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires,
        )
        return str(signed or raw)
    except Exception:
        return raw


def _presign_video_slides(slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in slides:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if row.get("imageUrl"):
            row["imageUrl"] = _presign_r2_get_url_if_needed(str(row.get("imageUrl")))
        if row.get("audioUrl"):
            row["audioUrl"] = _presign_r2_get_url_if_needed(str(row.get("audioUrl")))
        out.append(row)
    return out


def _tokenize_for_timeline(text: str) -> List[str]:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return []
    # Chinese chunks / number chunks / English words.
    tokens = re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9.%+-]+", normalized)
    return [t for t in tokens if t]


def _estimate_word_timestamps(narration: str, duration_secs: float) -> List[Dict[str, Any]]:
    if duration_secs <= 0:
        return []
    tokens = _tokenize_for_timeline(narration)
    if not tokens:
        return []
    total_chars = max(1, sum(len(t) for t in tokens))
    cursor = 0.0
    out: List[Dict[str, Any]] = []
    for token in tokens:
        span = max(0.04, duration_secs * (len(token) / total_chars))
        start = min(duration_secs, cursor)
        end = min(duration_secs, cursor + span)
        out.append({"word": token, "start": start, "end": end})
        cursor += span
    return out


def _align_action_start_frames(
    actions: List[SlideAction],
    narration: str,
    duration_secs: float,
    fps: int = 30,
) -> List[SlideAction]:
    if not actions:
        return actions
    duration = max(0.1, float(duration_secs))
    timestamps = _estimate_word_timestamps(narration, duration)
    aligned: List[SlideAction] = []

    for action in actions:
        current = action.model_copy(deep=True)
        if current.type == "highlight":
            keyword = (current.keyword or "").strip()
            frame = None
            if keyword and timestamps:
                for item in timestamps:
                    if keyword in str(item["word"]):
                        frame = int(float(item["start"]) * fps)
                        break
            if frame is None and keyword:
                idx = max(0, (narration or "").find(keyword))
                ratio = idx / max(1, len(narration or ""))
                frame = int(ratio * duration * fps)
            current.startFrame = max(0, frame if frame is not None else int(0.2 * duration * fps))
        elif current.startFrame <= 0:
            if current.type == "appear_items":
                current.startFrame = int(0.25 * duration * fps)
            elif current.type == "circle":
                current.startFrame = int(0.35 * duration * fps)
            elif current.type == "zoom_in":
                current.startFrame = int(0.45 * duration * fps)
        aligned.append(current)
    return aligned


def _parse_slides(slides: Any) -> List[SlideData]:
    if not isinstance(slides, list):
        raise HTTPException(status_code=400, detail="slides must be a list")
    parsed: List[SlideData] = []
    for idx, item in enumerate(slides):
        try:
            parsed.append(SlideData.model_validate(item))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invalid slide at index {idx}: {exc}") from exc
    return parsed


@router.post("/generate", response_model=ApiResponse)
async def generate(req: dict, user: AuthUser = Depends(get_current_user)):
    """Generate v7 slides with planner+mapper and strict schema checks."""
    try:
        from src.premium_generator_v7 import generate_v7

        result = await generate_v7(
            requirement=req.get("requirement", ""),
            num_slides=req.get("num_slides", 10),
            language=req.get("language", "zh-CN"),
            ai_call=req.get("ai_call"),  # test hook (optional)
        )
        # Defensive validation at route boundary.
        slides = _parse_slides(result.get("slides", []))
        result["slides"] = [s.model_dump(mode="json") for s in slides]
        return ApiResponse(success=True, data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("v7 generate failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tts", response_model=ApiResponse)
async def synthesize_tts(req: dict, user: AuthUser = Depends(get_current_user)):
    """Synthesize TTS and align actions to estimated word-level timeline."""
    try:
        from src.tts_synthesizer import synthesize_batch

        slides = _parse_slides(req.get("slides", []))

        narrations: List[str] = []
        for slide in slides:
            merged = "\n".join(line.text for line in slide.script if line.text.strip()).strip()
            narrations.append(merged)

        if not any(narrations):
            return ApiResponse(success=True, data={"slides": [s.model_dump(mode="json") for s in slides]})

        voice_style = req.get("voice_style", "zh-CN-female")
        urls, durations = await synthesize_batch(narrations, voice_style)

        for i, slide in enumerate(slides):
            audio_url = urls[i] if i < len(urls) else ""
            duration = float(durations[i]) if i < len(durations) else 0.0
            if audio_url:
                slide.narration_audio_url = audio_url
            slide.duration = max(2.0, duration + 0.8)
            slide.actions = _align_action_start_frames(
                actions=slide.actions,
                narration=narrations[i],
                duration_secs=slide.duration,
                fps=30,
            )

        return ApiResponse(success=True, data={"slides": [s.model_dump(mode="json") for s in slides]})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("v7 tts failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export", response_model=ApiResponse)
async def export(req: dict, user: AuthUser = Depends(get_current_user)):
    """
    Export with MiniMax PPTX generator.
    """
    from src.minimax_exporter import MiniMaxExportError, export_minimax_pptx

    try:
        from src.r2 import upload_bytes_to_r2

        slides = _parse_slides(req.get("slides", []))
        run_id = uuid.uuid4().hex[:12]
        title = str(req.get("title", "")).strip() or _extract_title_and_points(
            slides[0].markdown if slides else "",
            "PPT V7 Deck",
        )[0]
        style_variant = str(req.get("minimax_style_variant", "auto") or "auto")
        palette_key = str(req.get("minimax_palette_key", "auto") or "auto")
        verbatim_content = bool(req.get("verbatim_content", False))
        retry_scope = str(req.get("retry_scope", "deck") or "deck")
        target_slide_ids = [str(s).strip() for s in req.get("target_slide_ids", []) if str(s).strip()]
        target_block_ids = [str(s).strip() for s in req.get("target_block_ids", []) if str(s).strip()]
        retry_hint = str(req.get("retry_hint", "") or "")
        idempotency_key = str(req.get("idempotency_key", "") or "")
        allow_legacy_mode = str(
            os.getenv("PPT_ALLOW_LEGACY_MODE", "false")
        ).strip().lower() not in {"0", "false", "no", "off"}
        requested_generator_mode = str(req.get("generator_mode", "official") or "official").strip().lower()
        if requested_generator_mode == "legacy" and not allow_legacy_mode:
            requested_generator_mode = "official"
        elif requested_generator_mode not in {"official", "legacy"}:
            requested_generator_mode = str(os.getenv("PPT_GENERATOR_MODE", "official")).strip().lower()
            if requested_generator_mode == "legacy" and not allow_legacy_mode:
                requested_generator_mode = "official"
            if requested_generator_mode not in {"official", "legacy"}:
                requested_generator_mode = "official"
        enable_legacy_fallback = (
            str(os.getenv("PPT_ENABLE_LEGACY_FALLBACK", "false")).strip().lower()
            not in {"0", "false", "no", "off"}
        ) and allow_legacy_mode
        original_style = bool(req.get("original_style", True))
        disable_local_style_rewrite = bool(req.get("disable_local_style_rewrite", True))
        visual_priority = bool(req.get("visual_priority", True))
        visual_preset = str(req.get("visual_preset", "auto") or "auto")
        visual_density = str(req.get("visual_density", "balanced") or "balanced")
        constraint_hardness = str(req.get("constraint_hardness", "minimal") or "minimal")
        if constraint_hardness not in {"minimal", "balanced"}:
            constraint_hardness = "minimal"

        source_slides = _slides_to_minimax_sources(slides)
        export_result = export_minimax_pptx(
            slides=source_slides,
            title=title,
            author="AutoViralVid",
            style_variant=style_variant,
            palette_key=palette_key,
            verbatim_content=verbatim_content,
            deck_id=run_id,
            retry_scope=retry_scope,
            target_slide_ids=target_slide_ids,
            target_block_ids=target_block_ids,
            retry_hint=retry_hint,
            idempotency_key=idempotency_key,
            generator_mode=requested_generator_mode,
            enable_legacy_fallback=enable_legacy_fallback,
            original_style=original_style,
            disable_local_style_rewrite=disable_local_style_rewrite,
            visual_priority=visual_priority,
            visual_preset=visual_preset,
            visual_density=visual_density,
            constraint_hardness=constraint_hardness,
            timeout=180,
        )
        pptx_bytes = export_result["pptx_bytes"]
        pptx_url = await upload_bytes_to_r2(
            pptx_bytes,
            key=f"projects/{run_id}/pptx/presentation.pptx",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        slide_image_urls: List[str] = []
        try:
            from src.pptx_rasterizer import rasterize_pptx_bytes_to_png_bytes

            png_bytes_list = rasterize_pptx_bytes_to_png_bytes(pptx_bytes)
            for idx, png_bytes in enumerate(png_bytes_list):
                image_url = await upload_bytes_to_r2(
                    png_bytes,
                    key=f"projects/{run_id}/slides/slide_{idx + 1:03d}.png",
                    content_type="image/png",
                )
                slide_image_urls.append(image_url)
        except Exception as raster_exc:
            logger.warning("v7 export rasterize failed: %s", raster_exc)

        render_spec = export_result.get("render_spec") or {}
        video_slides = render_spec.get("slides") if isinstance(render_spec, dict) else None
        exported_slide_count = (
            len(video_slides)
            if isinstance(video_slides, list) and video_slides
            else int((export_result.get("generator_meta") or {}).get("render_slides") or len(slides))
        )
        if slide_image_urls:
            exported_slide_count = len(slide_image_urls)

        data: Dict[str, Any] = {
            "run_id": run_id,
            "pptx_url": pptx_url,
            "slide_image_urls": slide_image_urls,
            "slide_count": exported_slide_count,
            "skill": "minimax_pptx_generator",
            "generator_mode": export_result.get("generator_mode", requested_generator_mode),
        }
        if export_result.get("generator_meta"):
            data["generator_meta"] = export_result["generator_meta"]
        if slide_image_urls:
            data["video_mode"] = "ppt_image_slideshow"
            data["video_slides"] = _build_image_video_slides(slide_image_urls, slides)
            data["video_slide_count"] = len(slide_image_urls)
        elif isinstance(render_spec, dict):
            data["video_mode"] = render_spec.get("mode", "minimax_presentation")
        if not slide_image_urls and isinstance(video_slides, list) and video_slides:
            safe_video_slides = _presign_video_slides(video_slides)
            data["video_slides"] = safe_video_slides
            data["video_slide_count"] = len(safe_video_slides)

        return ApiResponse(success=True, data=data)
    except HTTPException:
        raise
    except MiniMaxExportError as e:
        logger.error("v7 export failed classified: %s", e, exc_info=True)
        return ApiResponse(success=False, data={"failure": e.to_dict()}, error=str(e))
    except Exception as e:
        logger.error("v7 export failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
