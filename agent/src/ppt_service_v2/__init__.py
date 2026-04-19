"""Minimal PPT service focused on prompt-direct ppt-master runtime."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import httpx

from src.minimax_exporter import export_minimax_pptx
from src.schemas.ppt import (
    ContentRequest,
    ExportRequest,
    OutlineRequest,
    ParsedDocument,
    PresentationOutline,
    RenderJob,
    SlideBackground,
    SlideContent,
    SlideElement,
    SlideOutline,
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
    SlideContentStrategy,
    SlidePlan,
)
from src.schemas.ppt_research import (
    ResearchContext,
    ResearchEvidence,
    ResearchGap,
    ResearchQuestion,
    ResearchRequest,
)

_ALLOWED_LAYOUTS: List[LayoutType] = ["hero_1", "split_2", "asymmetric_2", "grid_3", "grid_4", "bento_5", "timeline"]
_LLM_ENV_KEYS = (
    "AIBERM_API_KEY",
    "CRAZYROUTE_API_KEY",
    "CRAZYROUTER_API_KEY",
    "OPENAI_API_KEY",
    "LLM_API_KEY",
)
_ALLOWED_SUGGESTED_ELEMENTS = {"text", "image", "chart", "table", "latex", "shape"}
logger = logging.getLogger("ppt_service_v2")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S%f")[-12:]


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _env_flag(name: str, default: bool) -> bool:
    raw = _text(os.getenv(name), "")
    if not raw:
        return bool(default)
    return raw.lower() in {"1", "true", "yes", "on"}


def _has_llm_credentials() -> bool:
    return any(_text(os.getenv(key), "") for key in _LLM_ENV_KEYS)


def _dedup(items: Iterable[str], *, limit: int = 20) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        row = _text(item)
        if not row:
            continue
        key = row.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _shorten(text: str, limit: int = 30) -> str:
    cleaned = _text(re.sub(r"\s+", " ", text))
    return cleaned[:limit] if len(cleaned) > limit else cleaned


def _extract_json_payload(raw: str) -> Dict[str, Any]:
    text = _text(raw)
    if not text:
        raise ValueError("empty llm response")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    for match in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL):
        snippet = _text(match.group(1))
        if not snippet:
            continue
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        snippet = text[start : end + 1]
        parsed = json.loads(snippet)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("invalid llm json payload")


def _list_of_text(values: Any, *, limit: int = 8) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for item in values:
        row = _shorten(_text(item), 200)
        if row:
            out.append(row)
        if len(out) >= limit:
            break
    return out


def _normalize_suggested_elements(values: Any) -> List[str]:
    selected = [item for item in _list_of_text(values, limit=6) if item in _ALLOWED_SUGGESTED_ELEMENTS]
    return selected or ["text", "chart"]


def _format_bullets(bullets: List[str]) -> str:
    rows = bullets[:6] or ["Key takeaway"]
    return "\n".join([f"• {item}" for item in rows])


def _build_content_elements(*, title: str, bullets: List[str], summary: str) -> List[SlideElement]:
    elements = [
        SlideElement(type="text", left=72, top=72, width=1136, height=96, content=title),
        SlideElement(type="text", left=92, top=192, width=760, height=420, content=_format_bullets(bullets)),
    ]
    if summary:
        elements.append(
            SlideElement(
                type="text",
                left=880,
                top=210,
                width=320,
                height=320,
                content=summary,
            )
        )
    return elements


def _build_key_points(topic: str, *, language: str, limit: int = 8) -> List[str]:
    seed = _text(topic, "Topic")
    subject = re.findall(r"[A-Za-z0-9\-_/]{3,}|[\u4e00-\u9fff]{2,}", seed)
    lead = subject[0] if subject else seed.split(" ")[0]
    rows = [
        f"Background and context of {lead}",
        f"Core drivers behind {lead}",
        "Timeline and major turning points",
        "Stakeholders and decision dynamics",
        "Impacts on international relations",
        "Risk scenarios and uncertainty factors",
        "Evidence and representative cases",
        "Policy implications and takeaways",
    ]
    if language != "en-US":
        rows[0] = f"{lead} background and context"
        rows[1] = "Core drivers and triggers"
    return _dedup(rows, limit=limit)


def _fallback_references(topic: str) -> List[Dict[str, str]]:
    q = _text(topic, "presentation topic").replace(" ", "+")
    return [
        {"title": "Topic baseline search", "url": f"https://www.google.com/search?q={q}", "source": "fallback"},
        {"title": "General reference", "url": "https://en.wikipedia.org/wiki/International_relations", "source": "fallback"},
    ]


def _run(cmd: List[str], cwd: Path, timeout_sec: int = 30) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=max(5, int(timeout_sec)), check=False)
    return int(proc.returncode), str(proc.stdout or ""), str(proc.stderr or "")


def _web_search_references(*, topic: str, language: str, max_results: int) -> List[Dict[str, str]]:
    repo_root = Path(__file__).resolve().parents[3]
    adapter = repo_root / "agent" / "src" / "ppt_master_web_adapter.py"
    if not adapter.exists() or not _text(topic):
        return []
    cmd = [os.getenv("PYTHON", "python"), str(adapter), "search", "--query", _text(topic), "--num", str(max(1, min(int(max_results), 8))), "--language", "en-US" if language == "en-US" else "zh-CN"]
    try:
        code, stdout, _ = _run(cmd, adapter.parent, timeout_sec=30)
        if code != 0 or not stdout.strip():
            return []
        parsed = json.loads(stdout)
    except Exception:
        return []
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return []
    out: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"))
        url = _text(item.get("url"))
        if title and url.startswith(("http://", "https://")):
            out.append({"title": title, "url": url, "source": "web"})
        if len(out) >= max_results:
            break
    return out


def _prepare_pipeline_contract_inputs(req: PPTPipelineRequest, *, execution_profile: str) -> Dict[str, Any]:
    _ = execution_profile
    req.required_facts = _dedup(list(req.required_facts or []), limit=20)
    req.anchors = _dedup(list(req.anchors or []), limit=20)
    req.constraints = _dedup([*list(req.constraints or []), *[f"anchor_constraint:{a}" for a in req.anchors[:8]]], limit=20)
    return {"required_facts": req.required_facts, "anchors": req.anchors, "constraints": req.constraints}


def _resolve_quality_profile_id(quality_profile: str, *, topic: str = "", purpose: str = "", audience: str = "", total_pages: int = 10) -> str:
    raw = _text(quality_profile, "auto").lower().replace("-", "_")
    if raw and raw != "auto":
        return raw
    blob = " ".join([_text(topic), _text(purpose), _text(audience)]).lower()
    if any(k in blob for k in ("investor", "fundraising", "pitch")):
        return "investor_pitch"
    if any(k in blob for k in ("status", "weekly", "monthly", "briefing")):
        return "status_report"
    if any(k in blob for k in ("training", "onboarding", "classroom", "course")):
        return "training_deck"
    if any(k in blob for k in ("marketing", "launch", "brand", "campaign")):
        return "marketing_pitch"
    if any(k in blob for k in ("tech", "architecture", "review")):
        return "tech_review"
    if re.search(r"[\u4e00-\u9fff]", _text(purpose)):
        return "tech_review"
    if "ai" in blob and re.search(r"[\u4e00-\u9fff]", blob):
        return "investor_pitch"
    if int(total_pages or 10) >= 14:
        return "high_density_consulting"
    return "default"


def _pipeline_stage_timeout_sec(stage: str, default: int) -> int:
    raw = _text(os.getenv(f"PPT_PIPELINE_{_text(stage).upper()}_TIMEOUT_SEC"), "")
    if not raw:
        return int(default)
    try:
        return max(5, int(raw))
    except Exception:
        return int(default)


def _pipeline_export_timeout_sec(slide_count: int, route_mode: str) -> int:
    mode_bonus = {"fast": 0, "standard": 40, "refine": 80}.get(_text(route_mode).lower(), 40)
    raw = _text(os.getenv("PPT_PIPELINE_EXPORT_TIMEOUT_SEC"), "")
    try:
        forced = int(raw) if raw else 0
    except Exception:
        forced = 0
    computed = forced or (120 + max(1, int(slide_count)) * 8 + mode_bonus)
    return max(120, min(computed, 540))


def _normalize_retry_scope(value: Any) -> str:
    _ = value
    return "deck"


def _resolve_retry_budget(*, env_max_attempts: int, route_mode: str, route_policy_max: int) -> int:
    cap = {"fast": 1, "standard": 2, "refine": 3}.get(_text(route_mode, "standard").lower(), 2)
    return max(1, min(int(env_max_attempts), int(route_policy_max), int(cap)))


def _resolve_export_channel(value: str) -> str:
    env = _text(os.getenv("PPT_EXPORT_CHANNEL"), "local").lower()
    requested = _text(value, "auto").lower()
    if requested == "remote" or env == "remote":
        raise ValueError("remote channel is disabled")
    return "local"


def _page_type(slide_type: str) -> str:
    st = _text(slide_type, "content").lower()
    if st == "cover":
        return "cover"
    if st == "summary":
        return "closing"
    return "data_visualization"


def _position_to_card_id(position: str) -> str:
    pos = _text(position, "center").lower()
    return pos if pos in {"left", "right", "center", "top", "bottom"} else "center"


def _presentation_plan_to_render_payload(plan: PresentationPlan) -> Dict[str, Any]:
    slides: List[Dict[str, Any]] = []
    for slide in plan.slides:
        blocks = []
        for block in slide.blocks:
            row = block.model_dump()
            row["card_id"] = "title" if block.block_type == "title" else _position_to_card_id(block.position)
            blocks.append(row)
        title = _text(next((str(b.content) for b in slide.blocks if b.block_type == "title"), "Slide"))
        slides.append({"slide_id": f"slide-{slide.page_number}", "page_number": int(slide.page_number), "title": title, "slide_type": slide.slide_type, "page_type": _page_type(slide.slide_type), "subtype": _page_type(slide.slide_type), "layout_grid": slide.layout_grid, "bg_style": slide.bg_style, "blocks": blocks, "content_strategy": slide.content_strategy.model_dump() if slide.content_strategy else {}, "speaker_notes": _text(slide.notes_for_designer), "render_path": "svg", "load_skills": ["ppt-master", "pptx"], "agent_type": "ppt-master"})
    return {"title": plan.title, "theme": {"palette": "auto", "style": "soft"}, "style_variant": "soft", "palette_key": "auto", "theme_recipe": "auto", "tone": "auto", "svg_mode": "on", "skill_planning_runtime": {"enabled": True, "slides": [{"slide_id": str(s.get("slide_id") or ""), "skills": ["ppt-master", "pptx"]} for s in slides]}, "slides": slides}


def _apply_visual_orchestration(payload: Dict[str, Any]) -> Dict[str, Any]:
    return dict(payload or {})


def _ensure_content_contract(slides: List[Dict[str, Any]], *, profile: str = "default") -> List[Dict[str, Any]]:
    _ = profile
    out: List[Dict[str, Any]] = []
    for idx, slide in enumerate(slides or []):
        if not isinstance(slide, dict):
            continue
        row = dict(slide)
        title = _text(row.get("title"), f"Slide {idx + 1}")
        blocks = row.get("blocks") if isinstance(row.get("blocks"), list) else []
        has_title = any(isinstance(b, dict) and _text(b.get("block_type")).lower() == "title" for b in blocks)
        has_non_title = any(isinstance(b, dict) and _text(b.get("block_type")).lower() != "title" for b in blocks)
        if not has_title:
            blocks.insert(0, {"block_type": "title", "position": "top", "content": title, "card_id": "title"})
        if not has_non_title:
            blocks.append({"block_type": "body", "position": "left", "content": "Key point summary", "card_id": "left"})
        row["title"] = title
        row["blocks"] = blocks
        out.append(row)
    return out


async def _hydrate_image_assets(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    out.setdefault("image_asset_hydrated", False)
    return out


class PPTService:
    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[3]
        self.output_base = self.repo_root / "output" / "ppt_master_projects"
        self.output_base.mkdir(parents=True, exist_ok=True)
        self._render_jobs: Dict[str, Dict[str, Any]] = {}

    def _real_flow_enabled(self) -> bool:
        if not _env_flag("PPT_V2_REAL_FLOW_ENABLED", True):
            return False
        return _has_llm_credentials()

    @staticmethod
    def _fallback_outline(req: OutlineRequest) -> PresentationOutline:
        title = _shorten(_text(req.requirement, "Presentation"), 120)
        slides: List[SlideOutline] = []
        total = max(1, int(req.num_slides))
        for idx in range(total):
            stitle = title if idx == 0 else ("Summary" if idx == total - 1 else f"Section {idx}")
            slides.append(
                SlideOutline(
                    order=idx + 1,
                    title=stitle,
                    description=f"Focus: {stitle}",
                    key_points=[f"Key point {idx + 1}", "Context", "Action"],
                    suggested_elements=["text", "chart"],
                    estimated_duration=90,
                )
            )
        return PresentationOutline(
            title=title,
            theme="default",
            style=req.style,
            slides=slides,
            total_duration=sum(s.estimated_duration for s in slides),
        )

    @staticmethod
    def _fallback_content(req: ContentRequest) -> List[SlideContent]:
        out: List[SlideContent] = []
        for item in req.outline.slides:
            title = _text(item.title, f"Slide {item.order}")
            body = _text(item.description, "Key message")
            elements = [
                SlideElement(type="text", left=72, top=80, width=1136, height=90, content=title),
                SlideElement(type="text", left=96, top=210, width=1080, height=360, content=body),
            ]
            out.append(
                SlideContent(
                    outline_id=req.outline.id,
                    order=item.order,
                    title=title,
                    elements=elements,
                    background=SlideBackground(type="solid", color="#0B1220"),
                    narration=" ".join(item.key_points[:3]),
                    speaker_notes=body[:500],
                    duration=item.estimated_duration,
                )
            )
        return out

    async def _generate_outline_real(self, req: OutlineRequest) -> PresentationOutline:
        from src.openrouter_client import OpenRouterClient

        client = OpenRouterClient()
        model = _text(os.getenv("CONTENT_LLM_MODEL") or os.getenv("OPENAI_MODEL"), "openai/gpt-5.3-codex")
        prompt = f"""
你是一名资深企业咨询顾问，请根据需求生成 PPT 大纲。
要求页数：{int(req.num_slides)}
语言：{req.language}
风格：{req.style}
用途：{_text(req.purpose, "通用商务演示")}
需求：
{req.requirement}

只输出 JSON，不要输出任何额外解释。格式必须为：
{{
  "title": "演示标题",
  "theme": "default",
  "slides": [
    {{
      "order": 1,
      "title": "页面标题",
      "description": "页面说明",
      "key_points": ["要点1","要点2","要点3"],
      "suggested_elements": ["text","chart"],
      "estimated_duration": 90
    }}
  ]
}}
        """.strip()
        raw = await client.chat_completions(
            model=model,
            messages=[
                {"role": "system", "content": "You output strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        payload = _extract_json_payload(raw)
        rows = payload.get("slides") if isinstance(payload.get("slides"), list) else []
        slides: List[SlideOutline] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            order = idx + 1
            title = _shorten(_text(row.get("title"), f"Slide {order}"), 200)
            description = _shorten(_text(row.get("description"), ""), 800)
            key_points = _list_of_text(row.get("key_points"), limit=7) or [f"{title} 核心信息", "关键事实", "行动建议"]
            suggested_elements = _normalize_suggested_elements(row.get("suggested_elements"))
            duration_raw = row.get("estimated_duration")
            try:
                duration = int(duration_raw)
            except Exception:
                duration = 90
            duration = max(60, min(duration, 180))
            slides.append(
                SlideOutline(
                    order=order,
                    title=title,
                    description=description,
                    key_points=key_points,
                    suggested_elements=suggested_elements,
                    estimated_duration=duration,
                )
            )
            if len(slides) >= int(req.num_slides):
                break
        while len(slides) < int(req.num_slides):
            order = len(slides) + 1
            label = "Summary" if order == int(req.num_slides) else f"Section {order - 1}"
            slides.append(
                SlideOutline(
                    order=order,
                    title=label,
                    description=f"Focus: {label}",
                    key_points=[f"{label} 关键结论", "证据支撑", "下一步行动"],
                    suggested_elements=["text", "chart"],
                    estimated_duration=90,
                )
            )
        title = _shorten(_text(payload.get("title"), _text(req.requirement, "Presentation")), 120)
        return PresentationOutline(
            title=title,
            theme=_text(payload.get("theme"), "default"),
            style=req.style,
            slides=slides,
            total_duration=sum(item.estimated_duration for item in slides),
        )

    async def _generate_content_real(self, req: ContentRequest) -> List[SlideContent]:
        from src.openrouter_client import OpenRouterClient

        client = OpenRouterClient()
        model = _text(os.getenv("CONTENT_LLM_MODEL") or os.getenv("OPENAI_MODEL"), "openai/gpt-5.3-codex")
        out: List[SlideContent] = []
        for item in req.outline.slides:
            prompt = f"""
你是一名专业演示文稿写作专家，请为单页PPT生成可直接上屏的文案。
语言：{req.language}
页码：{int(item.order)}
页面标题：{item.title}
页面说明：{item.description}
关键要点：{json.dumps(list(item.key_points or []), ensure_ascii=False)}

只输出 JSON，不要输出其他文字。格式必须是：
{{
  "title": "页面标题",
  "bullet_points": ["要点1","要点2","要点3"],
  "summary": "页面高亮总结（可空）",
  "speaker_notes": "100-220字讲解词"
}}
            """.strip()
            row: Dict[str, Any] = {}
            try:
                raw = await client.chat_completions(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You output strict JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.35,
                    max_tokens=1400,
                )
                row = _extract_json_payload(raw)
            except Exception as exc:
                logger.warning("single-slide content generation failed on slide %s: %s", item.order, exc)
                row = {}
            title = _shorten(_text(row.get("title"), _text(item.title, f"Slide {item.order}")), 260)
            bullets = _list_of_text(row.get("bullet_points"), limit=6) or _list_of_text(item.key_points, limit=6)
            if not bullets:
                bullets = [f"{title} 关键信息", "证据与数据", "行动建议"]
            summary = _shorten(_text(row.get("summary"), ""), 120)
            notes = _shorten(_text(row.get("speaker_notes"), "；".join(bullets)), 900)
            elements = _build_content_elements(title=title, bullets=bullets, summary=summary)
            out.append(
                SlideContent(
                    outline_id=req.outline.id,
                    order=item.order,
                    title=title,
                    elements=elements,
                    background=SlideBackground(type="solid", color="#F8FAFC"),
                    narration=notes,
                    speaker_notes=notes,
                    duration=max(60, min(int(item.estimated_duration), 180)),
                )
            )
        return out

    async def generate_outline(self, req: OutlineRequest) -> PresentationOutline:
        if not self._real_flow_enabled():
            return self._fallback_outline(req)
        try:
            return await self._generate_outline_real(req)
        except Exception as exc:
            logger.warning("generate_outline real flow failed, fallback to deterministic outline: %s", exc)
            return self._fallback_outline(req)

    async def generate_content(self, req: ContentRequest) -> List[SlideContent]:
        if not self._real_flow_enabled():
            return self._fallback_content(req)
        try:
            return await self._generate_content_real(req)
        except Exception as exc:
            logger.warning("generate_content real flow failed, fallback to deterministic content: %s", exc)
            return self._fallback_content(req)

    async def parse_document(self, file_url: str, file_type: str) -> ParsedDocument:
        from src.document_parser import parse_document as parse_uploaded_document

        source_url = _text(file_url)
        normalized_type = _text(file_type, "pptx").lower()
        if normalized_type not in {"pptx", "ppt", "pdf"}:
            normalized_type = "pptx"
        return await parse_uploaded_document(source_url, normalized_type)

    async def enhance_slides(self, *, slides: List[SlideContent], language: str, enhance_narration: bool, generate_tts: bool, voice_style: str) -> List[SlideContent]:
        _ = language, enhance_narration, generate_tts, voice_style
        return slides

    async def _read_binary_source(self, source: str) -> bytes:
        ref = _text(source)
        if not ref:
            raise ValueError("empty media source")

        if ref.startswith("http://") or ref.startswith("https://"):
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.get(ref)
                response.raise_for_status()
                return bytes(response.content)

        local_path = ref
        if ref.startswith("file://"):
            parsed = urlparse(ref)
            local_path = unquote(parsed.path or "")
            if local_path.startswith("/") and len(local_path) >= 3 and local_path[2] == ":":
                local_path = local_path.lstrip("/")
        path = Path(local_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"source not found: {ref}")
        return path.read_bytes()

    async def _estimate_audio_duration_secs(self, source: str, fallback: float) -> float:
        ref = _text(source)
        if not ref:
            return max(2.0, float(fallback))
        try:
            from src.tts_synthesizer import _get_audio_duration

            audio_bytes = await self._read_binary_source(ref)
            duration = float(await _get_audio_duration(audio_bytes))
            if duration > 0:
                return max(2.0, duration + 0.4)
        except Exception as exc:
            logger.warning("estimate audio duration failed (%s): %s", ref, exc)
        return max(2.0, float(fallback))

    async def _build_video_slides_from_pptx(
        self,
        *,
        pptx_url: str,
        audio_urls: List[str],
        default_duration: float,
    ) -> List[Dict[str, Any]]:
        from src.pptx_rasterizer import rasterize_pptx_bytes_to_png_bytes
        from src.r2 import upload_bytes_to_r2

        pptx_bytes = await self._read_binary_source(pptx_url)
        png_bytes_list = await asyncio.to_thread(rasterize_pptx_bytes_to_png_bytes, pptx_bytes)
        if not png_bytes_list:
            raise RuntimeError("pptx_rasterization_failed")

        run_id = uuid.uuid4().hex[:12]
        slides: List[Dict[str, Any]] = []
        for idx, png_bytes in enumerate(png_bytes_list):
            image_url = await upload_bytes_to_r2(
                png_bytes,
                key=f"projects/ppt-render/{run_id}/slides/slide_{idx + 1:03d}.png",
                content_type="image/png",
            )
            duration = max(2.0, float(default_duration))
            item: Dict[str, Any] = {"imageUrl": image_url, "duration": duration}
            if idx < len(audio_urls):
                audio_url = _text(audio_urls[idx])
                if audio_url:
                    item["audioUrl"] = audio_url
                    item["duration"] = await self._estimate_audio_duration_secs(
                        audio_url, duration
                    )
            slides.append(item)
        return slides

    async def start_video_render(
        self,
        slides: List[Dict[str, Any]],
        config: VideoRenderConfig,
        *,
        pptx_url: Optional[str] = None,
        audio_urls: Optional[List[str]] = None,
    ) -> RenderJob:
        from src.lambda_renderer import start_render

        normalized_slides = [dict(item) for item in (slides or []) if isinstance(item, dict)]
        source_type = "slides"
        if _text(pptx_url):
            source_type = "pptx"
            normalized_slides = await self._build_video_slides_from_pptx(
                pptx_url=_text(pptx_url),
                audio_urls=[_text(item) for item in (audio_urls or []) if _text(item)],
                default_duration=6.0,
            )
        if not normalized_slides:
            raise RuntimeError("video_render_requires_valid_media_slides")

        render_config = (
            config.model_dump(mode="json")
            if hasattr(config, "model_dump")
            else dict(config or {})
        )
        prefer_local = _env_flag("PPT_RENDER_PREFER_LOCAL", True)
        started_at = _utc_now()
        result = await start_render(
            normalized_slides,
            render_config,
            prefer_local=prefer_local,
        )
        job_id = _text(result.get("render_id"), f"render_{_new_id()}")
        output_url = _text(result.get("video_url"))
        status = "done" if output_url else "rendering"

        job = RenderJob(
            id=job_id,
            project_id="",
            status=status,
            progress=1.0 if status == "done" else 0.1,
            lambda_job_id=job_id,
            output_url=output_url or None,
            error=None,
            created_at=started_at,
            updated_at=_utc_now(),
        )
        self._render_jobs[job_id] = {
            **job.model_dump(mode="json"),
            "mode": _text(result.get("mode"), "local"),
            "cost": float(result.get("cost") or 0.0),
            "source_type": source_type,
            "slides_count": len(normalized_slides),
        }
        return job

    async def get_render_status(self, job_id: str) -> Dict[str, Any]:
        from src.lambda_renderer import get_render_progress

        key = _text(job_id)
        if not key:
            return {"status": "not_found"}
        cached = dict(self._render_jobs.get(key) or {})
        if cached.get("status") in {"done", "failed"}:
            return cached

        progress = await get_render_progress(key)
        raw_status = _text(progress.get("status"), "unknown").lower()
        output_url = _text(progress.get("output_url")) or _text(cached.get("output_url"))

        if raw_status in {"done", "completed", "succeeded", "success"}:
            status = "done"
            progress_value = 1.0
        elif raw_status in {"failed", "error", "invalid"}:
            status = "failed"
            progress_value = float(progress.get("progress") or cached.get("progress") or 0.0)
        elif raw_status in {"unknown", "not_found"} and not cached:
            return {"status": "not_found"}
        else:
            status = "rendering"
            progress_value = float(progress.get("progress") or cached.get("progress") or 0.1)

        merged = {
            **cached,
            "id": key,
            "lambda_job_id": _text(cached.get("lambda_job_id"), key),
            "status": status,
            "progress": max(0.0, min(1.0, progress_value)),
            "output_url": output_url or None,
            "error": _text(progress.get("error")) or _text(cached.get("error")) or None,
            "updated_at": _utc_now(),
        }
        if not merged.get("created_at"):
            merged["created_at"] = _utc_now()
        self._render_jobs[key] = merged
        return merged

    async def get_download_url(self, job_id: str) -> Dict[str, Any]:
        status = await self.get_render_status(job_id)
        if status.get("status") == "not_found":
            raise LookupError("job not found")
        output_url = _text(status.get("output_url"))
        if not output_url:
            raise RuntimeError("render output not ready")
        return {"job_id": _text(job_id), "output_url": output_url}

    async def generate_research_context(self, req: ResearchRequest) -> ResearchContext:
        topic = _text(req.topic)
        language = req.language if req.language in {"zh-CN", "en-US"} else "zh-CN"
        key_points = _build_key_points(topic, language=language, limit=8)
        references: List[Dict[str, str]] = []
        strategy = "none"
        if bool(req.web_enrichment):
            references = _web_search_references(topic=topic, language=language, max_results=max(1, min(int(req.max_search_results), 8)))
            strategy = "web" if references else "web+fallback"
        if not references:
            references = _fallback_references(topic)
        evidence = [ResearchEvidence(claim=point, source_title=_text(ref.get("title"), "Reference"), source_url=_text(ref.get("url"), "https://example.com"), snippet=point, confidence=0.62, provenance="web" if ref.get("source") == "web" else "fallback", tags=[_shorten(point, 40)]) for point, ref in ((key_points[i], references[min(i, len(references) - 1)]) for i in range(min(len(key_points), 8)))]
        questions = [ResearchQuestion(question="Who is the primary audience for this deck?", category="audience", why="Audience level determines depth and vocabulary."), ResearchQuestion(question="What is the decision objective of this presentation?", category="purpose", why="Decision objective controls storyline and slide weighting."), ResearchQuestion(question="Which evidence should be treated as must-have?", category="data", why="Must-have facts define chart and citation priorities.")]
        gaps: List[ResearchGap] = []
        if not _text(req.audience):
            gaps.append(ResearchGap(code="audience", severity="medium", message="Audience details are generic.", query_hint="audience segmentation"))
        completeness = 0.72 if references else 0.55
        return ResearchContext(topic=topic, language=language, audience=_text(req.audience, "general"), purpose=_text(req.purpose, "presentation"), style_preference=_text(req.style_preference, "professional"), constraints=_dedup(req.constraints or [], limit=20), required_facts=_dedup(req.required_facts or [], limit=20), geography=_text(req.geography), time_range=_text(req.time_range), domain_terms=_dedup(req.domain_terms or [], limit=20), key_data_points=key_points[: max(3, min(12, len(key_points)))], reference_materials=references, evidence=evidence, gap_report=gaps, completeness_score=max(float(req.min_completeness), completeness), enrichment_applied=bool(req.web_enrichment), enrichment_strategy=(strategy if strategy in {"none", "web", "web+fallback"} else "none"), questions=questions)

    async def generate_outline_plan(self, req: OutlinePlanRequest) -> OutlinePlan:
        research = req.research
        pages = max(3, min(50, int(req.total_pages)))
        points = _dedup(research.key_data_points or _build_key_points(research.topic, language=research.language), limit=24)
        if not points:
            points = ["Background", "Mechanism", "Implications", "Risks"]
        notes: List[StickyNote] = [StickyNote(page_number=1, core_message=_shorten(_text(research.topic, "Topic"), 30), layout_hint="cover", content_density="low", data_elements=[], visual_anchor="title", key_points=points[:3] if len(points) >= 3 else ["Context", "Scope", "Goal"], speaker_notes=_shorten("Opening and framing", 200))]
        prev_layout: LayoutType = "cover"
        for page in range(2, pages):
            layout = _ALLOWED_LAYOUTS[(page - 2) % len(_ALLOWED_LAYOUTS)]
            if layout == prev_layout:
                layout = _ALLOWED_LAYOUTS[(page - 1) % len(_ALLOWED_LAYOUTS)]
            prev_layout = layout
            p = points[(page - 2) % len(points)]
            kp = [p, points[(page - 1) % len(points)], points[page % len(points)]]
            notes.append(StickyNote(page_number=page, core_message=_shorten(p, 30), layout_hint=layout, content_density="medium", data_elements=["timeline", "evidence"], visual_anchor="evidence", key_points=_dedup(kp, limit=7)[:3], speaker_notes=_shorten(f"Explain {p}", 200)))
        notes.append(StickyNote(page_number=pages, core_message="Summary and actions", layout_hint="summary", content_density="low", data_elements=["summary"], visual_anchor="summary", key_points=_dedup(["Key findings", "Risks", "Next actions"], limit=7), speaker_notes="Close with actions and open questions"))
        notes = notes[:pages]
        if notes[-1].layout_hint != "summary":
            notes[-1] = StickyNote(page_number=pages, core_message="Summary and actions", layout_hint="summary", key_points=["Key findings", "Risks", "Next actions"], speaker_notes="Close with actions and open questions")
        return OutlinePlan(title=_text(research.topic, "Presentation"), total_pages=pages, theme_suggestion="slate_minimal", style_suggestion="soft", notes=notes, logic_flow="Context -> mechanism -> impact -> risks -> actions")

    async def generate_presentation_plan(self, req: PresentationPlanRequest) -> PresentationPlan:
        slides: List[SlidePlan] = []
        for note in req.outline.notes:
            slide_type = "cover" if note.layout_hint == "cover" else ("summary" if note.layout_hint == "summary" else "content")
            core_title = _text(note.core_message, "Title")
            points = _dedup(note.key_points or [], limit=6)
            while len(points) < 4:
                points.append(f"Supporting point {len(points) + 1}")
            blocks = [
                ContentBlock(block_type="title", position="top", content=core_title),
                ContentBlock(block_type="subtitle", position="center", content=_text(note.visual_anchor, "Core message")),
                ContentBlock(block_type="list", position="left", content="; ".join(points[:4])),
                ContentBlock(block_type="body", position="right", content="; ".join(points[1:4])),
            ]
            strategy = SlideContentStrategy(assertion=_text(note.core_message, "Assertion"), evidence=_dedup(note.key_points, limit=6), data_anchor=_text(note.visual_anchor, "evidence"), page_role="summary" if slide_type == "summary" else "argument", density_hint="breathing" if slide_type in {"cover", "summary"} else "medium", render_path="svg")
            slides.append(SlidePlan(page_number=note.page_number, slide_type=slide_type, layout_grid=note.layout_hint, blocks=blocks, bg_style="light", archetype="ppt_master_runtime", template_candidates=[], notes_for_designer=_text(note.speaker_notes, ""), content_strategy=strategy))
        return PresentationPlan(title=req.outline.title, theme=req.outline.theme_suggestion, style=req.outline.style_suggestion, slides=slides, global_notes=req.outline.logic_flow)

    async def run_ppt_pipeline(self, req: PPTPipelineRequest) -> PPTPipelineResult:
        from src.ppt_quality_gate import validate_deck

        run_id = _new_id()
        stages: List[PPTPipelineStageStatus] = []

        def _push(stage: str, ok: bool, started_at: str, diagnostics: Optional[List[str]] = None) -> None:
            stages.append(PPTPipelineStageStatus(stage=stage, ok=bool(ok), started_at=started_at, finished_at=_utc_now(), diagnostics=list(diagnostics or [])))

        _prepare_pipeline_contract_inputs(req, execution_profile=_text(req.execution_profile, "auto"))

        t = _utc_now()
        research_req = ResearchRequest(topic=req.topic, language=req.language, audience=req.audience, purpose=req.purpose, style_preference=req.style_preference, constraints=list(req.constraints or []), required_facts=list(req.required_facts or []), geography=req.geography, time_range=req.time_range, domain_terms=list(req.domain_terms or []), web_enrichment=bool(req.web_enrichment), min_completeness=float(req.research_min_completeness), desired_citations=int(req.desired_citations), max_web_queries=int(req.max_web_queries), max_search_results=int(req.max_search_results))
        try:
            research = await asyncio.wait_for(self.generate_research_context(research_req), timeout=float(_pipeline_stage_timeout_sec("research", 120)))
        except asyncio.TimeoutError as exc:
            _push("research", False, t, ["timeout"])
            raise ValueError("Research stage timeout") from exc
        _push("research", True, t, [f"references={len(research.reference_materials)}"])

        t = _utc_now()
        try:
            outline_plan = await asyncio.wait_for(self.generate_outline_plan(OutlinePlanRequest(research=research, total_pages=req.total_pages)), timeout=float(_pipeline_stage_timeout_sec("outline", 120)))
        except asyncio.TimeoutError as exc:
            _push("outline_plan", False, t, ["timeout"])
            raise ValueError("Outline stage timeout") from exc
        _push("outline_plan", True, t, [f"pages={outline_plan.total_pages}"])

        t = _utc_now()
        try:
            presentation_plan = await asyncio.wait_for(self.generate_presentation_plan(PresentationPlanRequest(outline=outline_plan, research=research)), timeout=float(_pipeline_stage_timeout_sec("presentation", 180)))
        except asyncio.TimeoutError as exc:
            _push("presentation_plan", False, t, ["timeout"])
            raise ValueError("Presentation-plan stage timeout") from exc
        _push("presentation_plan", True, t, [f"slides={len(presentation_plan.slides)}"])

        t = _utc_now()
        render_payload = _presentation_plan_to_render_payload(presentation_plan)
        render_payload.update({"topic": req.topic, "audience": req.audience, "purpose": req.purpose, "style_preference": req.style_preference, "style_variant": _text(req.minimax_style_variant, "auto"), "palette_key": _text(req.minimax_palette_key, "auto"), "theme_recipe": _text(req.theme_recipe, "auto"), "tone": _text(req.tone, "auto"), "template_family": _text(req.template_family, "auto"), "skill_profile": _text(req.skill_profile, "auto"), "quality_profile": _resolve_quality_profile_id(req.quality_profile, topic=req.topic, purpose=req.purpose, audience=req.audience, total_pages=req.total_pages)})
        render_payload = _apply_visual_orchestration(render_payload)
        slides = _ensure_content_contract(list(render_payload.get("slides") or []), profile=render_payload["quality_profile"])
        render_payload["slides"] = slides
        if bool(req.image_asset_enrichment):
            render_payload = await _hydrate_image_assets(render_payload)
        quality_result = validate_deck(slides, profile=render_payload["quality_profile"])
        if not bool(getattr(quality_result, "ok", False)):
            _push("quality_gate", False, t, [f"issues={len(getattr(quality_result, 'issues', []) or [])}"])
            raise ValueError("Quality gate failed")
        if len(slides) < 3:
            _push("quality_gate", False, t, ["insufficient_slides"])
            raise ValueError("Quality gate failed")
        _push("quality_gate", True, t, [f"slides={len(slides)}"])

        t = _utc_now()
        export_data: Optional[Dict[str, Any]] = None
        if bool(req.with_export):
            timeout = _pipeline_export_timeout_sec(len(slides), _text(req.route_mode, "standard"))
            channel = _resolve_export_channel(_text(req.export_channel, "local"))
            try:
                export_data = await asyncio.wait_for(asyncio.to_thread(export_minimax_pptx, slides=slides, title=_text(req.title, presentation_plan.title), author=_text(req.author, "AutoViralVid"), style_variant=_text(req.minimax_style_variant, "auto"), palette_key=_text(req.minimax_palette_key, "auto"), theme_recipe=_text(req.theme_recipe, "auto"), tone=_text(req.tone, "auto"), route_mode=_text(req.route_mode, "standard"), render_channel=channel, generator_mode="official", template_family=_text(req.template_family, "auto"), skill_profile=_text(req.skill_profile, "auto"), quality_profile=_text(render_payload.get("quality_profile"), "default"), timeout=timeout), timeout=float(timeout + 30))
            except asyncio.TimeoutError as exc:
                _push("export", False, t, ["timeout"])
                raise ValueError("Export stage timeout") from exc
            export_data = dict(export_data or {})
            pptx_bytes = export_data.pop("pptx_bytes", None)
            run_dir = self.output_base / f"pipeline_{run_id}"
            run_dir.mkdir(parents=True, exist_ok=True)
            if isinstance(pptx_bytes, (bytes, bytearray)):
                output_pptx = run_dir / f"{run_id}.pptx"
                output_pptx.write_bytes(bytes(pptx_bytes))
                export_data["output_pptx"] = str(output_pptx)
            export_data.setdefault("slide_image_urls", [])
            _push("export", True, t, [f"channel={channel}"])
        else:
            _push("export", True, t, ["skipped by request"])

        if bool(req.save_artifacts):
            run_dir = self.output_base / f"pipeline_{run_id}"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "research.json").write_text(research.model_dump_json(indent=2), encoding="utf-8")
            (run_dir / "outline_plan.json").write_text(outline_plan.model_dump_json(indent=2), encoding="utf-8")
            (run_dir / "presentation_plan.json").write_text(presentation_plan.model_dump_json(indent=2), encoding="utf-8")
            (run_dir / "render_payload.json").write_text(json.dumps(render_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            if isinstance(export_data, dict):
                (run_dir / "export.json").write_text(json.dumps(export_data, ensure_ascii=False, indent=2), encoding="utf-8")

        return PPTPipelineResult(run_id=run_id, stages=stages, artifacts=PPTPipelineArtifacts(research=research, outline_plan=outline_plan, presentation_plan=presentation_plan, render_payload=render_payload), export=export_data)

    async def export_pptx(self, req: ExportRequest) -> Dict[str, Any]:
        slides = [s.model_dump() for s in req.slides]
        timeout = _pipeline_export_timeout_sec(len(slides), _text(req.route_mode, "standard"))
        channel = _resolve_export_channel(_text(req.export_channel, "local"))
        result = await asyncio.to_thread(export_minimax_pptx, slides=slides, title=_text(req.title, "Presentation"), author=_text(req.author, "AutoViralVid"), style_variant=_text(req.minimax_style_variant, "auto"), palette_key=_text(req.minimax_palette_key, "auto"), theme_recipe=_text(req.theme_recipe, "auto"), tone=_text(req.tone, "auto"), route_mode=_text(req.route_mode, "standard"), render_channel=channel, generator_mode=_text(req.generator_mode, "official"), template_family=_text(req.template_family, "auto"), skill_profile=_text(req.skill_profile, "auto"), quality_profile=_text(req.quality_profile, "auto"), timeout=timeout)
        out = dict(result or {})
        pptx_bytes = out.pop("pptx_bytes", None)
        run_dir = self.output_base / f"export_{_new_id()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(pptx_bytes, (bytes, bytearray)):
            output_pptx = run_dir / "presentation.pptx"
            output_pptx.write_bytes(bytes(pptx_bytes))
            out["output_pptx"] = str(output_pptx)
        return out


__all__ = [
    "PPTService",
    "_apply_visual_orchestration",
    "_ensure_content_contract",
    "_hydrate_image_assets",
    "_normalize_retry_scope",
    "_pipeline_export_timeout_sec",
    "_pipeline_stage_timeout_sec",
    "_prepare_pipeline_contract_inputs",
    "_presentation_plan_to_render_payload",
    "_resolve_export_channel",
    "_resolve_quality_profile_id",
    "_resolve_retry_budget",
]
