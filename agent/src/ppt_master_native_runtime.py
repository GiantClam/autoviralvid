"""Native ppt-master-like runtime (file-contract based, no JSON intermediary).

This runtime keeps orchestration aligned with ppt-master's serial workflow:
source -> template -> strategist -> executor -> postprocess -> export.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.llm_client import get_llm_client


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def _normalize_language(value: Any) -> str:
    text = _text(value, "").lower()
    if text.startswith("zh"):
        return "zh-CN"
    if text.startswith("en"):
        return "en-US"
    return "zh-CN"


def _env_int(name: str, default: int) -> int:
    raw = _text(os.getenv(name), "")
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _run_cmd(
    *,
    cmd: Sequence[str],
    cwd: Path,
    timeout_sec: int,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            list(cmd),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(10, int(timeout_sec)),
            check=False,
            env=env or dict(os.environ),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"timeout:{Path(cmd[1]).name if len(cmd) > 1 else cmd[0]}") from exc
    return int(proc.returncode), str(proc.stdout or ""), str(proc.stderr or "")


def _safe_slug(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", _text(text, fallback))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:80] if cleaned else fallback


def _load_layout_catalog(layouts_index_path: Path) -> Dict[str, Dict[str, str]]:
    if not layouts_index_path.exists():
        return {}
    try:
        payload = json.loads(layouts_index_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    layouts = payload.get("layouts") if isinstance(payload, dict) else {}
    if not isinstance(layouts, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for key, row in layouts.items():
        template_id = _text(key, "").strip()
        if not template_id:
            continue
        info = row if isinstance(row, dict) else {}
        out[template_id] = {
            "summary": _text(info.get("summary"), ""),
            "tone": _text(info.get("tone"), ""),
            "keywords": ", ".join(str(item) for item in (info.get("keywords") or []) if _text(item, "")),
        }
    return out


def _choose_template_family(
    *,
    prompt: str,
    style: str,
    language: str,
    template_family: str,
    layouts_dir: Path,
    layouts_index_path: Path,
    timeout_sec: int,
) -> str:
    explicit = _text(template_family, "").strip()
    if explicit and explicit.lower() != "auto":
        return explicit

    layout_catalog = _load_layout_catalog(layouts_index_path)
    candidates = sorted(
        name
        for name in layout_catalog.keys()
        if (layouts_dir / name).exists()
    )
    if not candidates:
        fallback = "mckinsey"
        return fallback if (layouts_dir / fallback).exists() else ""

    prompt_lines = []
    for template_id in candidates:
        row = layout_catalog.get(template_id, {})
        prompt_lines.append(
            f"- {template_id}: {row.get('summary','')} | {row.get('tone','')} | {row.get('keywords','')}"
        )
    chooser_messages = [
        {
            "role": "system",
            "content": (
                "You are selecting one ppt-master layout template.\n"
                "Return only one template id from the allowed list, no explanation."
            ),
        },
        {
            "role": "user",
            "content": (
                f"User prompt: {prompt}\n"
                f"Language: {language}\n"
                f"Requested style: {style}\n"
                "Allowed template ids and descriptions:\n"
                + "\n".join(prompt_lines)
            )[:120000],
        },
    ]
    try:
        raw_selected = _call_chat_text(
            messages=chooser_messages,
            max_tokens=80,
            timeout_sec=max(20, min(timeout_sec, 120)),
            temperature=0.0,
        )
    except Exception:
        raw_selected = ""
    selected_line = ""
    for line in _text(raw_selected, "").splitlines():
        normalized = line.strip()
        if normalized:
            selected_line = normalized
            break
    selected_tokens = selected_line.strip("` ").split()[:1]
    selected_id = selected_tokens[0] if selected_tokens else ""
    if selected_id in candidates:
        return selected_id

    # Fallback by style semantics.
    if "academic" in _text(style, "").lower() and "academic_defense" in candidates:
        return "academic_defense"
    if "consult" in _text(style, "").lower() and "mckinsey" in candidates:
        return "mckinsey"
    # Prefer mckinsey as stable default when available.
    if "mckinsey" in candidates:
        return "mckinsey"
    return candidates[0]


def _strip_code_fence(text: str, lang: str) -> str:
    pattern = re.compile(rf"```{re.escape(lang)}\s*(.*?)```", re.IGNORECASE | re.DOTALL)
    match = pattern.search(text)
    if match:
        return _text(match.group(1), "")
    return ""


def _parse_executor_output(raw_text: str) -> Tuple[str, str]:
    svg_block = _strip_code_fence(raw_text, "svg")
    notes_block = _strip_code_fence(raw_text, "notes")
    if not svg_block:
        match = re.search(r"(?is)<svg\b.*?</svg>", raw_text or "")
        svg_block = _text(match.group(0), "") if match else ""

    if not notes_block:
        # If notes fence absent, use text after the first svg block.
        if svg_block:
            idx = raw_text.find(svg_block)
            if idx >= 0:
                notes_block = _text(raw_text[idx + len(svg_block) :], "")
        notes_block = re.sub(r"(?is)</?svg[^>]*>", "", notes_block).strip()
        notes_block = re.sub(r"^```.*?```$", "", notes_block, flags=re.DOTALL).strip()

    return _text(svg_block, ""), _text(notes_block, "")


def _sanitize_svg_markup(svg_markup: str) -> str:
    text = _text(svg_markup, "")
    if not text:
        return ""
    # Remove illegal XML control chars.
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
    # Escape unescaped ampersands.
    text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)", "&amp;", text)
    return text


def _extract_svg_document(svg_markup: str) -> str:
    text = _text(svg_markup, "")
    if not text:
        return ""
    start = re.search(r"(?is)<svg\b", text)
    if not start:
        return ""
    candidate = text[start.start() :]
    end = re.search(r"(?is)</svg\s*>", candidate)
    if end:
        candidate = candidate[: end.end()]
    else:
        candidate = candidate.rstrip() + "\n</svg>"
    return _text(candidate, "")


def _is_valid_xml(xml_markup: str) -> bool:
    xml_text = _text(xml_markup, "")
    if not xml_text:
        return False
    try:
        ET.fromstring(xml_text)
        return True
    except Exception:
        return False


def _repair_svg_xml_with_llm(
    *,
    invalid_svg: str,
    page_no: int,
    timeout_sec: int,
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an XML repair engine.\n"
                "Fix malformed SVG XML and return ONLY one complete valid <svg>...</svg> document.\n"
                "Do not use markdown fences.\n"
                "Do not explain anything."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Page: {page_no}\n"
                "Repair this SVG so it becomes valid XML while preserving original visual intent:\n\n"
                f"{_text(invalid_svg, '')[:120000]}"
            ),
        },
    ]
    repaired_raw = _call_chat_text(
        messages=messages,
        max_tokens=12000,
        timeout_sec=max(30, min(timeout_sec, 600)),
        temperature=0.0,
    )
    # Some models may still wrap inside fences.
    fenced = _strip_code_fence(repaired_raw, "svg")
    candidate = fenced or repaired_raw
    candidate = _extract_svg_document(candidate)
    return _sanitize_svg_markup(candidate)


def _build_strategist_confirmations(
    *,
    strategist_doc: str,
    prompt: str,
    language: str,
    total_pages: int,
    style: str,
    selected_template: str,
    source_md_text: str,
    template_design_spec_text: str,
    research_items: List[Dict[str, str]],
    timeout_sec: int,
) -> str:
    max_tokens = max(2000, min(8000, _env_int("PPT_MASTER_STRATEGIST_CONFIRM_MAX_TOKENS", 4500)))
    source_limit = max(8000, min(120000, _env_int("PPT_MASTER_STRATEGIST_SOURCE_CHARS", 30000)))
    template_limit = max(5000, min(60000, _env_int("PPT_MASTER_STRATEGIST_TEMPLATE_CHARS", 20000)))
    messages = [
        {
            "role": "system",
            "content": (
                strategist_doc
                + "\n\nTask: Output only the bundled Eight Confirmations recommendation package in markdown."
                + "\nDo not output final design_spec.md in this step."
            )[:220000],
        },
        {
            "role": "user",
            "content": (
                f"Topic: {prompt}\n"
                f"Language for deck content values: {language}\n"
                f"Total pages target: {total_pages}\n"
                f"Style: {style}\n"
                f"Template: {selected_template}\n"
                f"Source markdown:\n{source_md_text[:source_limit]}\n\n"
                f"Template design spec example:\n{template_design_spec_text[:template_limit]}\n\n"
                f"Research evidence JSON: {json.dumps(research_items, ensure_ascii=False)}\n"
                "Provide concise recommendations for the eight confirmations only."
            ),
        },
    ]
    return _call_chat_text(
        messages=messages,
        max_tokens=max_tokens,
        timeout_sec=max(60, min(timeout_sec, 900)),
        temperature=0.0,
    )


def _build_strategist_design_spec(
    *,
    strategist_doc: str,
    design_spec_ref: str,
    prompt: str,
    language: str,
    total_pages: int,
    style: str,
    selected_template: str,
    source_md_text: str,
    template_design_spec_text: str,
    research_items: List[Dict[str, str]],
    confirmations_text: str,
    timeout_sec: int,
) -> str:
    max_tokens = max(3000, min(14000, _env_int("PPT_MASTER_STRATEGIST_DESIGNSPEC_MAX_TOKENS", 9000)))
    source_limit = max(8000, min(120000, _env_int("PPT_MASTER_STRATEGIST_SOURCE_CHARS", 30000)))
    template_limit = max(5000, min(60000, _env_int("PPT_MASTER_STRATEGIST_TEMPLATE_CHARS", 20000)))
    confirmations_limit = max(6000, min(50000, _env_int("PPT_MASTER_STRATEGIST_CONFIRMATIONS_CHARS", 20000)))
    messages = [
        {
            "role": "system",
            "content": (
                strategist_doc
                + "\n\n"
                + design_spec_ref
                + "\n\nTask: User has confirmed the Eight Confirmations package."
                + "\nGenerate final design_spec.md only. Do not ask follow-up questions."
            )[:220000],
        },
        {
            "role": "user",
            "content": (
                f"Topic: {prompt}\n"
                f"Language for deck content values: {language}\n"
                f"Total pages target: {total_pages}\n"
                f"Style: {style}\n"
                f"Template: {selected_template}\n"
                f"Source markdown:\n{source_md_text[:source_limit]}\n\n"
                f"Template design spec example:\n{template_design_spec_text[:template_limit]}\n\n"
                f"Research evidence JSON: {json.dumps(research_items, ensure_ascii=False)}\n"
                f"Confirmed Eight Confirmations package:\n{confirmations_text[:confirmations_limit]}\n\n"
                "Auto-confirmation: approved as-is. Produce the final complete design_spec.md now."
            ),
        },
    ]
    return _call_chat_text(
        messages=messages,
        max_tokens=max_tokens,
        timeout_sec=max(60, min(timeout_sec, 1200)),
        temperature=0.0,
    )


async def _chat_text(
    *,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float,
    model_override: Optional[str] = None,
) -> str:
    client = get_llm_client()
    old_model = getattr(client, "model", "")
    use_model = _text(model_override, "")
    if use_model:
        try:
            client.model = use_model
        except Exception:
            pass
    try:
        response = await client.chat_completion(
            messages=messages,
            temperature=float(temperature),
            max_tokens=max_tokens,
        )
    finally:
        if use_model and old_model:
            try:
                client.model = old_model
            except Exception:
                pass
    return _text(response.get("content"), "")


def _call_chat_text(
    *,
    messages: List[Dict[str, str]],
    max_tokens: int,
    timeout_sec: int,
    temperature: float = 0.0,
    model_override: Optional[str] = None,
) -> str:
    try:
        text = asyncio.run(
            asyncio.wait_for(
                _chat_text(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    model_override=model_override,
                ),
                timeout=float(max(20, timeout_sec)),
            )
        )
    except TimeoutError as exc:
        raise RuntimeError("timeout:llm") from exc
    if not text:
        raise RuntimeError("llm_stage_failed:empty")
    return text


def _executor_confirm_design_parameters(
    *,
    executor_base: str,
    design_spec_md_text: str,
    language: str,
    total_pages: int,
    timeout_sec: int,
) -> str:
    messages = [
        {
            "role": "system",
            "content": "\n\n".join(
                [
                    "You are executing ppt-master Executor preflight confirmation.",
                    "Produce design parameter confirmation only.",
                    executor_base,
                ]
            )[:180000],
        },
        {
            "role": "user",
            "content": (
                f"Deck language: {language}\n"
                f"Total pages: {total_pages}\n"
                "Confirm canvas dimensions, font plan, and color plan for this deck.\n"
                f"Design spec markdown:\n{design_spec_md_text[:100000]}"
            ),
        },
    ]
    return _call_chat_text(
        messages=messages,
        max_tokens=3000,
        timeout_sec=max(40, min(timeout_sec, 900)),
        temperature=0.0,
    )


def _executor_plan_page(
    *,
    executor_base: str,
    executor_style: str,
    design_spec_md_text: str,
    prompt: str,
    language: str,
    page_no: int,
    total_pages: int,
    previous_titles: List[str],
    timeout_sec: int,
) -> str:
    max_tokens = max(1200, min(5000, _env_int("PPT_MASTER_EXECUTOR_PLAN_MAX_TOKENS", 2200)))
    design_spec_limit = max(8000, min(100000, _env_int("PPT_MASTER_EXECUTOR_PLAN_DESIGNSPEC_CHARS", 30000)))
    messages = [
        {
            "role": "system",
            "content": "\n\n".join(
                [
                    "You are executing ppt-master Executor page planning declaration.",
                    "Output exactly two markdown lines:",
                    "1) Template mapping: <template svg path or None (free design)>",
                    "2) Adherence rules / layout strategy: <concise plan>",
                    executor_base,
                    executor_style,
                ]
            )[:200000],
        },
        {
            "role": "user",
            "content": (
                f"Deck topic: {prompt}\n"
                f"Language for content: {language}\n"
                f"Page: {page_no}/{total_pages}\n"
                f"Previous page titles: {json.dumps(previous_titles[-5:], ensure_ascii=False)}\n"
                f"Design spec markdown:\n{design_spec_md_text[:design_spec_limit]}"
            ),
        },
    ]
    return _call_chat_text(
        messages=messages,
        max_tokens=max_tokens,
        timeout_sec=max(40, min(timeout_sec, 900)),
        temperature=0.0,
    )


def _extract_page_plan_section(plan_text: str, page_no: int) -> str:
    text = _text(plan_text, "")
    if not text:
        return ""
    patterns = [
        rf"(?ims)^#+\s*slide\s*{page_no}\b.*?(?=^#+\s*slide\s*\d+\b|\Z)",
        rf"(?ims)^.*?\bslide\s*{page_no}\b.*?(?=\bslide\s*\d+\b|\Z)",
        rf"(?ims)^.*?\bpage\s*{page_no}\b.*?(?=\bpage\s*\d+\b|\Z)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return _text(m.group(0), "")
    return text[:4000]


def _extract_design_spec_section(
    design_spec_text: str,
    page_no: int,
    total_pages: int,
    max_chars: int,
) -> str:
    text = _text(design_spec_text, "")
    if not text:
        return ""

    limit = max(4000, int(max_chars))
    first_slide_header = re.search(r"(?im)^#+\s*(?:slide|page)\s*\d+\b", text)
    global_limit = max(1200, min(8000, limit // 3))
    global_part = text[: first_slide_header.start()] if first_slide_header else text[:global_limit]
    global_part = _text(global_part, "")[:global_limit]

    patterns = [
        rf"(?ims)^#+\s*(?:slide|page)\s*{page_no}\b.*?(?=^#+\s*(?:slide|page)\s*\d+\b|\Z)",
        rf"(?ims)^#+\s*第\s*{page_no}\s*页.*?(?=^#+\s*第\s*\d+\s*页|\Z)",
        rf"(?ims)^#+\s*(?:{page_no}/{total_pages}).*?(?=^#+\s*(?:\d+/{total_pages})|\Z)",
        rf"(?ims)\b(?:slide|page)\s*{page_no}\b.*?(?=(?:slide|page)\s*\d+\b|\Z)",
    ]
    page_part = ""
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            page_part = _text(match.group(0), "")
            break
    if not page_part:
        page_part = text[: max(2400, min(limit, 12000))]

    combined = f"{global_part}\n\n{page_part}".strip()
    return combined[:limit]


def _build_fast_page_plan(*, page_no: int, total_pages: int) -> str:
    if page_no == 1:
        template = "01_cover.svg"
        strategy = "Strong title slide with one-line subtitle and visual anchor."
    elif page_no == total_pages:
        template = "04_ending.svg"
        strategy = "Summary and Q&A close with key takeaways."
    elif page_no == 2:
        template = "02_toc.svg"
        strategy = "Agenda/table of contents that matches chapter flow."
    elif page_no in {3, 6, 9}:
        template = "02_chapter.svg"
        strategy = "Chapter divider emphasizing transition and hierarchy."
    else:
        template = "03_content.svg"
        strategy = "Content page with 3-5 concise bullets and evidence."
    return (
        f"Template mapping: {template}\n"
        f"Adherence rules / layout strategy: {strategy}"
    )


def _executor_render_page(
    *,
    executor_base: str,
    executor_style: str,
    shared_standards: str,
    design_spec_md_text: str,
    design_confirmation: str,
    page_plan: str,
    template_svg_name: str,
    template_svg_text: str,
    prompt: str,
    source_md_text: str,
    language: str,
    page_no: int,
    total_pages: int,
    previous_titles: List[str],
    timeout_sec: int,
    include_notes: bool = True,
) -> str:
    max_tokens = max(4000, min(18000, _env_int("PPT_MASTER_EXECUTOR_RENDER_MAX_TOKENS", 9000)))
    source_limit = max(1500, min(30000, _env_int("PPT_MASTER_EXECUTOR_SOURCE_CHARS", 8000)))
    design_spec_limit = max(6000, min(50000, _env_int("PPT_MASTER_EXECUTOR_DESIGNSPEC_CHARS", 22000)))
    template_svg_limit = max(3000, min(20000, _env_int("PPT_MASTER_EXECUTOR_TEMPLATE_SVG_CHARS", 12000)))
    render_model = _text(os.getenv("PPT_MASTER_EXECUTOR_RENDER_MODEL"), "")
    plan_section = _extract_page_plan_section(page_plan, page_no)
    design_spec_excerpt = _extract_design_spec_section(
        design_spec_text=design_spec_md_text,
        page_no=page_no,
        total_pages=total_pages,
        max_chars=design_spec_limit,
    )
    template_section = (
        f"Template reference ({template_svg_name}):\n{template_svg_text[:template_svg_limit]}"
        if _text(template_svg_text, "")
        else "Template reference: none (free design)"
    )
    messages = [
        {
            "role": "system",
            "content": "\n\n".join(
                [
                    "You are executing ppt-master Executor visual construction phase.",
                    "Follow executor-base, selected style guidance, and shared-standards as the primary authority.",
                    (
                        "Output only final artifacts in plain text with exactly two fenced blocks:\n"
                        "1) ```svg ...``` containing one complete valid SVG document.\n"
                        "2) ```notes ...``` containing speaker notes for this page."
                        if include_notes
                        else
                        "Output only one fenced block: ```svg ...``` containing one complete valid SVG document."
                    ),
                    "Do not output template mapping, confirmations, headings, or analysis text.",
                    "Write content in the requested language and keep outputs production-ready.",
                    executor_base,
                    executor_style,
                    shared_standards,
                ]
            )[:220000],
        },
        {
            "role": "user",
            "content": (
                f"Deck topic: {prompt}\n"
                f"Source markdown excerpt:\n{source_md_text[:source_limit]}\n\n"
                f"Language for content: {language}\n"
                f"Page: {page_no}/{total_pages}\n"
                f"Previous page titles: {json.dumps(previous_titles[-5:], ensure_ascii=False)}\n"
                f"Confirmed global design parameters:\n{design_confirmation[:10000]}\n\n"
                f"Page plan section:\n{plan_section}\n\n"
                f"{template_section}\n\n"
                f"Design specification (global + current page excerpt):\n{design_spec_excerpt}"
            ),
        },
    ]
    return _call_chat_text(
        messages=messages,
        max_tokens=max_tokens,
        timeout_sec=max(50, min(timeout_sec, 1200)),
        temperature=0.0,
        model_override=(render_model or None),
    )


def _executor_generate_total_notes(
    *,
    executor_base: str,
    design_spec_md_text: str,
    prompt: str,
    language: str,
    page_stems: List[str],
    page_titles: List[str],
    timeout_sec: int,
) -> str:
    max_tokens = max(2000, min(12000, _env_int("PPT_MASTER_EXECUTOR_NOTES_MAX_TOKENS", 7000)))
    design_spec_limit = max(8000, min(40000, _env_int("PPT_MASTER_EXECUTOR_NOTES_DESIGNSPEC_CHARS", 12000)))
    stems_json = json.dumps(page_stems, ensure_ascii=False)
    titles_json = json.dumps(page_titles, ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                "You are generating presentation speaker notes.\n"
                "Return markdown only. For each slide, create one section starting with:\n"
                "# <stem>\n\n"
                "Then provide concise speaking notes in the target language.\n"
                "Do not use code fences."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Deck topic: {prompt}\n"
                f"Language: {language}\n"
                f"Slide stems in strict order: {stems_json}\n"
                f"Slide titles in strict order: {titles_json}\n"
                f"Design spec excerpt:\n{design_spec_md_text[:design_spec_limit]}"
            ),
        },
    ]
    return _call_chat_text(
        messages=messages,
        max_tokens=max_tokens,
        timeout_sec=max(40, min(timeout_sec, 600)),
        temperature=0.2,
    )


def _copy_template_assets(*, template_path: Path, project_path: Path) -> None:
    if not template_path.exists():
        return
    target_templates = project_path / "templates"
    target_images = project_path / "images"
    target_templates.mkdir(parents=True, exist_ok=True)
    target_images.mkdir(parents=True, exist_ok=True)
    for ext in ("*.svg", "design_spec.md"):
        for src in template_path.glob(ext):
            dst = target_templates / src.name
            shutil.copyfile(src, dst)
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for src in template_path.glob(ext):
            dst = target_images / src.name
            shutil.copyfile(src, dst)


def _select_style_reference(*, references_dir: Path, style: str, template_name: str) -> Path:
    style_key = _text(style, "").lower()
    template_key = _text(template_name, "").lower()
    if "consult" in style_key or "mckinsey" in template_key or "consultant" in template_key:
        top_style = references_dir / "executor-consultant-top.md"
        if top_style.exists():
            return top_style
        return references_dir / "executor-consultant.md"
    return references_dir / "executor-general.md"


def _extract_svg_title(svg_markup: str, fallback: str) -> str:
    title_match = re.search(r"(?is)<title>\s*(.*?)\s*</title>", svg_markup or "")
    if title_match:
        return _text(title_match.group(1), fallback)
    text_match = re.search(r'(?is)<text[^>]*>\s*(.*?)\s*</text>', svg_markup or "")
    if text_match:
        text_content = re.sub(r"(?is)<[^>]+>", "", text_match.group(1))
        return _text(text_content, fallback)
    return fallback


def _run_optional_image_generation(
    *,
    scripts_dir: Path,
    project_path: Path,
    prompt: str,
    timeout_sec: int,
) -> Dict[str, str]:
    image_script = scripts_dir / "image_gen.py"
    if not image_script.exists():
        return {"status": "failed", "reason": "image_gen_script_missing"}
    images_dir = project_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(image_script),
        _text(prompt, "")[:240],
        "--aspect_ratio",
        "16:9",
        "--image_size",
        "1K",
        "-o",
        str(images_dir),
        "--backend",
        "openai",
        "--model",
        _text(os.getenv("PPT_MASTER_IMAGE_MODEL"), "gemini-3.1-flash-image-preview"),
    ]
    env = dict(os.environ)
    aiberm_key = _text(env.get("AIBERM_API_KEY"), "")
    aiberm_base = _text(env.get("AIBERM_API_BASE"), "")
    crazyroute_key = _text(env.get("CRAZYROUTE_API_KEY"), "")
    crazyroute_base = _text(env.get("CRAZYROUTE_API_BASE"), "")
    provider_key = aiberm_key or crazyroute_key
    provider_base = aiberm_base or crazyroute_base
    if provider_key:
        env["OPENAI_API_KEY"] = provider_key
    if provider_base:
        env["OPENAI_BASE_URL"] = provider_base
    code, stdout, stderr = _run_cmd(
        cmd=cmd,
        cwd=scripts_dir,
        timeout_sec=max(60, min(timeout_sec, 300)),
        env=env,
    )
    (project_path / "image_gen.log").write_text(
        "\n".join(
            [
                f"$ {' '.join(cmd)}",
                f"exit={code}",
                "stdout:",
                stdout,
                "stderr:",
                stderr,
            ]
        ),
        encoding="utf-8",
    )
    if code != 0:
        return {"status": "failed", "reason": "image_generation_failed_passed"}
    return {"status": "enabled", "reason": "image_generation_ok"}


def _extract_topic_keywords(topic: str, language: str) -> Set[str]:
    raw = _text(topic, "")
    if not raw:
        return set()
    tokens = [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z-]{2,}", raw)]
    if _normalize_language(language) == "zh-CN":
        cjk_chunks = re.findall(r"[\u4e00-\u9fff]{2,18}", raw)
        tokens.extend(cjk_chunks)
    stop = {"create", "presentation", "deck", "about", "with", "the", "and"}
    return {t for t in tokens if t not in stop}


def _score_research_item(
    *,
    query_keywords: Set[str],
    language: str,
    title: str,
    snippet: str,
    url: str,
) -> float:
    del language
    blob = f"{title}\n{snippet}".lower()
    if not blob.strip():
        return 0.1
    keyword_hits = sum(1 for key in query_keywords if key and key.lower() in blob)
    if query_keywords:
        keyword_score = keyword_hits / max(len(query_keywords), 1)
    else:
        keyword_score = 0.3
    domain_bonus = 0.05 if any(host in url.lower() for host in (".gov", ".edu", ".org")) else 0.0
    return keyword_score + domain_bonus

def _search_fetch_web(*, query: str, language: str, repo_root: Path, limit: int = 3) -> List[Dict[str, str]]:
    adapter = repo_root / "agent" / "src" / "ppt_master_web_adapter.py"
    if not adapter.exists():
        return []
    cmd = [
        sys.executable,
        str(adapter),
        "search",
        "--query",
        _text(query, ""),
        "--num",
        "5",
        "--language",
        _normalize_language(language),
    ]
    code, stdout, stderr = _run_cmd(cmd=cmd, cwd=adapter.parent, timeout_sec=30)
    if code != 0:
        _ = stderr
        return []
    try:
        payload = json.loads(stdout) if stdout.strip() else {}
    except Exception:
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    query_keywords = _extract_topic_keywords(query, language)
    out: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"), "")
        url = _text(item.get("url"), "")
        if not (title and url):
            continue
        fetch_cmd = [
            sys.executable,
            str(adapter),
            "fetch",
            "--url",
            url,
            "--max-chars",
            "6000",
        ]
        f_code, f_stdout, _f_stderr = _run_cmd(cmd=fetch_cmd, cwd=adapter.parent, timeout_sec=30)
        snippet = ""
        if f_code == 0:
            try:
                fetched = json.loads(f_stdout) if f_stdout.strip() else {}
                snippet = _text((fetched.get("content") if isinstance(fetched, dict) else ""), "")[:1000]
            except Exception:
                snippet = ""
        score = _score_research_item(
            query_keywords=query_keywords,
            language=language,
            title=title,
            snippet=snippet,
            url=url,
        )
        out.append({"title": title, "url": url, "snippet": snippet, "score": round(score, 4)})
    out.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
    return out[:limit]


def run_native_pipeline(
    *,
    request_payload: Dict[str, Any],
    project_path: Path,
    timeout_sec: int,
) -> Dict[str, Any]:
    prompt = _text(request_payload.get("prompt"), "")
    if not prompt:
        raise RuntimeError("missing_prompt")

    repo_root = Path(__file__).resolve().parents[2]
    skill_root = repo_root / "vendor" / "minimax-skills" / "skills" / "ppt-master"
    scripts_dir = skill_root / "scripts"
    references_dir = skill_root / "references"
    templates_dir = skill_root / "templates"

    language = _normalize_language(request_payload.get("language"))
    total_pages = max(3, min(50, _to_int(request_payload.get("total_pages"), 12)))
    style = _text(request_payload.get("style"), "professional")
    template_family = _text(request_payload.get("template_family"), "auto")
    web_enrichment = _to_bool(request_payload.get("web_enrichment"), True)
    include_images = _to_bool(request_payload.get("include_images"), False)
    fast_plan = _to_bool(
        request_payload.get("fast_plan"),
        _to_bool(os.getenv("PPT_MASTER_EXECUTOR_FAST_PLAN"), False),
    )
    notes_mode = _text(
        request_payload.get("notes_mode"),
        _text(os.getenv("PPT_MASTER_EXECUTOR_NOTES_MODE"), "batch"),
    ).lower()
    if notes_mode not in {"batch", "per_page"}:
        notes_mode = "batch"

    def _cap_timeout(*, floor: int, upper: int, env_name: str) -> int:
        cap = _env_int(env_name, upper)
        cap = max(floor, cap)
        return max(floor, min(int(timeout_sec), cap))

    t_confirm_timeout = _cap_timeout(
        floor=40,
        upper=420,
        env_name="PPT_MASTER_STRATEGIST_CONFIRM_TIMEOUT_SEC",
    )
    t_design_spec_timeout = _cap_timeout(
        floor=60,
        upper=600,
        env_name="PPT_MASTER_STRATEGIST_DESIGNSPEC_TIMEOUT_SEC",
    )
    t_executor_confirm_timeout = _cap_timeout(
        floor=40,
        upper=300,
        env_name="PPT_MASTER_EXECUTOR_CONFIRM_TIMEOUT_SEC",
    )
    t_plan_timeout = _cap_timeout(
        floor=30,
        upper=180,
        env_name="PPT_MASTER_EXECUTOR_PLAN_TIMEOUT_SEC",
    )
    t_render_timeout = _cap_timeout(
        floor=45,
        upper=300,
        env_name="PPT_MASTER_EXECUTOR_RENDER_TIMEOUT_SEC",
    )
    t_render_retry_timeout = _cap_timeout(
        floor=40,
        upper=180,
        env_name="PPT_MASTER_EXECUTOR_RENDER_RETRY_TIMEOUT_SEC",
    )
    t_xml_repair_timeout = _cap_timeout(
        floor=30,
        upper=120,
        env_name="PPT_MASTER_EXECUTOR_XML_REPAIR_TIMEOUT_SEC",
    )

    stage_rows: List[Dict[str, Any]] = []
    perf_rows: List[Dict[str, Any]] = []
    run_started_at = _utc_now()
    run_t0 = time.perf_counter()

    def _record(stage: str, ok: bool, detail: str = "") -> None:
        stage_rows.append(
            {
                "stage": stage,
                "ok": bool(ok),
                "started_at": _utc_now(),
                "finished_at": _utc_now(),
                "diagnostics": [detail] if detail else [],
            }
        )

    def _perf(label: str, started: float, **meta: Any) -> None:
        row: Dict[str, Any] = {
            "label": label,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 1),
            "at": _utc_now(),
        }
        for key, value in meta.items():
            if value is not None:
                row[key] = value
        perf_rows.append(row)

    runtime_input_dir = project_path / "_runtime_inputs"
    runtime_input_dir.mkdir(parents=True, exist_ok=True)
    progress_path = runtime_input_dir / "runtime_progress.json"

    def _update_progress(
        stage: str,
        detail: str,
        *,
        substage: str = "",
        percent: Optional[float] = None,
        current_page: Optional[int] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "stage": stage,
            "detail": _text(detail, stage),
            "updated_at": _utc_now(),
            "total_pages": int(total_pages),
        }
        if substage:
            payload["substage"] = substage
        if percent is not None:
            payload["percent"] = round(float(percent), 1)
        if current_page is not None:
            payload["current_page"] = max(0, min(int(current_page), int(total_pages)))
        try:
            progress_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # Step 1: source material
    _update_progress("step1", "Initializing generation workspace", percent=3.0)
    source_seed = runtime_input_dir / "prompt_source.md"
    source_seed.write_text(f"# Prompt\n\n{prompt}\n", encoding="utf-8")
    _record("step1_source_ready", True, "prompt_source_md_created")

    # Step 2: import sources via project_manager import-sources --move
    import_cmd = [
        sys.executable,
        str(scripts_dir / "project_manager.py"),
        "import-sources",
        str(project_path),
        str(source_seed),
        "--move",
    ]
    code, stdout, stderr = _run_cmd(
        cmd=import_cmd,
        cwd=scripts_dir,
        timeout_sec=max(40, min(timeout_sec, 300)),
    )
    if code != 0:
        detail = _text(stderr or stdout, f"exit_{code}")[:500]
        raise RuntimeError(f"script_nonzero:project_manager.py:{detail}")
    _record("step2_import_sources", True, "import-sources --move")
    _update_progress("step2", "Preparing source files", percent=8.0)
    sources_dir = project_path / "sources"
    source_md_candidates = sorted(sources_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    source_md = source_md_candidates[0] if source_md_candidates else (sources_dir / "prompt_source.md")

    # Step 3: template selection
    selected_template = _choose_template_family(
        prompt=prompt,
        style=style,
        language=language,
        template_family=template_family,
        layouts_dir=templates_dir / "layouts",
        layouts_index_path=templates_dir / "layouts" / "layouts_index.json",
        timeout_sec=max(40, min(timeout_sec, 240)),
    )
    template_path = templates_dir / "layouts" / selected_template
    if not template_path.exists():
        selected_template = "mckinsey"
        template_path = templates_dir / "layouts" / selected_template
    _copy_template_assets(template_path=template_path, project_path=project_path)
    _record("step3_template_selected", True, selected_template)
    _update_progress("step3", f"Template selected: {selected_template}", percent=12.0)

    # Step 4: strategist (auto-confirm mode, no blocking prompt to user)
    strategist_doc = (references_dir / "strategist.md").read_text(encoding="utf-8", errors="ignore")
    design_spec_ref = (templates_dir / "design_spec_reference.md").read_text(encoding="utf-8", errors="ignore")
    research_items: List[Dict[str, str]] = []
    _update_progress("step4", "Collecting web research context", substage="research", percent=14.0)
    if web_enrichment:
        t0 = time.perf_counter()
        research_items = _search_fetch_web(query=prompt, language=language, repo_root=repo_root, limit=3)
        _perf("step4.web_enrichment", t0, items=len(research_items))
    if web_enrichment and not research_items:
        _record("step4_research_fallback", True, "web_enrichment_no_relevant_hit_prompt_only")
    research_path = project_path / "research_notes.json"
    research_path.write_text(json.dumps({"items": research_items}, ensure_ascii=False, indent=2), encoding="utf-8")
    source_md_text = _text(source_md.read_text(encoding="utf-8", errors="ignore") if source_md.exists() else "", "")
    template_design_spec_text = _text(
        (template_path / "design_spec.md").read_text(encoding="utf-8", errors="ignore")
        if (template_path / "design_spec.md").exists()
        else "",
        "",
    )

    debug_dir = project_path / "_runtime_inputs" / "strategist_raw"
    debug_dir.mkdir(parents=True, exist_ok=True)

    _update_progress("step4", "Generating confirmation checklist", substage="confirmations", percent=18.0)
    t0 = time.perf_counter()
    confirmations_text = _build_strategist_confirmations(
        strategist_doc=strategist_doc,
        prompt=prompt,
        language=language,
        total_pages=total_pages,
        style=style,
        selected_template=selected_template,
        source_md_text=source_md_text,
        template_design_spec_text=template_design_spec_text,
        research_items=research_items,
        timeout_sec=t_confirm_timeout,
    )
    _perf("step4.confirmations", t0, timeout_sec=t_confirm_timeout)
    (debug_dir / "confirmations_proposed.md").write_text(confirmations_text, encoding="utf-8")
    _record("step4_confirmations", True, "eight_confirmations_proposed")

    auto_confirm_message = "AUTO-CONFIRMED by service runtime (API unattended mode)."
    (debug_dir / "confirmations_confirmed.md").write_text(
        confirmations_text + "\n\n" + auto_confirm_message + "\n",
        encoding="utf-8",
    )
    _record("step4_confirmations_auto_approved", True, "approved")

    _update_progress("step4", "Generating design specification", substage="design_spec", percent=22.0)
    t0 = time.perf_counter()
    design_spec_md_text = _build_strategist_design_spec(
        strategist_doc=strategist_doc,
        design_spec_ref=design_spec_ref,
        prompt=prompt,
        language=language,
        total_pages=total_pages,
        style=style,
        selected_template=selected_template,
        source_md_text=source_md_text,
        template_design_spec_text=template_design_spec_text,
        research_items=research_items,
        confirmations_text=confirmations_text,
        timeout_sec=t_design_spec_timeout,
    )
    _perf("step4.design_spec", t0, timeout_sec=t_design_spec_timeout)
    if not _text(design_spec_md_text, ""):
        raise RuntimeError("llm_stage_failed:strategist_empty")
    (debug_dir / "design_spec_generated.md").write_text(design_spec_md_text, encoding="utf-8")
    design_spec_md_path = project_path / "design_spec.md"
    design_spec_md_path.write_text(design_spec_md_text, encoding="utf-8")
    _record(
        "step4_strategist",
        True,
        "design_spec_md_generated_auto_confirm",
    )
    _update_progress("step4", "Design specification ready", substage="completed", percent=24.0)

    # Step 5: optional image generation (non-blocking)
    image_status = {"status": "disabled", "reason": "include_images_false"}
    if include_images:
        image_status = _run_optional_image_generation(
            scripts_dir=scripts_dir,
            project_path=project_path,
            prompt=prompt,
            timeout_sec=max(60, min(timeout_sec, 300)),
        )
    _record("step5_image_generator", True, f"{image_status['status']}:{image_status['reason']}")
    _update_progress("step5", "Preparing assets for rendering", percent=25.0)

    # Step 6: executor sequentially
    executor_base = (references_dir / "executor-base.md").read_text(encoding="utf-8", errors="ignore")
    style_ref_path = _select_style_reference(
        references_dir=references_dir,
        style=style,
        template_name=selected_template,
    )
    executor_style = style_ref_path.read_text(encoding="utf-8", errors="ignore")
    shared_standards = (references_dir / "shared-standards.md").read_text(
        encoding="utf-8",
        errors="ignore",
    )
    template_svg_text_by_name: Dict[str, str] = {}
    for filename in ("01_cover.svg", "02_toc.svg", "02_chapter.svg", "03_content.svg", "04_ending.svg"):
        local_template = project_path / "templates" / filename
        if not local_template.exists():
            local_template = template_path / filename
        if local_template.exists():
            template_svg_text_by_name[filename] = _text(
                local_template.read_text(encoding="utf-8", errors="ignore"),
                "",
            )
    svg_output = project_path / "svg_output"
    notes_dir = project_path / "notes"
    svg_output.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    debug_dir = project_path / "_runtime_inputs" / "executor_raw"
    debug_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    design_confirmation = _executor_confirm_design_parameters(
        executor_base=executor_base,
        design_spec_md_text=design_spec_md_text,
        language=language,
        total_pages=total_pages,
        timeout_sec=t_executor_confirm_timeout,
    )
    _perf("step6.executor_confirm", t0, timeout_sec=t_executor_confirm_timeout)
    (debug_dir / "design_confirmation.txt").write_text(design_confirmation, encoding="utf-8")

    notes_sections: List[str] = []
    page_titles: List[str] = []
    page_stems: List[str] = []
    for idx in range(total_pages):
        page_no = idx + 1
        _update_progress(
            "step6",
            f"Generating slides {page_no}/{total_pages}",
            percent=25.0 + (float(max(page_no - 1, 0)) / float(max(total_pages, 1))) * 65.0,
            current_page=max(page_no - 1, 0),
        )
        plan_t0 = time.perf_counter()
        if fast_plan:
            page_plan = _build_fast_page_plan(page_no=page_no, total_pages=total_pages)
            _perf("step6.page_plan.fast", plan_t0, page_no=page_no)
        else:
            page_plan = _executor_plan_page(
                executor_base=executor_base,
                executor_style=executor_style,
                design_spec_md_text=design_spec_md_text,
                prompt=prompt,
                language=language,
                page_no=page_no,
                total_pages=total_pages,
                previous_titles=page_titles,
                timeout_sec=t_plan_timeout,
            )
            _perf("step6.page_plan.llm", plan_t0, page_no=page_no, timeout_sec=t_plan_timeout)
        (debug_dir / f"page_{page_no:02d}_plan.txt").write_text(page_plan, encoding="utf-8")

        plan_text_lower = _text(page_plan, "").lower()
        template_hint_match = re.search(r"(0[1-4]_[a-z0-9_-]+\.svg)", plan_text_lower)
        template_svg_name = template_hint_match.group(1) if template_hint_match else ""
        if not template_svg_name:
            if page_no == 1:
                template_svg_name = "01_cover.svg"
            elif page_no == total_pages:
                template_svg_name = "04_ending.svg"
            elif page_no == 2 and "02_toc.svg" in template_svg_text_by_name:
                template_svg_name = "02_toc.svg"
            elif "chapter" in plan_text_lower and "02_chapter.svg" in template_svg_text_by_name:
                template_svg_name = "02_chapter.svg"
            else:
                template_svg_name = "03_content.svg"
        template_svg_text = _text(template_svg_text_by_name.get(template_svg_name), "")
        render_t0 = time.perf_counter()
        llm_raw = _executor_render_page(
            executor_base=executor_base,
            executor_style=executor_style,
            shared_standards=shared_standards,
            design_spec_md_text=design_spec_md_text,
            design_confirmation=design_confirmation,
            page_plan=page_plan,
            template_svg_name=template_svg_name,
            template_svg_text=template_svg_text,
            prompt=prompt,
            source_md_text=source_md_text,
            language=language,
            page_no=page_no,
            total_pages=total_pages,
            previous_titles=page_titles,
            timeout_sec=t_render_timeout,
            include_notes=(notes_mode == "per_page"),
        )
        _perf("step6.page_render.llm", render_t0, page_no=page_no, timeout_sec=t_render_timeout)
        (debug_dir / f"page_{page_no:02d}_render_1.txt").write_text(
            llm_raw,
            encoding="utf-8",
        )
        svg_markup, speaker_notes = _parse_executor_output(llm_raw)
        svg_markup = _sanitize_svg_markup(_extract_svg_document(svg_markup) or svg_markup)
        used_fallback_svg = False
        if "<svg" not in _text(svg_markup, "").lower():
            retry_t0 = time.perf_counter()
            llm_raw_retry = _executor_render_page(
                executor_base=executor_base,
                executor_style=executor_style,
                shared_standards=shared_standards,
                design_spec_md_text=design_spec_md_text,
                design_confirmation=design_confirmation,
                page_plan=page_plan,
                template_svg_name=template_svg_name,
                template_svg_text=template_svg_text,
                prompt=prompt,
                source_md_text=source_md_text,
                language=language,
                page_no=page_no,
                total_pages=total_pages,
                previous_titles=page_titles,
                timeout_sec=t_render_retry_timeout,
                include_notes=(notes_mode == "per_page"),
            )
            _perf(
                "step6.page_render.retry_llm",
                retry_t0,
                page_no=page_no,
                timeout_sec=t_render_retry_timeout,
            )
            (debug_dir / f"page_{page_no:02d}_render_2.txt").write_text(
                llm_raw_retry,
                encoding="utf-8",
            )
            svg_markup, speaker_notes = _parse_executor_output(llm_raw_retry)
            svg_markup = _sanitize_svg_markup(_extract_svg_document(svg_markup) or svg_markup)
            if "<svg" not in _text(svg_markup, "").lower():
                fallback_svg = _sanitize_svg_markup(
                    _extract_svg_document(template_svg_text) or template_svg_text
                )
                if "<svg" in _text(fallback_svg, "").lower():
                    svg_markup = fallback_svg
                    speaker_notes = (
                        _text(speaker_notes, "").strip()
                        or f"Fallback slide content for page {page_no} due to LLM SVG format failure."
                    )
                    used_fallback_svg = True
                    _record(
                        f"step6_executor_page_{page_no}",
                        True,
                        "fallback_template_svg_used:missing_svg_root",
                    )
                else:
                    raise RuntimeError(f"llm_stage_failed:executor_svg_page_{page_no}:missing_svg_root")
        if not _is_valid_xml(svg_markup):
            (debug_dir / f"page_{page_no:02d}_render_invalid_xml.txt").write_text(
                _text(svg_markup, ""),
                encoding="utf-8",
            )
            repaired_svg = ""
            try:
                repair_t0 = time.perf_counter()
                repaired_svg = _repair_svg_xml_with_llm(
                    invalid_svg=svg_markup,
                    page_no=page_no,
                    timeout_sec=t_xml_repair_timeout,
                )
                _perf(
                    "step6.page_xml_repair.llm",
                    repair_t0,
                    page_no=page_no,
                    timeout_sec=t_xml_repair_timeout,
                )
            except Exception as exc:
                _record(
                    f"step6_executor_page_{page_no}_xml_repair",
                    True,
                    f"repair_attempt_failed:{_text(exc, 'unknown')[:120]}",
                )
            if repaired_svg and _is_valid_xml(repaired_svg):
                svg_markup = repaired_svg
                (debug_dir / f"page_{page_no:02d}_render_xml_repaired.txt").write_text(
                    svg_markup,
                    encoding="utf-8",
                )
                _record(
                    f"step6_executor_page_{page_no}_xml_repair",
                    True,
                    "repaired_by_llm",
                )
            else:
                fallback_svg = _sanitize_svg_markup(
                    _extract_svg_document(template_svg_text) or template_svg_text
                )
                if _is_valid_xml(fallback_svg):
                    svg_markup = fallback_svg
                    speaker_notes = (
                        _text(speaker_notes, "").strip()
                        or f"Fallback slide content for page {page_no} due to invalid SVG XML."
                    )
                    used_fallback_svg = True
                    _record(
                        f"step6_executor_page_{page_no}",
                        True,
                        "fallback_template_svg_used:invalid_xml",
                    )
                else:
                    raise RuntimeError(f"llm_stage_failed:executor_svg_page_{page_no}:invalid_xml")
        if used_fallback_svg:
            _record(
                f"step6_executor_page_{page_no}_xml",
                True,
                "fallback_svg_xml_valid",
            )

        raw_title = _extract_svg_title(svg_markup, f"slide_{page_no}")

        stem = f"{page_no:02d}_{_safe_slug(raw_title, f'slide_{page_no}')}"
        svg_file = svg_output / f"{stem}.svg"
        svg_file.write_text(svg_markup, encoding="utf-8")
        page_stems.append(stem)
        page_titles.append(raw_title)
        if notes_mode == "per_page":
            notes_sections.append(f"# {stem}\n\n{_text(speaker_notes, raw_title)}\n")
        _update_progress(
            "step6",
            f"Generating slides {page_no}/{total_pages}",
            percent=25.0 + (float(page_no) / float(max(total_pages, 1))) * 65.0,
            current_page=page_no,
        )

    if notes_mode == "batch":
        notes_t0 = time.perf_counter()
        try:
            notes_total_text = _executor_generate_total_notes(
                executor_base=executor_base,
                design_spec_md_text=design_spec_md_text,
                prompt=prompt,
                language=language,
                page_stems=page_stems,
                page_titles=page_titles,
                timeout_sec=max(60, min(timeout_sec, 600)),
            )
            _perf("step6.notes_batch", notes_t0, mode="batch")
            if not _text(notes_total_text, ""):
                raise RuntimeError("empty_notes")
        except Exception as exc:
            _perf("step6.notes_batch_fallback", notes_t0, detail=_text(exc, "unknown")[:120])
            notes_total_text = "\n\n".join(
                [f"# {stem}\n\n{title}\n" for stem, title in zip(page_stems, page_titles)]
            )
        (notes_dir / "total.md").write_text(notes_total_text, encoding="utf-8")
    else:
        (notes_dir / "total.md").write_text("\n\n".join(notes_sections), encoding="utf-8")

    _record("step6_executor", True, f"svg_pages={total_pages}")
    _update_progress("step7", "Finalizing and packaging PPTX", percent=96.0, current_page=total_pages)

    # Step 7: post-process and export
    commands = [
        [sys.executable, str(scripts_dir / "total_md_split.py"), str(project_path)],
        [sys.executable, str(scripts_dir / "finalize_svg.py"), str(project_path)],
        [sys.executable, str(scripts_dir / "svg_to_pptx.py"), str(project_path), "-s", "final"],
    ]
    export_with_warnings = False
    for cmd in commands:
        cmd_t0 = time.perf_counter()
        code, stdout, stderr = _run_cmd(
            cmd=cmd,
            cwd=scripts_dir,
            timeout_sec=max(90, min(timeout_sec, 1800)),
        )
        _perf("step7.command", cmd_t0, script=Path(cmd[1]).name, exit_code=code)
        if code != 0:
            script_name = Path(cmd[1]).name
            if script_name == "svg_to_pptx.py":
                existing_pptx = sorted(project_path.glob("*.pptx"))
                if existing_pptx:
                    export_with_warnings = True
                    detail = _text(stderr or stdout, f"exit_{code}")[:500]
                    _record(f"step7_{script_name}", True, f"nonzero_with_artifacts:{detail}")
                    continue
            detail = _text(stderr or stdout, f"exit_{code}")[:500]
            raise RuntimeError(f"script_nonzero:{script_name}:{detail}")
        _record(f"step7_{Path(cmd[1]).name}", True, "ok")

    pptx_candidates = sorted(project_path.glob("*.pptx"), key=lambda p: p.stat().st_mtime, reverse=True)
    output_pptx = ""
    if export_with_warnings:
        for row in pptx_candidates:
            if row.name.lower().endswith("_svg.pptx"):
                output_pptx = str(row)
                break
    if not output_pptx:
        for row in pptx_candidates:
            if not row.name.lower().endswith("_svg.pptx"):
                output_pptx = str(row)
                break
    if not output_pptx and pptx_candidates:
        output_pptx = str(pptx_candidates[0])
    if not output_pptx:
        raise RuntimeError("artifact_missing:output_pptx")

    total_elapsed_ms = round((time.perf_counter() - run_t0) * 1000.0, 1)
    runtime_profile_path = project_path / "runtime_profile.json"
    runtime_profile_path.write_text(
        json.dumps(
            {
                "started_at": run_started_at,
                "finished_at": _utc_now(),
                "total_elapsed_ms": total_elapsed_ms,
                "total_pages": total_pages,
                "fast_plan": bool(fast_plan),
                "notes_mode": notes_mode,
                "timeouts": {
                    "step4_confirmations": t_confirm_timeout,
                    "step4_design_spec": t_design_spec_timeout,
                    "step6_executor_confirm": t_executor_confirm_timeout,
                    "step6_page_plan": t_plan_timeout,
                    "step6_page_render": t_render_timeout,
                    "step6_page_render_retry": t_render_retry_timeout,
                    "step6_xml_repair": t_xml_repair_timeout,
                },
                "records": perf_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "run_id": f"ppt_master_native_{uuid.uuid4().hex[:12]}",
        "stages": stage_rows,
        "artifacts": {
            "design_spec": str(design_spec_md_path),
            "notes_total": str(notes_dir / "total.md"),
            "research_notes": str(research_path),
            "source_md": str(source_md),
            "image_status": image_status["status"],
            "image_reason": image_status["reason"],
            "runtime_profile": str(runtime_profile_path),
        },
        "export": {
            "output_pptx": output_pptx,
            "generator_mode": "ppt_master_native_runtime",
            "project_name": project_path.name,
        },
    }




