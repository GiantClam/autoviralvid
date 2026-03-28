"""PPT service: generation, export, enhancement and render lifecycle."""

from __future__ import annotations

import html
import hashlib
import json
import logging
import os
import re
import uuid
import base64
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote as url_quote, urlparse
from urllib import error as urllib_error
from urllib import request as urllib_request

from src.schemas.ppt import (
    ContentRequest,
    ExportRequest,
    OutlineRequest,
    ParsedDocument,
    PresentationOutline,
    RenderJob,
    SlideContent,
    VideoRenderConfig,
)
from src.schemas.ppt_outline import LayoutType, OutlinePlan, OutlinePlanRequest, StickyNote
from src.schemas.ppt_pipeline import (
    PPTPipelineArtifacts,
    PPTPipelineRequest,
    PPTPipelineResult,
    PPTPipelineStageStatus,
)
from src.schemas.ppt_plan import (
    ContentBlock,
    PresentationPlan,
    PresentationPlanRequest,
    SlidePlan,
)
from src.schemas.ppt_research import (
    ResearchContext,
    ResearchEvidence,
    ResearchGap,
    ResearchQuestion,
    ResearchRequest,
)
from src.ppt_planning import enforce_layout_diversity, recommend_layout
from src.ppt_template_catalog import (
    resolve_template_for_slide,
    template_profiles as shared_template_profiles,
)

logger = logging.getLogger("ppt_service")

_supabase = None
_local_render_jobs: Dict[str, Dict[str, Any]] = {}
_dot_env_cache: Optional[Dict[str, str]] = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _env_flag(name: str, default: str = "false") -> bool:
    return str(os.getenv(name, default)).strip().lower() not in {"0", "false", "no", "off"}


def _resolve_export_channel(requested: str | None) -> str:
    configured = str(_env_value("PPT_EXPORT_CHANNEL", "local")).strip().lower()
    if configured not in {"local", "remote", "auto"}:
        configured = "local"
    channel = str(requested or "auto").strip().lower()
    if channel not in {"local", "remote", "auto"}:
        channel = "auto"
    if channel == "auto":
        channel = "local" if configured == "auto" else configured
    if channel not in {"local", "remote"}:
        return "local"
    return channel


def _load_local_env() -> Dict[str, str]:
    global _dot_env_cache
    if _dot_env_cache is not None:
        return _dot_env_cache

    cache: Dict[str, str] = {}
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        try:
            for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and value:
                    cache[key] = value
        except Exception:
            cache = {}
    _dot_env_cache = cache
    return cache


def _env_value(name: str, default: str = "") -> str:
    value = str(os.getenv(name, "")).strip()
    if value:
        return value
    fallback = str(_load_local_env().get(name, "")).strip()
    if fallback:
        os.environ.setdefault(name, fallback)
        return fallback
    return default


def _clamp_percent(value: object, default: int = 100) -> int:
    try:
        parsed = int(str(value))
    except Exception:
        parsed = default
    return max(0, min(100, parsed))


def _stable_bucket(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _render_status_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": row.get("id"),
        "project_id": row.get("project_id"),
        "status": row.get("status", "unknown"),
        "progress": row.get("progress", 0),
        "lambda_job_id": row.get("lambda_job_id"),
        "output_url": row.get("output_url"),
        "error": row.get("error"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|(?:\d+[.)]))\s+(.+?)\s*$")
_HTML_RE = re.compile(r"<[^>]+>")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _strip_md_text(text: str) -> str:
    cleaned = _HTML_RE.sub(" ", text or "")
    cleaned = cleaned.replace("`", " ").replace("*", " ").replace("_", " ").replace("#", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _prefer_zh(*texts: object) -> bool:
    for text in texts:
        if _CJK_RE.search(str(text or "")):
            return True
    return False


def _looks_like_garbled_input(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    q = s.count("?")
    if q < 3:
        return False
    ratio = q / max(1, len(s))
    if ratio < 0.15:
        return False
    if _CJK_RE.search(s):
        return False
    return True


def _assert_slides_not_garbled(slides: List[Dict[str, Any]]) -> None:
    suspicious: List[str] = []
    for i, slide in enumerate(slides):
        idx = i + 1
        title = str(slide.get("title") or "")
        if _looks_like_garbled_input(title):
            suspicious.append(f"slide[{idx}].title")
        narration = str(slide.get("narration") or "")
        if _looks_like_garbled_input(narration):
            suspicious.append(f"slide[{idx}].narration")
        for j, el in enumerate(slide.get("elements") or []):
            if not isinstance(el, dict):
                continue
            if str(el.get("type") or "").lower() != "text":
                continue
            content = str(el.get("content") or "")
            if _looks_like_garbled_input(content):
                suspicious.append(f"slide[{idx}].elements[{j}].content")
    if suspicious:
        raise ValueError(
            "Input text appears garbled (too many '?'). Ensure UTF-8 payload encoding."
            f" Fields: {', '.join(suspicious[:8])}"
        )


def _extract_title_and_bullets(markdown: str, fallback_title: str) -> tuple[str, List[str]]:
    title = fallback_title
    bullets: List[str] = []
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
        bullet = _BULLET_RE.match(line)
        if bullet:
            parsed = _strip_md_text(bullet.group(1))
            if parsed:
                bullets.append(parsed)
            continue
        plain = _strip_md_text(line)
        if plain and len(plain) >= 3:
            bullets.append(plain)

    dedup: List[str] = []
    seen = set()
    for item in bullets:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
        if len(dedup) >= 6:
            break
    return title, dedup


def _extract_script_text(slide: Dict[str, Any]) -> str:
    script = slide.get("script")
    if isinstance(script, list):
        lines: List[str] = []
        for item in script:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    lines.append(text)
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    lines.append(text)
        if lines:
            return " ".join(lines).strip()
    narration = str(slide.get("narration") or "").strip()
    if narration:
        return narration
    speaker_notes = str(slide.get("speaker_notes") or "").strip()
    if speaker_notes:
        return speaker_notes
    return ""


def _normalize_slide_for_renderer(slide: Dict[str, Any], index: int) -> Dict[str, Any]:
    # Layout-style slide (already compatible with SlidePresentation)
    if isinstance(slide.get("elements"), list):
        out = dict(slide)
        out.setdefault("id", f"slide-{index + 1}")
        out.setdefault("order", index)
        out.setdefault("title", f"Slide {index + 1}")
        out.setdefault("duration", max(3, int(float(slide.get("duration") or 6))))
        out.setdefault("background", {"type": "solid", "color": "#f8fafc"})
        if "narrationAudioUrl" not in out and slide.get("narration_audio_url"):
            out["narrationAudioUrl"] = slide.get("narration_audio_url")
        if "narration" not in out:
            out["narration"] = _extract_script_text(slide)
        return out

    # Semantic slide (markdown/script/actions): convert into layout text block.
    markdown = str(slide.get("markdown") or "")
    fallback_title = f"Slide {index + 1}"
    title, bullets = _extract_title_and_bullets(markdown, fallback_title)
    if not bullets:
        stripped = _strip_md_text(markdown)
        bullets = [stripped] if stripped else ["Content unavailable"]
    lines_html = "<br/>".join(f"&bull; {html.escape(item)}" for item in bullets[:6])

    narration = _extract_script_text(slide)
    return {
        "id": str(slide.get("id") or f"slide-{index + 1}"),
        "order": index,
        "title": title,
        "elements": [
            {
                "id": f"content-{index + 1}",
                "type": "text",
                "left": 96,
                "top": 210,
                "width": 1728,
                "height": 760,
                "content": lines_html,
                "style": {
                    "fontSize": 52,
                    "lineHeight": 1.35,
                    "color": "#1e293b",
                },
            }
        ],
        "background": {"type": "solid", "color": "#f8fafc"},
        "narration": narration,
        "narrationAudioUrl": slide.get("narration_audio_url") or slide.get("narrationAudioUrl"),
        "duration": max(3, int(float(slide.get("duration") or 6))),
    }


def _is_image_slide(slide: Dict[str, Any]) -> bool:
    if not isinstance(slide, dict):
        return False
    image_url = str(slide.get("imageUrl") or slide.get("image_url") or "").strip()
    return bool(image_url)


def _normalize_image_slide_for_renderer(slide: Dict[str, Any]) -> Dict[str, Any]:
    image_url = str(slide.get("imageUrl") or slide.get("image_url") or "").strip()
    if not image_url:
        raise ValueError("image slide missing imageUrl")
    audio_url = str(slide.get("audioUrl") or slide.get("audio_url") or "").strip()
    duration = max(3.0, float(slide.get("duration") or 6.0))
    out: Dict[str, Any] = {"imageUrl": image_url, "duration": duration}
    if audio_url:
        out["audioUrl"] = audio_url
    return out


def _build_image_video_slides(
    image_urls: List[str],
    slides: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, url in enumerate(image_urls):
        src = slides[idx] if idx < len(slides) else {}
        audio_url = str(src.get("narration_audio_url") or src.get("narrationAudioUrl") or "").strip()
        duration = max(3.0, float(src.get("duration") or 6.0))
        safe_image_url = _presign_r2_get_url_if_needed(url)
        safe_audio_url = _presign_r2_get_url_if_needed(audio_url) if audio_url else ""
        item: Dict[str, Any] = {
            "imageUrl": safe_image_url,
            "duration": duration,
        }
        if safe_audio_url:
            item["audioUrl"] = safe_audio_url
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
    host_allowed = False
    if configured_hosts:
        host_allowed = host in configured_hosts
    else:
        host_allowed = (
            host.endswith(".r2.dev")
            or host.endswith(".autoviralvid.com")
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


def _layout_to_slide_type(layout: str) -> str:
    if layout == "cover":
        return "cover"
    if layout == "summary":
        return "summary"
    return "content"


def _collect_stage_diagnostics(prefix: str, messages: List[str], limit: int = 10) -> List[str]:
    out: List[str] = []
    for msg in messages[: max(0, limit)]:
        text = str(msg or "").strip()
        if not text:
            continue
        out.append(f"{prefix}: {text}")
    return out


def _extract_plan_slide_title(slide: Dict[str, Any], fallback: str) -> str:
    blocks = slide.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if str(block.get("block_type") or "").strip().lower() != "title":
                continue
            text = str(block.get("content") or "").strip()
            if text:
                return text[:200]
    title = str(slide.get("title") or "").strip()
    if title:
        return title[:200]
    return fallback


def _infer_semantic_page_type(layout_grid: str, blocks: List[Dict[str, Any]]) -> str:
    layout = str(layout_grid or "").strip().lower()
    types = {_as_block_type(block) for block in blocks if isinstance(block, dict)}
    if layout == "timeline" or "timeline" in types:
        return "timeline"
    if "table" in types:
        return "table"
    if any(t in {"chart", "kpi"} for t in types):
        return "data"
    if layout in {"split_2", "asymmetric_2", "grid_2"}:
        return "comparison"
    return "content"


_LAYOUT_CARD_SLOTS: Dict[str, List[str]] = {
    "hero_1": ["main"],
    "split_2": ["left", "right"],
    "asymmetric_2": ["major", "minor"],
    "grid_3": ["c1", "c2", "c3"],
    "grid_4": ["tl", "tr", "bl", "br"],
    "bento_5": ["hero", "s1", "s2", "s3", "s4"],
    "bento_6": ["h1", "h2", "s1", "s2", "s3", "s4"],
    "timeline": ["t1", "t2", "t3", "t4", "t5"],
}


def _preferred_slots(layout: str, position: str, block_type: str) -> List[str]:
    layout_key = str(layout or "").strip().lower()
    position_key = str(position or "").strip().lower()
    block_type_key = str(block_type or "").strip().lower()
    if layout_key == "hero_1":
        return ["main"]

    lookup: Dict[str, List[str]] = {
        "top": ["tl", "tr", "h1", "h2", "left", "major", "c1", "c2", "s1", "s2", "t1", "t2"],
        "left": ["left", "major", "c1", "tl", "bl", "h1", "s1", "t1", "t2"],
        "right": ["right", "minor", "c3", "tr", "br", "h2", "s3", "t4", "t5"],
        "center": ["main", "hero", "c2", "h1", "h2", "s2", "t3"],
        "bottom": ["bl", "br", "s3", "s4", "t4", "t5"],
        "top_left": ["tl", "left", "major", "h1", "s1", "t1"],
        "top_right": ["tr", "right", "minor", "h2", "s2", "t2"],
        "bottom_left": ["bl", "left", "major", "s3", "t4"],
        "bottom_right": ["br", "right", "minor", "s4", "t5"],
    }
    if block_type_key == "title":
        return ["main", "hero", "left", "major", "c1", "tl", "h1", "t1"]
    return lookup.get(position_key, [])


def _assign_layout_card_ids(layout_grid: str, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    slots = list(_LAYOUT_CARD_SLOTS.get(str(layout_grid or "").strip().lower(), []))
    used: set[str] = set()
    normalized: List[Dict[str, Any]] = []

    for block in blocks:
        out = dict(block)
        card_id = str(out.get("card_id") or "").strip()
        generic_fallback = bool(re.fullmatch(r"card-\d+", card_id))
        if card_id and not generic_fallback and card_id not in used:
            used.add(card_id)
            normalized.append(out)
            continue
        out["card_id"] = ""
        normalized.append(out)

    for idx, block in enumerate(normalized):
        existing = str(block.get("card_id") or "").strip()
        if existing:
            continue
        position = str(block.get("position") or "").strip().lower()
        btype = str(block.get("block_type") or block.get("type") or "").strip().lower()
        if btype == "title":
            chosen = "title"
            if chosen in used:
                chosen = f"title_{idx + 1}"
            block["card_id"] = chosen
            used.add(chosen)
            continue
        preferred = _preferred_slots(layout_grid, position, btype)

        chosen = ""
        for candidate in preferred:
            if candidate in slots and candidate not in used:
                chosen = candidate
                break
        if not chosen:
            for candidate in slots:
                if candidate not in used:
                    chosen = candidate
                    break
        if not chosen:
            chosen = f"card-{idx + 1}"
        block["card_id"] = chosen
        used.add(chosen)

    return normalized


def _presentation_plan_to_render_payload(plan: PresentationPlan) -> Dict[str, Any]:
    slides: List[Dict[str, Any]] = []
    for idx, slide in enumerate(plan.slides):
        raw = slide.model_dump()
        title = _extract_plan_slide_title(raw, fallback=f"Slide {idx + 1}")
        raw_slide_type = str(raw.get("slide_type") or "content").strip().lower()
        layout_grid = str(raw.get("layout_grid") or "split_2")
        normalized_slide_type = (
            raw_slide_type
            if raw_slide_type in {"cover", "summary", "toc", "divider", "content"}
            else "content"
        )
        blocks = raw.get("blocks") if isinstance(raw.get("blocks"), list) else []
        normalized_blocks: List[Dict[str, Any]] = []
        for block_idx, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            normalized = dict(block)
            normalized.setdefault("card_id", f"card-{block_idx + 1}")
            normalized_blocks.append(normalized)
        normalized_blocks = _assign_layout_card_ids(layout_grid, normalized_blocks)
        semantic_page_type = (
            normalized_slide_type
            if normalized_slide_type in {"cover", "summary", "toc", "divider"}
            else _infer_semantic_page_type(layout_grid, normalized_blocks)
        )

        slides.append(
            {
                "id": f"slide-{idx + 1}",
                "page_number": int(raw.get("page_number") or (idx + 1)),
                "slide_type": normalized_slide_type,
                "page_type": semantic_page_type,
                "subtype": semantic_page_type,
                "layout_grid": layout_grid,
                "bg_style": str(raw.get("bg_style") or "light"),
                "image_keywords": raw.get("image_keywords") or [],
                "title": title,
                "narration": str(raw.get("notes_for_designer") or ""),
                "blocks": normalized_blocks,
            }
        )

    return {
        "title": plan.title,
        "theme": {"palette": plan.theme, "style": plan.style},
        "slides": slides,
    }


def _pipeline_artifact_dir(run_id: str) -> Path:
    return Path(__file__).resolve().parents[1] / "renders" / "tmp" / "ppt_pipeline" / run_id


def _write_pipeline_artifact(run_id: str, name: str, payload: Dict[str, Any]) -> None:
    def _json_default(value: Any) -> Any:
        if isinstance(value, (bytes, bytearray)):
            return {"__type__": "bytes", "length": len(value)}
        return str(value)

    out_dir = _pipeline_artifact_dir(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.json"
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


_LAYOUT_CARD_COUNTS = {
    "hero_1": 1,
    "split_2": 2,
    "asymmetric_2": 2,
    "grid_3": 3,
    "grid_4": 4,
    "bento_5": 5,
    "bento_6": 6,
    "timeline": 5,
}


def _brand_placeholder_svg_data_uri(title: str = "Brand Visual Placeholder") -> str:
    safe = html.escape(str(title or "Brand Visual Placeholder"), quote=True)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        '<rect width="1200" height="675" rx="28" fill="#0D1630" stroke="#1E335E" stroke-width="3"/>'
        '<rect x="56" y="54" width="8" height="34" rx="4" fill="#2F7BFF"/>'
        f'<text x="80" y="80" fill="#E8F0FF" font-size="36" font-family="Segoe UI, Arial" font-weight="700">{safe}</text>'
        '<text x="80" y="125" fill="#95A8CC" font-size="24" font-family="Segoe UI, Arial">brand visual placeholder</text>'
        '<rect x="80" y="170" width="1040" height="440" rx="22" fill="#121F3D" stroke="#1E335E" stroke-width="2" stroke-dasharray="10 8"/>'
        "</svg>"
    )
    return f"data:image/svg+xml;utf8,{url_quote(svg)}"


def _resolve_template_family(slide: Dict[str, Any]) -> str:
    st = str(
        slide.get("page_type")
        or slide.get("slide_type")
        or slide.get("subtype")
        or "content"
    ).strip().lower()
    layout = str(slide.get("layout_grid") or slide.get("layout") or "split_2").strip().lower()
    return resolve_template_for_slide(
        slide=slide if isinstance(slide, dict) else {},
        slide_type=st,
        layout_grid=layout,
        requested_template=str(slide.get("template_family") or slide.get("template_id") or ""),
        desired_density=str(slide.get("content_density") or "balanced"),
    )


def _template_profiles(template_family: str) -> Dict[str, str]:
    return shared_template_profiles(template_family)


def _as_block_type(block: Dict[str, Any]) -> str:
    return str(block.get("block_type") or block.get("type") or "").strip().lower()


_SPLIT_TEXT_RE = re.compile(r"[;；,\n，。.!?]+")
_TEXTUAL_BLOCK_TYPES = {
    "title",
    "subtitle",
    "text",
    "body",
    "list",
    "quote",
    "icon_text",
    "comparison",
}
_VISUAL_BLOCK_TYPES = {"image", "chart", "kpi", "table"}


def _normalize_text_key(text: str) -> str:
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%+.-]", "", lowered)


def _extract_block_text(block: Dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        parts: List[str] = []
        for key in ("title", "body", "text", "label", "caption", "description"):
            value = str(content.get(key) or "").strip()
            if value:
                parts.append(value)
        if parts:
            return " ".join(parts).strip()
    data = block.get("data")
    if isinstance(data, dict):
        parts = []
        for key in ("title", "label", "description"):
            value = str(data.get(key) or "").strip()
            if value:
                parts.append(value)
        if parts:
            return " ".join(parts).strip()
    return ""


def _extract_slide_keypoints(slide: Dict[str, Any], title_text: str) -> List[str]:
    tokens: List[str] = [title_text, str(slide.get("narration") or "").strip()]
    image_keywords = slide.get("image_keywords")
    if isinstance(image_keywords, list):
        tokens.extend(str(item or "").strip() for item in image_keywords)
    for block in slide.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        tokens.append(_extract_block_text(block))

    phrases: List[str] = []
    seen = set()
    for token in tokens:
        for part in _SPLIT_TEXT_RE.split(str(token or "")):
            phrase = str(part or "").strip()
            if len(phrase) < 4:
                continue
            key = _normalize_text_key(phrase)
            if not key or key in seen:
                continue
            seen.add(key)
            phrases.append(phrase)
            if len(phrases) >= 8:
                return phrases
    return phrases


def _extract_numeric_values(text: str) -> List[float]:
    values: List[float] = []
    for match in re.finditer(r"-?\d+(?:\.\d+)?", str(text or "")):
        try:
            values.append(float(match.group(0)))
        except Exception:
            continue
    return values


def _dedupe_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for block in blocks:
        btype = _as_block_type(block) or "text"
        text = _extract_block_text(block)
        text_key = _normalize_text_key(text)
        signature = (
            f"text:{text_key}"
            if btype in _TEXTUAL_BLOCK_TYPES and text_key
            else f"{btype}:{text_key}"
        )
        if signature in seen and signature != f"{btype}:":
            continue
        seen.add(signature)
        out.append(block)
    return out


def _auto_emphasis(block: Dict[str, Any], fallback_keywords: List[str]) -> List[str]:
    current = block.get("emphasis")
    if isinstance(current, list):
        valid = [str(item).strip() for item in current if str(item).strip()]
        if valid:
            return valid[:4]
    text = _extract_block_text(block)
    emphasis: List[str] = []
    numbers = re.findall(r"\d+(?:\.\d+)?%?", text)
    emphasis.extend(numbers[:2])
    for kw in fallback_keywords:
        if kw and kw not in emphasis:
            emphasis.append(kw)
        if len(emphasis) >= 3:
            break
    return emphasis[:3]


def _trim_blocks_to_layout_capacity(layout: str, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep blocks within layout capacity while preserving semantic diversity."""
    layout_key = str(layout or "").strip().lower()
    card_capacity = _LAYOUT_CARD_COUNTS.get(layout_key, 0)
    if card_capacity <= 0:
        return blocks

    title_blocks = [b for b in blocks if _as_block_type(b) == "title"]
    non_title_blocks = [b for b in blocks if _as_block_type(b) != "title"]
    if len(non_title_blocks) <= card_capacity:
        return ([title_blocks[0]] if title_blocks else []) + non_title_blocks

    def _same_text(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        return _normalize_text_key(_extract_block_text(a)) == _normalize_text_key(
            _extract_block_text(b)
        )

    selected: List[Dict[str, Any]] = []

    first_text = next(
        (
            block
            for block in non_title_blocks
            if _as_block_type(block) in _TEXTUAL_BLOCK_TYPES
        ),
        None,
    )
    if first_text is not None:
        selected.append(first_text)

    first_visual = next(
        (
            block
            for block in non_title_blocks
            if _as_block_type(block) in _VISUAL_BLOCK_TYPES
            and all(block is not cur for cur in selected)
            and all(not _same_text(block, cur) for cur in selected)
        ),
        None,
    )
    if first_visual is not None and len(selected) < card_capacity:
        selected.append(first_visual)

    for block in non_title_blocks:
        if len(selected) >= card_capacity:
            break
        if any(block is cur for cur in selected):
            continue
        if any(_same_text(block, cur) for cur in selected):
            continue
        selected.append(block)

    trimmed = ([title_blocks[0]] if title_blocks else []) + selected[:card_capacity]
    return trimmed


def _ensure_content_contract(slide: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(slide)
    slide_type = str(out.get("slide_type") or "").strip().lower()
    terminal_slide = slide_type in {"cover", "summary", "toc", "divider", "hero_1"}

    blocks = out.get("blocks")
    if not isinstance(blocks, list):
        blocks = []
    fixed: List[Dict[str, Any]] = [dict(b) for b in blocks if isinstance(b, dict)]
    fixed = _dedupe_blocks(fixed)

    title_text = str(out.get("title") or "Core Insight").strip() or "Core Insight"
    prefer_zh = _prefer_zh(title_text, out.get("narration"), *(out.get("image_keywords") or []))
    keypoints = _extract_slide_keypoints(out, title_text)

    if not terminal_slide:
        has_title = any(_as_block_type(block) == "title" for block in fixed)
        has_body_or_list = any(_as_block_type(block) in {"body", "list"} for block in fixed)
        has_anchor = any(_as_block_type(block) in {"image", "chart", "kpi"} for block in fixed)

        if not has_title:
            fixed.insert(
                0,
                {
                    "block_type": "title",
                    "card_id": "title",
                    "position": "top",
                    "content": title_text,
                    "emphasis": [],
                },
            )

        if not has_body_or_list:
            fallback_points = keypoints[:3]
            if len(fallback_points) < 3:
                fallback_points.extend(
                    [
                        "核心结论" if prefer_zh else "Core insight",
                        "关键论据" if prefer_zh else "Key evidence",
                        "落地动作" if prefer_zh else "Execution action",
                    ][: 3 - len(fallback_points)]
                )
            fixed.append(
                {
                    "block_type": "list",
                    "card_id": "list_main",
                    "position": "left",
                    "content": ";".join(fallback_points[:3]),
                    "emphasis": fallback_points[:2],
                }
            )

        if not has_anchor:
            numeric_source = " ".join([title_text, str(out.get("narration") or "")] + keypoints)
            nums = _extract_numeric_values(numeric_source)
            if nums:
                first = nums[0]
                trend = nums[1] - first if len(nums) >= 2 else (8.0 if first >= 0 else -8.0)
                anchor_label = next(
                    (
                        point
                        for point in keypoints
                        if _normalize_text_key(point) != _normalize_text_key(title_text)
                    ),
                    title_text,
                )
                fixed.append(
                    {
                        "block_type": "kpi",
                        "card_id": "kpi_anchor",
                        "position": "right",
                        "data": {
                            "number": round(first, 2),
                            "unit": "%",
                            "trend": round(trend, 2),
                            "label": anchor_label,
                        },
                        "content": anchor_label,
                        "emphasis": [str(round(first, 2))],
                    }
                )

        layout = str(out.get("layout_grid") or out.get("layout") or "").strip().lower()
        card_count = _LAYOUT_CARD_COUNTS.get(layout, max(2, len(fixed)))
        min_non_title_blocks = max(2, int((card_count * 0.55) + 0.999))
        non_title_count = len([b for b in fixed if _as_block_type(b) != "title"])
        filler_idx = 0
        while non_title_count < min_non_title_blocks:
            item = keypoints[filler_idx % len(keypoints)] if keypoints else (
                f"补充要点 {filler_idx + 1}" if prefer_zh else f"Supporting point {filler_idx + 1}"
            )
            fixed.append(
                {
                    "block_type": "body",
                    "card_id": f"body_fill_{filler_idx + 1}",
                    "position": "center",
                    "content": item,
                    "emphasis": [item[:14]],
                }
            )
            non_title_count += 1
            filler_idx += 1

    fixed = _dedupe_blocks(fixed)
    fixed = _trim_blocks_to_layout_capacity(
        str(out.get("layout_grid") or out.get("layout") or "").strip().lower(),
        fixed,
    )
    fixed = _assign_layout_card_ids(
        str(out.get("layout_grid") or out.get("layout") or "").strip().lower(),
        fixed,
    )
    for idx, block in enumerate(fixed):
        block["block_type"] = _as_block_type(block) or "text"
        if not str(block.get("card_id") or "").strip():
            block["card_id"] = f"card-{idx + 1}"
        if block["block_type"] != "title":
            block["emphasis"] = _auto_emphasis(block, keypoints)

    out["blocks"] = fixed
    out["template_family"] = _resolve_template_family(out)
    out.update(_template_profiles(out["template_family"]))
    out["bg_style"] = (
        "light"
        if out["template_family"] in {"neural_blueprint_light", "ops_lifecycle_light", "consulting_warm_light"}
        else "dark"
    )
    out["svg_mode"] = "on"
    out["enforce_visual_contract"] = True
    return out


def _apply_visual_orchestration(render_payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(render_payload or {})
    slides = out.get("slides")
    if not isinstance(slides, list):
        return out
    out["slides"] = [_ensure_content_contract(slide if isinstance(slide, dict) else {}) for slide in slides]
    out["svg_mode"] = "on"
    out["enforce_visual_contract"] = True
    if not str(out.get("template_family") or "").strip():
        out["template_family"] = "auto"
    deck_template = str(out.get("template_family") or "dashboard_dark").strip().lower()
    if deck_template == "auto":
        first = out["slides"][0] if out["slides"] else {}
        deck_template = str(first.get("template_family") or "dashboard_dark").strip().lower()
    resolved_profiles = _template_profiles(deck_template)
    for key, value in resolved_profiles.items():
        existing = str(out.get(key) or "").strip()
        if existing and existing.lower() != "auto":
            out[key] = existing
        else:
            out[key] = value
    theme = out.get("theme")
    if isinstance(theme, dict):
        if not str(theme.get("style") or "").strip() or str(theme.get("style")).strip().lower() == "auto":
            theme["style"] = "pill"
        out["theme"] = theme
    return out


_SCHEMA_SLIDE_RE = re.compile(r"slides\[(\d+)\]", flags=re.IGNORECASE)


def _extract_slide_targets_from_schema_error(detail: str, slides: List[Dict[str, Any]]) -> List[str]:
    indexes = sorted({int(m.group(1)) for m in _SCHEMA_SLIDE_RE.finditer(str(detail or ""))})
    targets: List[str] = []
    for idx in indexes:
        if idx < 0 or idx >= len(slides):
            continue
        slide = slides[idx] if isinstance(slides[idx], dict) else {}
        candidate = str(slide.get("slide_id") or slide.get("id") or f"slide-{idx + 1}").strip()
        if candidate and candidate not in targets:
            targets.append(candidate)
    return targets


def _search_serper_sync(
    *,
    query: str,
    api_key: str,
    num: int = 5,
    gl: str = "us",
    hl: str = "zh-cn",
) -> List[Dict[str, str]]:
    base_url = str(_env_value("SERPER_API_URL", "https://google.serper.dev/search")).strip()
    payload = json.dumps(
        {
            "q": query,
            "num": max(1, min(10, int(num))),
            "gl": gl,
            "hl": hl,
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        base_url,
        data=payload,
        method="POST",
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=12) as resp:  # nosec B310
            raw = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, json.JSONDecodeError):
        return []

    organic = parsed.get("organic") if isinstance(parsed, dict) else []
    if not isinstance(organic, list):
        return []

    items: List[Dict[str, str]] = []
    for row in organic:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        url = str(row.get("link") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        if not title or not url:
            continue
        items.append({"title": title, "url": url, "snippet": snippet})
        if len(items) >= max(3, min(10, int(num))):
            break
    return items


async def _search_serper_web(
    *,
    query: str,
    api_key: str,
    num: int = 5,
    gl: str = "us",
    hl: str = "zh-cn",
) -> List[Dict[str, str]]:
    import asyncio

    return await asyncio.to_thread(
        _search_serper_sync,
        query=query,
        api_key=api_key,
        num=num,
        gl=gl,
        hl=hl,
    )


_GENERIC_AUDIENCE = {"general", "all", "public", "everyone", "大众", "通用", "全部人群"}
_GENERIC_PURPOSE = {"presentation", "general", "汇报", "演示", "展示"}
_GENERIC_STYLE = {"professional", "default", "normal", "商务", "专业", "常规"}


def _is_generic_slot(value: str, generic: set[str]) -> bool:
    text = str(value or "").strip().lower()
    return not text or text in generic


def _dedup_strings(items: List[str], *, limit: int) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _build_research_gaps(req: ResearchRequest, *, is_zh: bool) -> List[ResearchGap]:
    gaps: List[ResearchGap] = []
    if _is_generic_slot(req.audience, _GENERIC_AUDIENCE):
        gaps.append(
            ResearchGap(
                code="audience",
                severity="high",
                message="受众描述过于泛化，缺少明确角色与决策层级。"
                if is_zh
                else "Audience definition is too generic; role and decision level are missing.",
                query_hint=f"{req.topic} 目标受众 分层" if is_zh else f"{req.topic} target audience segmentation",
            )
        )
    if _is_generic_slot(req.purpose, _GENERIC_PURPOSE):
        gaps.append(
            ResearchGap(
                code="purpose",
                severity="medium",
                message="演示目标不够明确，难以确定叙事重点。"
                if is_zh
                else "Presentation objective is not specific enough for clear narrative focus.",
                query_hint=f"{req.topic} 商业目标 KPI" if is_zh else f"{req.topic} business objective KPI",
            )
        )
    if _is_generic_slot(req.style_preference, _GENERIC_STYLE):
        gaps.append(
            ResearchGap(
                code="style",
                severity="low",
                message="视觉风格偏好不明确，建议补充调性或品牌约束。"
                if is_zh
                else "Visual style preference is vague; add tone or brand constraints.",
                query_hint=f"{req.topic} 品牌视觉 风格" if is_zh else f"{req.topic} brand visual style",
            )
        )
    if not req.required_facts:
        gaps.append(
            ResearchGap(
                code="required_facts",
                severity="high",
                message="缺少必须展示的数据点，图表选型依据不足。"
                if is_zh
                else "Missing must-have facts, limiting chart and evidence selection.",
                query_hint=f"{req.topic} 核心指标 数据" if is_zh else f"{req.topic} core metrics data",
            )
        )
    if not str(req.time_range or "").strip():
        gaps.append(
            ResearchGap(
                code="time_range",
                severity="medium",
                message="缺少时间范围，趋势数据无法限定口径。"
                if is_zh
                else "Time range is missing, making trend framing ambiguous.",
                query_hint=f"{req.topic} 近3年 趋势" if is_zh else f"{req.topic} last 3 years trend",
            )
        )
    if not str(req.geography or "").strip():
        gaps.append(
            ResearchGap(
                code="geography",
                severity="low",
                message="缺少地域范围，市场数据可能口径不一致。"
                if is_zh
                else "Geographic scope is missing; market figures may be inconsistent.",
                query_hint=f"{req.topic} 中国 市场" if is_zh else f"{req.topic} regional market",
            )
        )
    return gaps


def _build_research_queries(
    req: ResearchRequest,
    *,
    is_zh: bool,
    gaps: List[ResearchGap],
) -> List[str]:
    extras = " ".join(
        part
        for part in [
            str(req.time_range or "").strip(),
            str(req.geography or "").strip(),
            " ".join(req.domain_terms[:2]),
        ]
        if part
    ).strip()

    queries: List[str] = []
    if req.required_facts:
        for fact in req.required_facts:
            q = " ".join(part for part in [req.topic, fact, extras] if part).strip()
            if q:
                queries.append(q)
    for gap in gaps:
        if gap.query_hint:
            q = " ".join(part for part in [req.topic, gap.query_hint, extras] if part).strip()
            queries.append(q)

    if not queries:
        default_queries = (
            [
                f"{req.topic} 市场规模 增长",
                f"{req.topic} 行业报告 数据",
                f"{req.topic} 最新统计 指标",
            ]
            if is_zh
            else [
                f"{req.topic} market size trend",
                f"{req.topic} benchmark report data",
                f"{req.topic} latest statistics metrics",
            ]
        )
        queries.extend(default_queries)

    return _dedup_strings(queries, limit=max(1, req.max_web_queries))


def _score_evidence_confidence(url: str, snippet: str) -> float:
    host = str(urlparse(url).netloc or "").lower()
    score = 0.58
    if host.endswith(".gov") or host.endswith(".edu"):
        score = 0.84
    elif any(token in host for token in ("research", "report", "data", "stat")):
        score = 0.74
    if len(str(snippet or "").strip()) >= 120:
        score += 0.08
    elif len(str(snippet or "").strip()) >= 60:
        score += 0.04
    return max(0.35, min(0.93, round(score, 2)))


def _score_research_completeness(
    req: ResearchRequest,
    *,
    key_data_points: int,
    references: int,
    evidence_count: int,
    gaps: List[ResearchGap],
) -> float:
    score = 0.28  # topic is required
    score += 0.12 if not _is_generic_slot(req.audience, _GENERIC_AUDIENCE) else 0.04
    score += 0.10 if not _is_generic_slot(req.purpose, _GENERIC_PURPOSE) else 0.03
    score += 0.05 if not _is_generic_slot(req.style_preference, _GENERIC_STYLE) else 0.02
    score += 0.12 if req.required_facts else 0.03
    if str(req.time_range or "").strip():
        score += 0.06
    if str(req.geography or "").strip():
        score += 0.04
    if req.constraints:
        score += 0.05
    score += min(0.10, (key_data_points / 8.0) * 0.10)
    score += min(0.08, (references / max(1, req.desired_citations)) * 0.08)
    score += min(0.05, (evidence_count / 6.0) * 0.05)

    high_gaps = sum(1 for gap in gaps if gap.severity == "high")
    medium_gaps = sum(1 for gap in gaps if gap.severity == "medium")
    score -= min(0.09, high_gaps * 0.03 + medium_gaps * 0.015)
    return max(0.0, min(1.0, round(score, 3)))


def _search_serper_images_sync(
    *,
    query: str,
    api_key: str,
    num: int = 5,
    gl: str = "us",
    hl: str = "zh-cn",
) -> List[Dict[str, str]]:
    base_url = str(_env_value("SERPER_IMAGE_API_URL", "https://google.serper.dev/images")).strip()
    payload = json.dumps(
        {
            "q": query,
            "num": max(1, min(10, int(num))),
            "gl": gl,
            "hl": hl,
        }
    ).encode("utf-8")
    req = urllib_request.Request(
        base_url,
        data=payload,
        method="POST",
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=12) as resp:  # nosec B310
            raw = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(raw)
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, json.JSONDecodeError):
        return []

    rows = parsed.get("images") if isinstance(parsed, dict) else []
    if not isinstance(rows, list):
        return []

    out: List[Dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        image_url = str(row.get("imageUrl") or row.get("url") or "").strip()
        title = str(row.get("title") or "").strip()
        source = str(row.get("source") or row.get("link") or "").strip()
        if not image_url.startswith(("http://", "https://")):
            continue
        out.append(
            {
                "title": title,
                "url": image_url,
                "source": source,
            }
        )
        if len(out) >= max(3, min(10, int(num))):
            break
    return out


async def _search_serper_images(
    *,
    query: str,
    api_key: str,
    num: int = 5,
    gl: str = "us",
    hl: str = "zh-cn",
) -> List[Dict[str, str]]:
    import asyncio

    return await asyncio.to_thread(
        _search_serper_images_sync,
        query=query,
        api_key=api_key,
        num=num,
        gl=gl,
        hl=hl,
    )


def _fetch_image_data_uri_sync(url: str, max_bytes: int = 3_000_000) -> str:
    raw_url = str(url or "").strip()
    if not raw_url.startswith(("http://", "https://")):
        return ""

    req = urllib_request.Request(
        raw_url,
        method="GET",
        headers={
            "User-Agent": "Mozilla/5.0 (PPTAssetBot/1.0)",
            "Accept": "image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=12) as resp:  # nosec B310
            content_type = str(resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            payload = resp.read(max_bytes + 1)
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError):
        return ""

    if not payload or len(payload) > max_bytes:
        return ""
    if not content_type.startswith("image/"):
        guessed = mimetypes.guess_type(raw_url)[0] or ""
        content_type = guessed.lower()
    if not content_type.startswith("image/"):
        return ""

    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


async def _fetch_image_data_uri(url: str, max_bytes: int = 3_000_000) -> str:
    import asyncio

    return await asyncio.to_thread(_fetch_image_data_uri_sync, url, max_bytes)


def _is_placeholder_image_url(url: str) -> bool:
    s = str(url or "").strip().lower()
    if not s:
        return True
    return "brand%20visual%20placeholder" in s or "brand visual placeholder" in s


_DEFAULT_STOCK_IMAGE_DOMAIN_HINTS = (
    "unsplash.com",
    "images.unsplash.com",
    "pexels.com",
    "images.pexels.com",
    "pixabay.com",
    "cdn.pixabay.com",
    "freepik.com",
    "i.ibb.co",
)


def _stock_image_domain_hints() -> List[str]:
    hints = {h.lower() for h in _DEFAULT_STOCK_IMAGE_DOMAIN_HINTS}
    extra = str(_env_value("PPT_STOCK_IMAGE_DOMAINS", "")).strip()
    if extra:
        hints.update(part.strip().lower() for part in extra.split(",") if part.strip())
    return sorted(hints)


def _is_stock_image_candidate(item: Dict[str, str], stock_domain_hints: List[str]) -> bool:
    if not isinstance(item, dict):
        return False
    url_candidates = [
        str(item.get("url") or "").strip().lower(),
        str(item.get("source") or "").strip().lower(),
    ]
    title = str(item.get("title") or "").strip().lower()
    hosts = []
    for candidate in url_candidates:
        if not candidate:
            continue
        try:
            parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
        except ValueError:
            continue
        host = str(parsed.netloc or "").strip().lower()
        if host:
            hosts.append(host)
    for host in hosts:
        if any(hint in host for hint in stock_domain_hints):
            return True
    blob = " ".join([*url_candidates, title])
    return any(hint in blob for hint in stock_domain_hints)


def _dedupe_image_candidates(candidates: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def _extract_image_keywords(slide: Dict[str, Any], block: Dict[str, Any], deck_title: str) -> List[str]:
    out: List[str] = []
    data = block.get("data")
    if isinstance(data, dict):
        kws = data.get("keywords")
        if isinstance(kws, list):
            out.extend(str(item or "").strip() for item in kws)
    image_keywords = slide.get("image_keywords")
    if isinstance(image_keywords, list):
        out.extend(str(item or "").strip() for item in image_keywords)
    out.extend(
        [
            str(deck_title or "").strip(),
            str(slide.get("title") or "").strip(),
            str(block.get("content") or "").strip(),
        ]
    )

    dedup: List[str] = []
    seen = set()
    for item in out:
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
        if len(dedup) >= 6:
            break
    return dedup


async def _hydrate_image_assets(render_payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(render_payload or {})
    slides = out.get("slides")
    if not isinstance(slides, list) or not slides:
        return out

    enabled = str(os.getenv("PPT_IMAGE_ASSET_ENABLED", "true")).strip().lower() not in {"0", "false", "no", "off"}
    serper_api_key = str(_env_value("SERPER_API_KEY", "")).strip()
    if not enabled or not serper_api_key:
        return out

    image_search_cache: Dict[str, List[Dict[str, str]]] = {}
    data_uri_cache: Dict[str, str] = {}
    deck_title = str(out.get("title") or "").strip()
    hl = "zh-cn" if _prefer_zh(deck_title) else "en"
    stock_domain_hints = _stock_image_domain_hints()
    stock_search_domains = [
        part.strip().lower()
        for part in str(_env_value("PPT_STOCK_SEARCH_DOMAINS", "unsplash.com,pexels.com,pixabay.com")).split(",")
        if part.strip()
    ]
    fallback_stock_terms = (
        ["科技 抽象 背景", "商业 数据 可视化", "蓝色 科技 质感"]
        if hl == "zh-cn"
        else ["technology abstract background", "business analytics dashboard", "ai workflow illustration"]
    )

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        blocks = slide.get("blocks")
        if not isinstance(blocks, list):
            continue

        for block in blocks:
            if not isinstance(block, dict):
                continue
            if str(block.get("block_type") or block.get("type") or "").strip().lower() != "image":
                continue

            content = block.get("content")
            if isinstance(content, dict):
                content_obj = dict(content)
            else:
                content_obj = {"title": str(content or slide.get("title") or deck_title or "Visual")}
            data = block.get("data")
            data_obj = dict(data) if isinstance(data, dict) else {}

            existing_url = ""
            for key in ("url", "src", "imageUrl", "image_url"):
                existing_url = str(content_obj.get(key) or data_obj.get(key) or block.get(key) or "").strip()
                if existing_url:
                    break
            if existing_url and not _is_placeholder_image_url(existing_url):
                if existing_url.startswith("http://") or existing_url.startswith("https://"):
                    if existing_url not in data_uri_cache:
                        data_uri_cache[existing_url] = await _fetch_image_data_uri(existing_url)
                    if data_uri_cache[existing_url]:
                        content_obj["url"] = data_uri_cache[existing_url]
                        data_obj["source_url"] = existing_url
                block["content"] = content_obj
                if data_obj:
                    block["data"] = data_obj
                continue

            keywords = _extract_image_keywords(slide, block, deck_title)
            selected_url = ""
            selected_source = ""
            for keyword in keywords:
                if keyword not in image_search_cache:
                    stock_candidates: List[Dict[str, str]] = []
                    for domain in stock_search_domains:
                        site_query = f"{keyword} site:{domain}"
                        site_candidates = await _search_serper_images(
                            query=site_query,
                            api_key=serper_api_key,
                            num=4,
                            hl=hl,
                        )
                        stock_candidates.extend(site_candidates)
                        if len(stock_candidates) >= 10:
                            break
                    if not stock_candidates:
                        for seed in fallback_stock_terms:
                            for domain in stock_search_domains:
                                site_query = f"{seed} site:{domain}"
                                site_candidates = await _search_serper_images(
                                    query=site_query,
                                    api_key=serper_api_key,
                                    num=4,
                                    hl=hl,
                                )
                                stock_candidates.extend(site_candidates)
                                if len(stock_candidates) >= 10:
                                    break
                            if len(stock_candidates) >= 10:
                                break

                    generic_candidates = await _search_serper_images(
                        query=keyword,
                        api_key=serper_api_key,
                        num=6,
                        hl=hl,
                    )
                    stock_candidates.extend(
                        [
                            item
                            for item in generic_candidates
                            if _is_stock_image_candidate(item, stock_domain_hints)
                        ]
                    )
                    stock_candidates = [
                        item
                        for item in stock_candidates
                        if _is_stock_image_candidate(item, stock_domain_hints)
                    ]

                    ranked_candidates = _dedupe_image_candidates([*stock_candidates, *generic_candidates])
                    image_search_cache[keyword] = ranked_candidates

                candidates = image_search_cache.get(keyword, [])
                for item in candidates:
                    candidate_url = str(item.get("url") or "").strip()
                    if not candidate_url:
                        continue
                    if candidate_url not in data_uri_cache:
                        data_uri_cache[candidate_url] = await _fetch_image_data_uri(candidate_url)
                    if data_uri_cache[candidate_url]:
                        selected_url = candidate_url
                        selected_source = "stock" if _is_stock_image_candidate(item, stock_domain_hints) else "web"
                        break
                if selected_url:
                    break

            if selected_url:
                data_uri = data_uri_cache[selected_url]
                if data_uri:
                    content_obj["url"] = data_uri
                    data_obj["source_url"] = selected_url
                    data_obj["source_type"] = selected_source or "web"
                else:
                    data_obj["source_type"] = "missing"
            else:
                data_obj["source_type"] = "missing"

            block["content"] = content_obj
            if data_obj:
                block["data"] = data_obj

    out["slides"] = slides
    return out


def _get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
        if url and key:
            _supabase = create_client(url, key)
    return _supabase


def _persist_ppt_retry_diagnostic(payload: Dict[str, Any]) -> None:
    sb = _get_supabase()
    if not sb:
        return
    try:
        sb.table("autoviralvid_ppt_retry_diagnostics").insert(payload).execute()
    except Exception as exc:
        logger.debug("[ppt_service] skip retry diagnostic persistence: %s", exc)


class PPTService:
    @staticmethod
    def _cache_render_job(job: RenderJob) -> None:
        _local_render_jobs[job.id] = {
            "id": job.id,
            "project_id": job.project_id,
            "status": job.status,
            "progress": job.progress,
            "lambda_job_id": job.lambda_job_id,
            "output_url": job.output_url,
            "error": job.error,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    async def generate_outline(self, req: OutlineRequest) -> PresentationOutline:
        from src.outline_generator import generate_outline

        return await generate_outline(
            requirement=req.requirement,
            language=req.language,
            num_slides=req.num_slides,
            style=req.style,
            purpose=req.purpose,
        )

    async def generate_content(self, req: ContentRequest) -> List[SlideContent]:
        from src.content_generator import generate_content

        return await generate_content(
            outline=req.outline,
            language=req.language,
        )

    async def generate_research_context(self, req: ResearchRequest) -> ResearchContext:
        topic = req.topic.strip()
        is_zh = req.language == "zh-CN" or _prefer_zh(
            topic,
            req.audience,
            req.purpose,
            req.style_preference,
            req.constraints,
            req.required_facts,
        )
        if is_zh:
            questions = [
                ResearchQuestion(
                    question="这份PPT的核心受众是谁？",
                    category="audience",
                    why="受众决定表达深度、叙事方式和术语密度。",
                ),
                ResearchQuestion(
                    question="这次演示最核心的目标是什么？",
                    category="purpose",
                    why="目标会影响结构是偏说服、汇报还是教学。",
                ),
                ResearchQuestion(
                    question="希望呈现怎样的视觉风格和语气？",
                    category="style",
                    why="风格偏好会直接影响配色、排版和内容密度。",
                ),
                ResearchQuestion(
                    question="必须展示的关键数据有哪些？",
                    category="data",
                    why="关键数据决定图表、KPI和证据链是否完整。",
                ),
                ResearchQuestion(
                    question="页数、时长和重点章节有哪些限制？",
                    category="scope",
                    why="范围约束决定每页信息量和取舍策略。",
                ),
            ]
            fallback_key_data_points = [
                f"{topic} 的市场规模与近3年增速",
                f"{topic} 的目标人群与转化漏斗",
                f"{topic} 的核心经营指标（收入/成本/ROI）",
                f"{topic} 的竞争格局与差异化优势",
                f"{topic} 的阶段目标与里程碑",
            ]
        else:
            questions = [
                ResearchQuestion(
                    question="Who is the primary audience for this deck?",
                    category="audience",
                    why="Audience determines language depth, examples, and narrative framing.",
                ),
                ResearchQuestion(
                    question="What is the primary objective of this presentation?",
                    category="purpose",
                    why="Objective drives whether the structure is persuasive, reporting, or educational.",
                ),
                ResearchQuestion(
                    question="Which visual tone and style is preferred?",
                    category="style",
                    why="Style preference affects theme, palette, and layout density.",
                ),
                ResearchQuestion(
                    question="Which key data points must be shown?",
                    category="data",
                    why="Must-have data determines chart and KPI component choices.",
                ),
                ResearchQuestion(
                    question="What are the page-count and time constraints?",
                    category="scope",
                    why="Scope constraints decide per-slide density and priority allocation.",
                ),
            ]
            fallback_key_data_points = [
                f"{topic} market size and 3-year growth trend",
                f"{topic} target audience and conversion funnel",
                f"{topic} core metrics (revenue/cost/ROI)",
                f"{topic} competitor comparison and differentiation",
                f"{topic} milestones and phased goals",
            ]
        required_facts = _dedup_strings(list(req.required_facts or []), limit=12)
        gaps = _build_research_gaps(req, is_zh=is_zh)
        search_queries = _build_research_queries(req, is_zh=is_zh, gaps=gaps)
        base_score = _score_research_completeness(
            req,
            key_data_points=0,
            references=0,
            evidence_count=0,
            gaps=gaps,
        )
        should_enrich = bool(req.web_enrichment) and (
            base_score < req.min_completeness
            or any(gap.severity in {"high", "medium"} for gap in gaps)
        )

        key_data_points: List[str] = []
        references: List[Dict[str, str]] = []
        evidence: List[ResearchEvidence] = []
        serper_api_key = str(_env_value("SERPER_API_KEY", "")).strip()

        if should_enrich and serper_api_key:
            seen_urls = set()
            fetched_at = _utc_now()
            for query in search_queries:
                items = await _search_serper_web(
                    query=query,
                    api_key=serper_api_key,
                    num=req.max_search_results,
                    gl="cn" if is_zh else "us",
                    hl="zh-cn" if is_zh else "en",
                )
                for item in items:
                    url = str(item.get("url") or "").strip()
                    title = str(item.get("title") or "").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    if not url or not title or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    confidence = _score_evidence_confidence(url, snippet)
                    references.append({"title": title, "url": url})
                    evidence.append(
                        ResearchEvidence(
                            claim=(snippet or title)[:500],
                            source_title=title[:300],
                            source_url=url,
                            snippet=snippet[:800],
                            fetched_at=fetched_at,
                            confidence=confidence,
                            provenance="web",
                            tags=_dedup_strings(
                                [
                                    "required_fact"
                                    for fact in required_facts
                                    if fact.lower() in f"{title} {snippet}".lower()
                                ],
                                limit=4,
                            ),
                        )
                    )
                    if snippet:
                        key_data_points.append(snippet[:180])
                    key_data_points.append(title[:140])
                if len(references) >= max(req.desired_citations, 3) and len(key_data_points) >= 8:
                    break
        elif should_enrich and not serper_api_key:
            logger.info(
                "[ppt_service] SERPER_API_KEY missing; fallback to synthesized research context for topic=%s",
                topic,
            )

        dedup_points = _dedup_strings(
            [*required_facts, *key_data_points, *fallback_key_data_points],
            limit=8,
        )
        guard = 0
        while len(dedup_points) < 3:
            dedup_points.append(
                (
                    f"{topic} 的关键指标需进一步补充来源（补充项{guard + 1}）"
                    if is_zh
                    else f"{topic} key metrics need additional verifiable sources ({guard + 1})"
                )
            )
            dedup_points = _dedup_strings(dedup_points, limit=8)
            guard += 1
            if guard >= 3:
                break

        dedup_refs: List[Dict[str, str]] = []
        seen_urls = set()
        for row in references:
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            dedup_refs.append({"title": title, "url": url})
            if len(dedup_refs) >= max(req.desired_citations + 2, 5):
                break

        if len(dedup_refs) < req.desired_citations:
            for query in search_queries:
                fallback_url = f"https://www.google.com/search?q={url_quote(query)}"
                if fallback_url in seen_urls:
                    continue
                seen_urls.add(fallback_url)
                dedup_refs.append(
                    {
                        "title": (
                            f"待核验检索入口：{query}"
                            if is_zh
                            else f"Search entry to verify: {query}"
                        )[:300],
                        "url": fallback_url,
                    }
                )
                if len(dedup_refs) >= req.desired_citations:
                    break

        unresolved_gaps = list(gaps)
        if len(dedup_refs) < req.desired_citations:
            unresolved_gaps.append(
                ResearchGap(
                    code="citations",
                    severity="high",
                    message=(
                        f"可用参考来源不足（{len(dedup_refs)}/{req.desired_citations}）"
                        if is_zh
                        else f"Insufficient references ({len(dedup_refs)}/{req.desired_citations})"
                    ),
                    query_hint=search_queries[0] if search_queries else topic,
                )
            )

        if required_facts:
            evidence_corpus = " ".join(
                [*dedup_points, *[e.claim for e in evidence], *[e.snippet for e in evidence]]
            ).lower()
            missing_facts = [fact for fact in required_facts if fact.lower() not in evidence_corpus]
            for fact in missing_facts[:3]:
                unresolved_gaps.append(
                    ResearchGap(
                        code="required_facts",
                        severity="medium",
                        message=(
                            f"关键数据点未被覆盖：{fact}"
                            if is_zh
                            else f"Required fact not covered: {fact}"
                        ),
                        query_hint=fact,
                    )
                )

        dedup_gaps: List[ResearchGap] = []
        seen_gap_keys = set()
        for gap in unresolved_gaps:
            marker = f"{gap.code}|{gap.message.strip().lower()}|{gap.query_hint.strip().lower()}"
            if marker in seen_gap_keys:
                continue
            seen_gap_keys.add(marker)
            dedup_gaps.append(gap)

        completeness_score = _score_research_completeness(
            req,
            key_data_points=len(dedup_points),
            references=len(dedup_refs),
            evidence_count=len(evidence),
            gaps=dedup_gaps,
        )
        enrichment_strategy = (
            "web" if evidence else ("web+fallback" if should_enrich else "none")
        )
        return ResearchContext(
            topic=topic,
            language="zh-CN" if is_zh else "en-US",
            audience=req.audience,
            purpose=req.purpose,
            style_preference=req.style_preference,
            constraints=req.constraints,
            required_facts=required_facts,
            geography=req.geography,
            time_range=req.time_range,
            domain_terms=req.domain_terms,
            key_data_points=dedup_points[:8],
            reference_materials=dedup_refs[: max(req.desired_citations, 3)],
            evidence=evidence[:12],
            gap_report=dedup_gaps[:12],
            completeness_score=completeness_score,
            enrichment_applied=bool(should_enrich),
            enrichment_strategy=enrichment_strategy,
            questions=questions,
        )

    async def generate_outline_plan(self, req: OutlinePlanRequest) -> OutlinePlan:
        total_pages = req.total_pages
        data_points = [str(x).strip() for x in req.research.key_data_points if str(x).strip()]
        if not data_points:
            data_points = [req.research.topic]
        is_zh = _prefer_zh(req.research.topic, req.research.audience, req.research.purpose)

        notes: List[StickyNote] = []
        for idx in range(total_pages):
            page_number = idx + 1
            if idx == 0:
                core_message = (
                    f"{req.research.topic}总览"[:30]
                    if is_zh
                    else f"{req.research.topic} overview"
                )
                density = "low"
                data_elements: List[str] = []
                visual_anchor = "title"
            elif idx == total_pages - 1:
                core_message = (
                    f"{req.research.topic}关键结论"[:30]
                    if is_zh
                    else f"{req.research.topic} key takeaways"
                )
                density = "low"
                data_elements = ["summary", "action"]
                visual_anchor = "summary"
            else:
                seed = data_points[(idx - 1) % len(data_points)]
                core_message = seed[:30]
                if idx % 4 == 0:
                    data_elements = ["kpi", "chart", "table", "trend"]
                elif idx % 3 == 0:
                    data_elements = ["kpi", "chart", "comparison"]
                elif idx % 2 == 0:
                    data_elements = ["timeline", "list"]
                else:
                    data_elements = ["list", "insight"]
                density = "high" if len(data_elements) >= 3 else "medium"
                visual_anchor = "chart" if "chart" in data_elements or "kpi" in data_elements else "text"

            point_base = idx % len(data_points)
            points = [
                data_points[(point_base + 0) % len(data_points)][:120],
                data_points[(point_base + 1) % len(data_points)][:120],
                data_points[(point_base + 2) % len(data_points)][:120],
            ]

            seed_note = StickyNote(
                page_number=page_number,
                core_message=core_message[:30],
                layout_hint="split_2",
                content_density=density,  # type: ignore[arg-type]
                data_elements=data_elements,
                visual_anchor=visual_anchor,
                key_points=points,
                speaker_notes=(
                    f"第{page_number}页：突出一个核心观点，并给出可执行结论。"
                    if is_zh
                    else f"Page {page_number} focus with concise storyline."
                ),
            )
            layout = recommend_layout(seed_note, idx, total_pages)
            notes.append(seed_note.model_copy(update={"layout_hint": layout}))

        fixed_layouts = enforce_layout_diversity([note.layout_hint for note in notes])
        notes = [
            note.model_copy(update={"layout_hint": fixed_layouts[idx]})
            for idx, note in enumerate(notes)
        ]

        return OutlinePlan(
            title=req.research.topic,
            total_pages=total_pages,
            theme_suggestion="slate_minimal",
            style_suggestion="soft",
            notes=notes,
            logic_flow=(
                "先交代背景与问题，再给出证据和方案，最后收束到行动建议。"
                if is_zh
                else "Open with context, build evidence and proposals, end with clear actions."
            ),
        )

    async def generate_presentation_plan(
        self, req: PresentationPlanRequest
    ) -> PresentationPlan:
        is_zh = _prefer_zh(req.outline.title, req.research.topic if req.research else "")

        def _kpi_seed(page_number: int) -> int:
            return 80 + ((page_number * 17) % 65)

        def _chart_series(base: int) -> List[int]:
            return [base, int(base * 1.18), int(base * 1.36)]

        def _labels() -> List[str]:
            return ["2024", "2025E", "2026E"] if is_zh else ["2024", "2025E", "2026E"]

        def _compact_points(
            points: List[str],
            *,
            max_points: int = 4,
            max_chars: int = 96,
        ) -> List[str]:
            dedup: List[str] = []
            seen = set()
            for raw in points or []:
                text = str(raw or "").strip()
                if not text:
                    continue
                for piece in re.split(r"[;；,\n，。.!?]+", text):
                    item = str(piece or "").strip()
                    if len(item) < 4:
                        continue
                    clipped = item[:max_chars].strip()
                    if not clipped:
                        continue
                    key = clipped.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    dedup.append(clipped)
                    if len(dedup) >= max_points:
                        return dedup
            return dedup

        def _split_points_for_two_columns(points: List[str]) -> tuple[List[str], List[str]]:
            unique: List[str] = []
            seen = set()
            for item in points:
                text = str(item or "").strip()
                if not text:
                    continue
                key = text.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(text)
            if not unique:
                return [], []
            if len(unique) == 1:
                return [unique[0]], []
            pivot = max(1, (len(unique) + 1) // 2)
            left = unique[:pivot]
            right = unique[pivot:]
            if not right:
                right = unique[-1:]
            return left, right

        slides: List[SlidePlan] = []
        for note in req.outline.notes:
            lower_elements = [str(item).strip().lower() for item in note.data_elements]
            need_chart = ("chart" in lower_elements) or note.layout_hint in {"grid_3", "grid_4", "bento_6", "timeline"}
            need_kpi = ("kpi" in lower_elements) or note.layout_hint in {"grid_3", "bento_6"}
            need_image = ("image" in lower_elements) or note.visual_anchor.lower() in {"image", "图片", "图像"} or note.layout_hint in {"asymmetric_2", "bento_5"}
            compact_points = _compact_points(note.key_points, max_points=4, max_chars=96)
            if not compact_points:
                compact_points = (
                    ["核心结论", "关键论据", "落地动作"]
                    if is_zh
                    else ["Core insight", "Key evidence", "Execution action"]
                )

            blocks: List[ContentBlock] = [
                ContentBlock(
                    block_type="title",
                    position="top",
                    content=note.core_message,
                    emphasis=[],
                )
            ]

            if note.layout_hint == "cover":
                blocks.append(
                    ContentBlock(
                        block_type="subtitle",
                        position="center",
                        content=(
                            "围绕核心价值主张，建立背景、痛点与机会的第一页认知。"
                            if is_zh
                            else "Opening statement tailored to target audience."
                        ),
                        emphasis=["value"],
                    )
                )
            elif note.layout_hint == "summary":
                blocks.append(
                    ContentBlock(
                        block_type="list",
                        position="center",
                        content="; ".join(compact_points[:3]),
                        emphasis=["conclusion", "action"] if not is_zh else ["结论", "行动"],
                    )
                )
            else:
                left_points, right_points = _split_points_for_two_columns(compact_points)
                if not left_points:
                    left_points = compact_points[:1]
                if not right_points:
                    right_points = compact_points[-1:] or left_points[:1]
                if need_kpi:
                    kpi_value = _kpi_seed(note.page_number)
                    blocks.append(
                        ContentBlock(
                            block_type="kpi",
                            position="left",
                            content="核心指标" if is_zh else "Core KPI",
                            data={
                                "number": kpi_value,
                                "unit": "%" if ("占比" in note.core_message or "增长" in note.core_message or not is_zh) else "点",
                                "trend": 6 + (note.page_number % 12),
                                "label": note.core_message[:24],
                            },
                            emphasis=["growth"] if not is_zh else ["增长"],
                        )
                    )
                if need_chart:
                    base = 35 + (note.page_number * 9)
                    blocks.append(
                        ContentBlock(
                            block_type="chart",
                            position="right" if need_kpi else "center",
                            content="趋势对比" if is_zh else "Trend comparison",
                            data={
                                "chartType": "bar",
                                "labels": _labels(),
                                "datasets": [
                                    {
                                        "label": "关键指标" if is_zh else "Key metric",
                                        "data": _chart_series(base),
                                    }
                                ],
                            },
                            emphasis=["trend"] if not is_zh else ["趋势"],
                        )
                    )
                if need_image:
                    blocks.append(
                        ContentBlock(
                            block_type="image",
                            position="right" if not need_chart else "bottom_right",
                            content="视觉锚点图" if is_zh else "Visual anchor image",
                            data={
                                "title": note.core_message,
                                "keywords": [req.outline.title, note.core_message, note.visual_anchor],
                            },
                            emphasis=["visual_anchor"],
                        )
                    )
                blocks.append(
                    ContentBlock(
                        block_type="body",
                        position="left",
                        content="; ".join(left_points),
                        emphasis=["focus"] if not is_zh else ["重点"],
                    )
                )
                blocks.append(
                    ContentBlock(
                        block_type="list",
                        position="right",
                        content="; ".join(right_points),
                        emphasis=["evidence"] if not is_zh else ["证据"],
                    )
                )

            slides.append(
                SlidePlan(
                    page_number=note.page_number,
                    slide_type=_layout_to_slide_type(note.layout_hint),  # type: ignore[arg-type]
                    layout_grid=note.layout_hint,
                    blocks=blocks,
                    bg_style="light",
                    image_keywords=[req.outline.title, note.visual_anchor],
                    notes_for_designer=(
                        "保证标题层级明显，视觉锚点优先，图文区域留足呼吸感。"
                        if is_zh
                        else "Keep hierarchy clear and prioritize readability."
                    ),
                )
            )

        return PresentationPlan(
            title=req.outline.title,
            theme=req.outline.theme_suggestion,
            style=req.outline.style_suggestion,
            slides=slides,
            global_notes=(
                "先确保内容完整与证据链，再做视觉打磨。"
                if is_zh
                else "Prioritize content completeness and logic before styling polish."
            ),
        )

    async def run_ppt_pipeline(self, req: PPTPipelineRequest) -> PPTPipelineResult:
        from src.minimax_exporter import export_minimax_pptx
        from src.ppt_quality_gate import validate_deck, validate_layout_diversity

        run_id = _new_id()
        stages: List[PPTPipelineStageStatus] = []

        def _append_stage(
            stage: str,
            started_at: str,
            ok: bool,
            diagnostics: Optional[List[str]] = None,
        ) -> None:
            stages.append(
                PPTPipelineStageStatus(
                    stage=stage,  # type: ignore[arg-type]
                    ok=ok,
                    started_at=started_at,
                    finished_at=_utc_now(),
                    diagnostics=diagnostics or [],
                )
            )

        # Stage 1: research
        research_started = _utc_now()
        research_req = ResearchRequest(
            topic=req.topic,
            language=req.language,
            audience=req.audience,
            purpose=req.purpose,
            style_preference=req.style_preference,
            constraints=req.constraints,
            required_facts=req.required_facts,
            geography=req.geography,
            time_range=req.time_range,
            domain_terms=req.domain_terms,
            web_enrichment=req.web_enrichment,
            min_completeness=req.research_min_completeness,
            desired_citations=req.desired_citations,
            max_web_queries=req.max_web_queries,
            max_search_results=req.max_search_results,
        )
        research = await self.generate_research_context(research_req)
        min_points = max(3, int(req.min_key_data_points))
        min_refs = max(1, int(req.min_reference_materials))
        failures: List[str] = []
        if len(research.key_data_points) < min_points:
            failures.append(f"insufficient key_data_points (<{min_points})")
        if len(research.reference_materials) < min_refs:
            failures.append(f"insufficient reference_materials (<{min_refs})")
        if float(research.completeness_score) < float(req.research_min_completeness):
            failures.append(
                "insufficient completeness "
                f"({research.completeness_score:.3f} < {float(req.research_min_completeness):.3f})"
            )
        diagnostics = [
            f"completeness={research.completeness_score:.3f}",
            f"references={len(research.reference_materials)}",
            f"evidence={len(research.evidence)}",
            f"gaps={len(research.gap_report)}",
            f"enrichment={research.enrichment_strategy}",
        ]
        if failures:
            _append_stage("research", research_started, False, failures + diagnostics)
            raise ValueError("Research stage failed: " + "; ".join(failures[:3]))
        _append_stage("research", research_started, True, diagnostics)
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-1-research", research.model_dump())

        # Stage 2: sticky-note outline plan
        outline_started = _utc_now()
        outline_plan = await self.generate_outline_plan(
            OutlinePlanRequest(
                research=research,
                total_pages=req.total_pages,
            )
        )
        _append_stage("outline_plan", outline_started, True)
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-2-outline-plan", outline_plan.model_dump())

        # Stage 3: wireframe presentation plan
        presentation_started = _utc_now()
        presentation_plan = await self.generate_presentation_plan(
            PresentationPlanRequest(outline=outline_plan, research=research)
        )
        _append_stage("presentation_plan", presentation_started, True)
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-3-presentation-plan", presentation_plan.model_dump())

        base_render_payload = _presentation_plan_to_render_payload(presentation_plan)
        if str(req.quality_profile or "").strip() and str(req.quality_profile).strip().lower() != "auto":
            base_render_payload["quality_profile"] = str(req.quality_profile).strip()
        render_payload = await _hydrate_image_assets(
            _apply_visual_orchestration(base_render_payload)
        )

        # Stage 4: strict quality gate before any render/export
        quality_started = _utc_now()
        quality_issues = []
        quality_profile = str(render_payload.get("quality_profile") or req.quality_profile or "default").strip().lower()
        if not quality_profile or quality_profile == "auto":
            quality_profile = "default"
        for _attempt in range(1, 4):
            content_gate = validate_deck(
                render_payload.get("slides") or [],
                profile=quality_profile,
            )
            layout_gate = validate_layout_diversity(
                render_payload,
                profile=quality_profile,
                enforce_terminal_slide_types=True,
            )
            quality_issues = [*content_gate.issues, *layout_gate.issues]
            if not quality_issues:
                break
            # Stage 2 repair: enforce visual contract and asset placeholders before retrying.
            render_payload = await _hydrate_image_assets(_apply_visual_orchestration(render_payload))
            if _attempt >= 3:
                break

        if quality_issues:
            diagnostics = _collect_stage_diagnostics(
                "quality",
                [
                    f"{issue.slide_id}:{issue.code}:{issue.message}"
                    for issue in quality_issues
                ],
                limit=20,
            )
            _append_stage("quality_gate", quality_started, False, diagnostics + [f"profile={quality_profile}"])
            raise ValueError("Quality gate failed: " + "; ".join(diagnostics[:6]))
        _append_stage("quality_gate", quality_started, True, [f"profile={quality_profile}"])
        if req.save_artifacts:
            _write_pipeline_artifact(run_id, "stage-4-render-payload", render_payload)

        export_data: Optional[Dict[str, Any]] = None
        export_started = _utc_now()
        if req.with_export:
            export_channel = _resolve_export_channel(req.export_channel)
            export_data = export_minimax_pptx(
                slides=render_payload["slides"],
                title=req.title or presentation_plan.title,
                author=req.author,
                render_channel=export_channel,
                style_variant=req.minimax_style_variant,
                palette_key=req.minimax_palette_key,
                deck_id=run_id,
                generator_mode="official",
                original_style=True,
                disable_local_style_rewrite=True,
                visual_priority=True,
                visual_preset="tech_cinematic",
                visual_density="balanced",
                constraint_hardness="minimal",
                svg_mode="on",
                template_family="auto",
                template_id=str(render_payload.get("template_id") or ""),
                skill_profile=str(render_payload.get("skill_profile") or ""),
                hardness_profile=str(render_payload.get("hardness_profile") or ""),
                schema_profile=str(render_payload.get("schema_profile") or ""),
                contract_profile=str(render_payload.get("contract_profile") or ""),
                quality_profile=quality_profile,
                enforce_visual_contract=True,
                timeout=180,
            )
            _append_stage("export", export_started, True, [f"channel={export_channel}"])
            if req.save_artifacts and isinstance(export_data, dict):
                _write_pipeline_artifact(run_id, "stage-5-export", export_data)
        else:
            _append_stage("export", export_started, True, ["skipped by request"])

        return PPTPipelineResult(
            run_id=run_id,
            stages=stages,
            artifacts=PPTPipelineArtifacts(
                research=research,
                outline_plan=outline_plan,
                presentation_plan=presentation_plan,
                render_payload=render_payload,
            ),
            export=export_data,
        )

    async def export_pptx(self, req: ExportRequest) -> Dict[str, Any]:
        import asyncio

        from src.minimax_exporter import MiniMaxExportError, export_minimax_pptx
        from src.ppt_failure_classifier import classify_failure
        from src.ppt_patch_merge import merge_render_spec
        from src.ppt_quality_gate import validate_deck, validate_layout_diversity
        from src.ppt_retry_orchestrator import build_retry_hint, make_retry_decision
        from src.pptx_rasterizer import rasterize_pptx_bytes_to_png_bytes
        from src.r2 import upload_bytes_to_r2

        slides_data = [s.model_dump() for s in req.slides]
        visual_seed = await _hydrate_image_assets(
            _apply_visual_orchestration(
                {
                    "title": req.title,
                    "theme": {"palette": req.minimax_palette_key, "style": req.minimax_style_variant},
                    "slides": slides_data,
                    "template_family": req.template_family,
                    "template_id": req.template_family if req.template_family != "auto" else "",
                    "skill_profile": req.skill_profile,
                    "hardness_profile": req.hardness_profile,
                    "schema_profile": req.schema_profile,
                    "contract_profile": req.contract_profile,
                    "quality_profile": req.quality_profile,
                    "svg_mode": req.svg_mode,
                }
            )
        )
        orchestrated_slides = visual_seed.get("slides")
        if isinstance(orchestrated_slides, list):
            slides_data = orchestrated_slides
        skill = "minimax_pptx_generator"
        logger.info("[ppt_service] export_pptx using skill=%s", skill)

        retry_enabled = str(os.getenv("PPT_RETRY_ENABLED", "true")).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        partial_retry_enabled = (
            str(os.getenv("PPT_PARTIAL_RETRY_ENABLED", "true")).strip().lower()
            not in {"0", "false", "no", "off"}
        )
        max_retry_attempts = max(1, int(os.getenv("PPT_RETRY_MAX_ATTEMPTS", "3")))
        env_generator_mode = str(os.getenv("PPT_GENERATOR_MODE", "official")).strip().lower()
        if env_generator_mode not in {"official", "legacy"}:
            env_generator_mode = "official"
        allow_legacy_mode = _env_flag("PPT_ALLOW_LEGACY_MODE", "false")
        enable_legacy_fallback = _env_flag("PPT_ENABLE_LEGACY_FALLBACK", "false") and allow_legacy_mode

        retry_scope = req.retry_scope
        target_slide_ids = list(req.target_slide_ids or [])
        target_block_ids = list(req.target_block_ids or [])
        retry_hint = req.retry_hint
        deck_id = req.deck_id or _new_id()
        export_channel = _resolve_export_channel(req.export_channel)
        quality_profile = str(req.quality_profile or visual_seed.get("quality_profile") or "default").strip().lower()
        if not quality_profile or quality_profile == "auto":
            quality_profile = "default"
        requested_mode = str(req.generator_mode or "auto").strip().lower()
        if requested_mode == "legacy" and allow_legacy_mode:
            generator_mode = "legacy"
        elif requested_mode == "legacy" and not allow_legacy_mode:
            logger.warning(
                "[ppt_service] requested legacy mode but PPT_ALLOW_LEGACY_MODE=false; forcing official"
            )
            generator_mode = "official"
        elif requested_mode == "official":
            generator_mode = "official"
        else:
            if env_generator_mode == "legacy" and allow_legacy_mode:
                generator_mode = "legacy"
            else:
                generator_mode = "official"

        render_spec_version = "v1"
        diagnostics: List[Dict[str, Any]] = []
        attempt = 1
        export_result: Dict[str, Any] | None = None
        base_render_spec: Dict[str, Any] | None = None

        while True:
            try:
                effective_visual_preset = (
                    "tech_cinematic" if str(req.visual_preset or "auto").strip().lower() == "auto" else str(req.visual_preset)
                )
                current_result = export_minimax_pptx(
                    slides=slides_data,
                    title=req.title,
                    author=req.author,
                    render_channel=export_channel,
                    generator_mode=generator_mode,
                    enable_legacy_fallback=enable_legacy_fallback,
                    style_variant=req.minimax_style_variant,
                    palette_key=req.minimax_palette_key,
                    verbatim_content=bool(req.verbatim_content),
                    deck_id=deck_id,
                    retry_scope=retry_scope,
                    target_slide_ids=target_slide_ids,
                    target_block_ids=target_block_ids,
                    retry_hint=retry_hint,
                    idempotency_key=req.idempotency_key or "",
                    original_style=bool(req.original_style),
                    disable_local_style_rewrite=bool(req.disable_local_style_rewrite),
                    visual_priority=bool(req.visual_priority),
                    visual_preset=effective_visual_preset,
                    visual_density=str(req.visual_density or "balanced"),
                    constraint_hardness=str(req.constraint_hardness or "minimal"),
                    svg_mode=str(req.svg_mode or "on"),
                    template_family=str(req.template_family or "auto"),
                    template_id=str(req.template_family if req.template_family != "auto" else ""),
                    skill_profile=str(req.skill_profile or ""),
                    hardness_profile=str(req.hardness_profile or ""),
                    schema_profile=str(req.schema_profile or ""),
                    contract_profile=str(req.contract_profile or ""),
                    quality_profile=quality_profile,
                    enforce_visual_contract=bool(req.enforce_visual_contract),
                    timeout=180,
                )
                generator_mode = str(current_result.get("generator_mode") or generator_mode)

                if base_render_spec is None:
                    base_render_spec = current_result.get("render_spec") or {}
                elif partial_retry_enabled and retry_scope in {"slide", "block"}:
                    current_patch = current_result.get("render_spec") or {}
                    current_result["render_spec"] = merge_render_spec(base_render_spec, current_patch)
                    base_render_spec = current_result.get("render_spec") or {}

                content_gate = validate_deck(
                    (current_result.get("input_payload") or {}).get("slides") or slides_data,
                    profile=quality_profile,
                )
                layout_gate = validate_layout_diversity(
                    current_result.get("render_spec") or {},
                    profile=quality_profile,
                )
                gate_issues = [*content_gate.issues, *layout_gate.issues]
                if not gate_issues:
                    export_result = current_result
                    diagnostics.append(
                        {
                            "attempt": attempt,
                            "status": "success",
                            "export_channel": export_channel,
                            "generator_mode": generator_mode,
                            "retry_scope": retry_scope,
                            "quality_profile": quality_profile,
                            "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                        }
                    )
                    break

                issue_codes = {issue.code for issue in gate_issues}
                failure_code = (
                    "encoding_invalid"
                    if "encoding_invalid" in issue_codes
                    else (
                        "layout_homogeneous"
                        if (
                            "layout_homogeneous" in issue_codes
                            or "layout_adjacent_repeat" in issue_codes
                        )
                        else "schema_invalid"
                    )
                )
                failure_detail = "; ".join(
                    f"{issue.slide_id}:{issue.code}" for issue in gate_issues[:10]
                )
                classification = classify_failure(failure_code)
                decision = make_retry_decision(
                    code=classification.code,
                    attempt=attempt,
                    max_attempts=min(max_retry_attempts, classification.max_attempts),
                    base_delay_ms=classification.base_delay_ms,
                )
                diagnostics.append(
                    {
                        "attempt": attempt,
                        "status": "quality_gate_failed",
                        "export_channel": export_channel,
                        "failure_code": classification.code,
                        "failure_detail": failure_detail,
                        "quality_profile": quality_profile,
                        "generator_mode": generator_mode,
                        "retry_scope": retry_scope,
                    }
                )
                _persist_ppt_retry_diagnostic(
                    {
                        "deck_id": deck_id,
                        "failure_code": classification.code,
                        "failure_detail": failure_detail,
                        "retry_scope": retry_scope,
                        "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                        "attempt": attempt,
                        "idempotency_key": req.idempotency_key,
                        "export_channel": export_channel,
                        "quality_profile": quality_profile,
                        "render_spec_version": render_spec_version,
                        "status": "quality_gate_failed",
                        "created_at": _utc_now(),
                    }
                )
                if (not retry_enabled) or (not decision.should_retry):
                    raise MiniMaxExportError(
                        message=f"PPT quality gate failed: {failure_detail}",
                        classification=classification,
                        detail=failure_detail,
                    )

                if partial_retry_enabled and gate_issues and failure_code != "layout_homogeneous":
                    retry_scope = "slide"
                    target_slide_ids = sorted({issue.slide_id for issue in gate_issues if issue.slide_id})
                    target_block_ids = []

                retry_hint = build_retry_hint(
                    failure_code=classification.code,
                    failure_detail=failure_detail,
                    attempt=attempt,
                    retry_scope=retry_scope,
                    target_ids=target_block_ids if retry_scope == "block" else target_slide_ids,
                )
                await asyncio.sleep(decision.delay_ms / 1000.0)
                attempt += 1
            except MiniMaxExportError as exc:
                classification = exc.classification
                if classification.code == "schema_invalid":
                    schema_targets = _extract_slide_targets_from_schema_error(exc.detail, slides_data)
                    if schema_targets:
                        retry_scope = "slide"
                        target_slide_ids = schema_targets
                        target_block_ids = []
                        # Re-apply visual orchestration before retrying only failed pages.
                        slides_data = (
                            await _hydrate_image_assets(
                                _apply_visual_orchestration(
                                    {
                                        "title": req.title,
                                        "theme": {"palette": req.minimax_palette_key, "style": req.minimax_style_variant},
                                        "slides": slides_data,
                                        "template_family": req.template_family,
                                        "template_id": req.template_family if req.template_family != "auto" else "",
                                        "skill_profile": req.skill_profile,
                                        "hardness_profile": req.hardness_profile,
                                        "schema_profile": req.schema_profile,
                                        "contract_profile": req.contract_profile,
                                        "quality_profile": req.quality_profile,
                                        "svg_mode": req.svg_mode,
                                    }
                                )
                            )
                        ).get("slides", slides_data)
                decision = make_retry_decision(
                    code=classification.code,
                    attempt=attempt,
                    max_attempts=min(max_retry_attempts, classification.max_attempts),
                    base_delay_ms=classification.base_delay_ms,
                )
                diagnostics.append(
                    {
                        "attempt": attempt,
                        "status": "failed",
                        "failure_code": classification.code,
                        "failure_detail": exc.detail[:800],
                        "generator_mode": generator_mode,
                        "retry_scope": retry_scope,
                        "retryable": classification.retryable,
                    }
                )
                _persist_ppt_retry_diagnostic(
                    {
                        "deck_id": deck_id,
                        "failure_code": classification.code,
                        "failure_detail": exc.detail[:1200],
                        "retry_scope": retry_scope,
                        "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                        "attempt": attempt,
                        "idempotency_key": req.idempotency_key,
                        "export_channel": export_channel,
                        "quality_profile": quality_profile,
                        "render_spec_version": render_spec_version,
                        "status": "failed",
                        "created_at": _utc_now(),
                    }
                )

                if (not retry_enabled) or (not decision.should_retry):
                    raise

                retry_hint = build_retry_hint(
                    failure_code=classification.code,
                    failure_detail=exc.detail,
                    attempt=attempt,
                    retry_scope=retry_scope,
                    target_ids=target_block_ids if retry_scope == "block" else target_slide_ids,
                )
                await asyncio.sleep(decision.delay_ms / 1000.0)
                attempt += 1
            except Exception as exc:
                classification = classify_failure(exc)
                decision = make_retry_decision(
                    code=classification.code,
                    attempt=attempt,
                    max_attempts=min(max_retry_attempts, classification.max_attempts),
                    base_delay_ms=classification.base_delay_ms,
                )
                failure_detail = str(exc)
                diagnostics.append(
                    {
                        "attempt": attempt,
                        "status": "failed",
                        "failure_code": classification.code,
                        "failure_detail": failure_detail[:800],
                        "generator_mode": generator_mode,
                        "retry_scope": retry_scope,
                        "retryable": classification.retryable,
                    }
                )
                _persist_ppt_retry_diagnostic(
                    {
                        "deck_id": deck_id,
                        "failure_code": classification.code,
                        "failure_detail": failure_detail[:1200],
                        "retry_scope": retry_scope,
                        "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                        "attempt": attempt,
                        "idempotency_key": req.idempotency_key,
                        "render_spec_version": render_spec_version,
                        "status": "failed",
                        "created_at": _utc_now(),
                    }
                )
                if (not retry_enabled) or (not decision.should_retry):
                    raise
                retry_hint = build_retry_hint(
                    failure_code=classification.code,
                    failure_detail=failure_detail,
                    attempt=attempt,
                    retry_scope=retry_scope,
                    target_ids=target_block_ids if retry_scope == "block" else target_slide_ids,
                )
                await asyncio.sleep(decision.delay_ms / 1000.0)
                attempt += 1

        if export_result is None:
            raise RuntimeError("MiniMax export completed without result")

        project_id = _new_id()
        key = f"projects/{project_id}/pptx/presentation.pptx"
        url = await upload_bytes_to_r2(
            export_result["pptx_bytes"],
            key,
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        export_data: Dict[str, Any] = {"url": url, "skill": skill}
        generator_meta = export_result.get("generator_meta") or {}
        if generator_meta:
            export_data["generator_meta"] = generator_meta
        export_data["generator_mode"] = export_result.get("generator_mode", generator_mode)
        export_data["export_channel"] = export_result.get("render_channel", export_channel)
        export_data["quality_profile"] = quality_profile
        export_data["deck_id"] = deck_id
        export_data["attempts"] = attempt
        export_data["retry_scope"] = retry_scope
        export_data["render_spec_version"] = render_spec_version
        export_data["diagnostics"] = diagnostics

        slide_image_urls: List[str] = []
        try:
            png_bytes_list = rasterize_pptx_bytes_to_png_bytes(export_result["pptx_bytes"])
            for idx, png_bytes in enumerate(png_bytes_list):
                image_url = await upload_bytes_to_r2(
                    png_bytes,
                    key=f"projects/{project_id}/slides/slide_{idx + 1:03d}.png",
                    content_type="image/png",
                )
                slide_image_urls.append(image_url)
        except Exception as exc:
            logger.warning("[ppt_service] ppt rasterize skipped: %s", exc)
        if slide_image_urls:
            export_data["slide_image_urls"] = slide_image_urls
            export_data["video_mode"] = "ppt_image_slideshow"
            export_data["video_slides"] = _build_image_video_slides(slide_image_urls, slides_data)
            export_data["video_slide_count"] = len(slide_image_urls)

        render_spec = export_result.get("render_spec") or {}
        if isinstance(render_spec, dict) and not slide_image_urls:
            video_slides = render_spec.get("slides")
            if isinstance(video_slides, list) and video_slides:
                export_data["video_mode"] = render_spec.get("mode", "minimax_presentation")
                export_data["video_slides"] = video_slides
                export_data["video_slide_count"] = len(video_slides)

        _persist_ppt_retry_diagnostic(
            {
                "deck_id": deck_id,
                "failure_code": None,
                "failure_detail": None,
                "retry_scope": retry_scope,
                "retry_target_ids": target_block_ids if retry_scope == "block" else target_slide_ids,
                "attempt": attempt,
                "idempotency_key": req.idempotency_key,
                "render_spec_version": render_spec_version,
                "status": "success",
                "created_at": _utc_now(),
            }
        )

        return export_data

    async def parse_document(self, file_url: str, file_type: str = "pptx") -> ParsedDocument:
        from src.document_parser import parse_document

        return await parse_document(file_url, file_type)

    async def enhance_slides(
        self,
        slides: List[SlideContent],
        language: str = "zh-CN",
        enhance_narration: bool = True,
        generate_tts: bool = True,
        voice_style: str = "zh-CN-female",
    ) -> List[SlideContent]:
        if enhance_narration:
            slides = await self._enhance_narration(slides, language)
        if generate_tts:
            slides = await self._synthesize_tts(slides, voice_style)
        return slides

    async def _enhance_narration(
        self,
        slides: List[SlideContent],
        language: str,
    ) -> List[SlideContent]:
        import asyncio

        from src.openrouter_client import OpenRouterClient

        client = OpenRouterClient()
        model = os.getenv("ENHANCE_LLM_MODEL", "openai/gpt-4o-mini")
        if language == "zh-CN":
            system_prompt = (
                "You are a PPT narration optimizer. Rewrite for spoken delivery in Chinese, "
                "keep key facts, and target around 50-300 Chinese characters."
            )
        else:
            system_prompt = (
                "You are a PPT narration optimizer. Make text conversational, smooth, "
                "and concise while preserving key information."
            )

        semaphore = asyncio.Semaphore(5)

        async def _enhance_one(idx: int, slide: SlideContent) -> tuple[int, str]:
            async with semaphore:
                narration = (slide.narration or "").strip()
                if not narration:
                    text_parts = [
                        el.content
                        for el in slide.elements
                        if getattr(el, "type", "") == "text" and getattr(el, "content", "")
                    ]
                    narration = " ".join(text_parts).strip()[:500]
                if len(narration) < 10:
                    return idx, narration

                raw = await client.chat_completions(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"标题: {slide.title}\n\n讲解稿:\n{narration}"},
                    ],
                    temperature=0.5,
                    max_tokens=1024,
                )
                enhanced = (raw or "").strip() or narration
                return idx, enhanced

        tasks = [_enhance_one(i, s) for i, s in enumerate(slides)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning("[ppt_service] narration enhance failed: %s", result)
                continue
            idx, enhanced = result
            slides[idx] = slides[idx].model_copy(update={"narration": enhanced})

        return slides

    async def _synthesize_tts(
        self,
        slides: List[SlideContent],
        voice_style: str,
    ) -> List[SlideContent]:
        from src.tts_synthesizer import synthesize_batch

        texts = [s.narration for s in slides]
        urls, durations = await synthesize_batch(texts, voice_style)

        for i, url in enumerate(urls):
            if not url:
                continue
            audio_dur = durations[i] if i < len(durations) else 0
            slide_dur = max(3, int(audio_dur + 1))
            slides[i] = slides[i].model_copy(
                update={
                    "narration_audio_url": url,
                    "duration": slide_dur,
                }
            )
            logger.info(
                "[ppt_service] slide %d: audio %.1fs -> video %ss",
                i + 1,
                float(audio_dur),
                slide_dur,
            )

        return slides

    async def start_video_render(
        self,
        slides: List[Dict[str, Any]],
        config: VideoRenderConfig,
    ) -> RenderJob:
        from src.lambda_renderer import start_render

        job = RenderJob(
            project_id=_new_id(),
            status="pending",
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        self._cache_render_job(job)

        sb = _get_supabase()
        if sb:
            try:
                sb.table("ppt_render_jobs").upsert(
                    {
                        "id": job.id,
                        "project_id": job.project_id,
                        "status": job.status,
                        "progress": 0,
                        "config": config.model_dump_json(),
                        "created_at": job.created_at,
                        "updated_at": job.updated_at,
                    }
                ).execute()
            except Exception as exc:
                logger.warning("[ppt_service] failed to persist render job: %s", exc)

        try:
            image_mode = len(slides) > 0 and all(
                _is_image_slide(s.model_dump() if hasattr(s, "model_dump") else s) for s in slides
            )
            slides_data: List[Dict[str, Any]] = []
            for idx, slide in enumerate(slides):
                if isinstance(slide, dict):
                    if image_mode:
                        slides_data.append(_normalize_image_slide_for_renderer(slide))
                    else:
                        slides_data.append(_normalize_slide_for_renderer(slide, idx))
                elif hasattr(slide, "model_dump"):
                    slide_dict = slide.model_dump()  # type: ignore[arg-type]
                    if image_mode:
                        slides_data.append(_normalize_image_slide_for_renderer(slide_dict))
                    else:
                        slides_data.append(_normalize_slide_for_renderer(slide_dict, idx))
                else:
                    raise ValueError(f"Unsupported slide type: {type(slide)!r}")

            config_data = config.model_dump()
            if image_mode:
                config_data["composition"] = "ImageSlideshow"

            result = await start_render(
                slides=slides_data,
                config=config_data,
                prefer_local=not bool(os.getenv("REMOTION_LAMBDA_FUNCTION")),
            )

            job.lambda_job_id = result.get("render_id")
            job.output_url = result.get("video_url")
            if job.output_url:
                job.status = "done"
                job.progress = 100
            else:
                job.status = "rendering"
            job.updated_at = _utc_now()

            if sb:
                try:
                    sb.table("ppt_render_jobs").update(
                        {
                            "status": job.status,
                            "progress": job.progress,
                            "lambda_job_id": job.lambda_job_id,
                            "output_url": job.output_url,
                            "updated_at": job.updated_at,
                        }
                    ).eq("id", job.id).execute()
                except Exception:
                    pass
            self._cache_render_job(job)
        except Exception as exc:
            logger.error("[ppt_service] video render failed: %s", exc)
            job.status = "failed"
            job.error = str(exc)
            job.updated_at = _utc_now()
            if sb:
                try:
                    sb.table("ppt_render_jobs").update(
                        {
                            "status": "failed",
                            "error": job.error,
                            "updated_at": job.updated_at,
                        }
                    ).eq("id", job.id).execute()
                except Exception:
                    pass
            self._cache_render_job(job)

        return job

    async def get_render_status(self, job_id: str) -> Dict[str, Any]:
        sb = _get_supabase()
        if not sb:
            cached = _local_render_jobs.get(job_id)
            if cached:
                return _render_status_from_row(cached)
            return {"job_id": job_id, "status": "not_found"}

        try:
            res = sb.table("ppt_render_jobs").select("*").eq("id", job_id).limit(1).execute()
            if res.data:
                return _render_status_from_row(res.data[0])

            cached = _local_render_jobs.get(job_id)
            if cached:
                return _render_status_from_row(cached)
            return {"job_id": job_id, "status": "not_found"}
        except Exception as exc:
            logger.warning("[ppt_service] get_render_status supabase fallback: %s", exc)
            cached = _local_render_jobs.get(job_id)
            if cached:
                return _render_status_from_row(cached)
            return {"job_id": job_id, "status": "unknown", "error": str(exc)}

    async def get_download_url(self, job_id: str) -> Dict[str, Any]:
        sb = _get_supabase()
        row: Dict[str, Any] | None = None
        if sb:
            try:
                res = (
                    sb.table("ppt_render_jobs")
                    .select("*")
                    .eq("id", job_id)
                    .limit(1)
                    .execute()
                )
                if res.data:
                    row = res.data[0]
            except Exception as exc:
                logger.warning("[ppt_service] get_download_url supabase fallback: %s", exc)

        if row is None:
            row = _local_render_jobs.get(job_id)
        if row is None:
            raise LookupError(f"Render job not found: {job_id}")

        status = row.get("status", "unknown")
        if status not in ("done", "completed"):
            return {
                "job_id": job_id,
                "status": status,
                "message": f"Render not finished: {status}",
                "output_url": None,
            }

        output_url = row.get("output_url")
        if not output_url:
            return {
                "job_id": job_id,
                "status": status,
                "message": "Render finished but output URL is empty",
                "output_url": None,
            }

        try:
            from urllib.parse import urlparse

            from src.r2 import get_r2_client

            r2 = get_r2_client()
            if r2:
                parsed = urlparse(output_url)
                key = parsed.path.lstrip("/")
                bucket = os.getenv("R2_BUCKET", "video")
                presigned = r2.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": key},
                    ExpiresIn=3600,
                )
                return {"job_id": job_id, "status": status, "output_url": presigned}
        except Exception as exc:
            logger.warning("[ppt_service] presign failed, fallback direct URL: %s", exc)

        return {"job_id": job_id, "status": status, "output_url": output_url}
