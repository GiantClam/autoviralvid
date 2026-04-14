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
    selected = _text(raw_selected, "").splitlines()[0].strip()
    selected = selected.strip("` ").split()[:1]
    selected_id = selected[0] if selected else ""
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
                f"Source markdown:\n{source_md_text[:120000]}\n\n"
                f"Template design spec example:\n{template_design_spec_text[:50000]}\n\n"
                f"Research evidence JSON: {json.dumps(research_items, ensure_ascii=False)}\n"
                "Provide concise recommendations for the eight confirmations only."
            ),
        },
    ]
    return _call_chat_text(
        messages=messages,
        max_tokens=6000,
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
                f"Source markdown:\n{source_md_text[:120000]}\n\n"
                f"Template design spec example:\n{template_design_spec_text[:50000]}\n\n"
                f"Research evidence JSON: {json.dumps(research_items, ensure_ascii=False)}\n"
                f"Confirmed Eight Confirmations package:\n{confirmations_text[:40000]}\n\n"
                "Auto-confirmation: approved as-is. Produce the final complete design_spec.md now."
            ),
        },
    ]
    return _call_chat_text(
        messages=messages,
        max_tokens=12000,
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
                f"Design spec markdown:\n{design_spec_md_text[:100000]}"
            ),
        },
    ]
    return _call_chat_text(
        messages=messages,
        max_tokens=4000,
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
) -> str:
    render_model = _text(os.getenv("PPT_MASTER_EXECUTOR_RENDER_MODEL"), "")
    plan_section = _extract_page_plan_section(page_plan, page_no)
    template_section = (
        f"Template reference ({template_svg_name}):\n{template_svg_text[:20000]}"
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
                    "Output only final artifacts in plain text with exactly two fenced blocks:",
                    "1) ```svg ...``` containing one complete valid SVG document.",
                    "2) ```notes ...``` containing speaker notes for this page.",
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
                f"Source markdown excerpt:\n{source_md_text[:50000]}\n\n"
                f"Language for content: {language}\n"
                f"Page: {page_no}/{total_pages}\n"
                f"Previous page titles: {json.dumps(previous_titles[-5:], ensure_ascii=False)}\n"
                f"Confirmed global design parameters:\n{design_confirmation[:10000]}\n\n"
                f"Page plan section:\n{plan_section}\n\n"
                f"{template_section}\n\n"
                f"Design specification:\n{design_spec_md_text[:90000]}"
            ),
        },
    ]
    return _call_chat_text(
        messages=messages,
        max_tokens=16000,
        timeout_sec=max(50, min(timeout_sec, 1200)),
        temperature=0.0,
        model_override=(render_model or None),
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

    stage_rows: List[Dict[str, Any]] = []

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

    # Step 1: source material
    runtime_input_dir = project_path / "_runtime_inputs"
    runtime_input_dir.mkdir(parents=True, exist_ok=True)
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

    # Step 4: strategist (auto-confirm mode, no blocking prompt to user)
    strategist_doc = (references_dir / "strategist.md").read_text(encoding="utf-8", errors="ignore")
    design_spec_ref = (templates_dir / "design_spec_reference.md").read_text(encoding="utf-8", errors="ignore")
    research_items: List[Dict[str, str]] = []
    if web_enrichment:
        research_items = _search_fetch_web(query=prompt, language=language, repo_root=repo_root, limit=3)
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
        timeout_sec=max(60, min(timeout_sec, 900)),
    )
    (debug_dir / "confirmations_proposed.md").write_text(confirmations_text, encoding="utf-8")
    _record("step4_confirmations", True, "eight_confirmations_proposed")

    auto_confirm_message = "AUTO-CONFIRMED by service runtime (API unattended mode)."
    (debug_dir / "confirmations_confirmed.md").write_text(
        confirmations_text + "\n\n" + auto_confirm_message + "\n",
        encoding="utf-8",
    )
    _record("step4_confirmations_auto_approved", True, "approved")

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
        timeout_sec=max(60, min(timeout_sec, 1200)),
    )
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
    design_confirmation = _executor_confirm_design_parameters(
        executor_base=executor_base,
        design_spec_md_text=design_spec_md_text,
        language=language,
        total_pages=total_pages,
        timeout_sec=max(50, min(timeout_sec, 1200)),
    )
    (debug_dir / "design_confirmation.txt").write_text(design_confirmation, encoding="utf-8")

    notes_sections: List[str] = []
    page_titles: List[str] = []
    for idx in range(total_pages):
        page_no = idx + 1
        page_plan = _executor_plan_page(
            executor_base=executor_base,
            executor_style=executor_style,
            design_spec_md_text=design_spec_md_text,
            prompt=prompt,
            language=language,
            page_no=page_no,
            total_pages=total_pages,
            previous_titles=page_titles,
            timeout_sec=max(50, min(timeout_sec, 1200)),
        )
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
            timeout_sec=max(50, min(timeout_sec, 1200)),
        )
        (debug_dir / f"page_{page_no:02d}_render_1.txt").write_text(
            llm_raw,
            encoding="utf-8",
        )
        svg_markup, speaker_notes = _parse_executor_output(llm_raw)
        svg_markup = _sanitize_svg_markup(svg_markup)
        used_fallback_svg = False
        if "<svg" not in _text(svg_markup, "").lower():
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
                timeout_sec=max(50, min(timeout_sec, 1200)),
            )
            (debug_dir / f"page_{page_no:02d}_render_2.txt").write_text(
                llm_raw_retry,
                encoding="utf-8",
            )
            svg_markup, speaker_notes = _parse_executor_output(llm_raw_retry)
            svg_markup = _sanitize_svg_markup(svg_markup)
            if "<svg" not in _text(svg_markup, "").lower():
                fallback_svg = _sanitize_svg_markup(template_svg_text)
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
        try:
            ET.fromstring(svg_markup)
        except Exception:
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
        page_titles.append(raw_title)
        notes_sections.append(f"# {stem}\n\n{_text(speaker_notes, raw_title)}\n")
    (notes_dir / "total.md").write_text("\n\n".join(notes_sections), encoding="utf-8")
    _record("step6_executor", True, f"svg_pages={total_pages}")

    # Step 7: post-process and export
    commands = [
        [sys.executable, str(scripts_dir / "total_md_split.py"), str(project_path)],
        [sys.executable, str(scripts_dir / "finalize_svg.py"), str(project_path)],
        [sys.executable, str(scripts_dir / "svg_to_pptx.py"), str(project_path), "-s", "final"],
    ]
    export_with_warnings = False
    for cmd in commands:
        code, stdout, stderr = _run_cmd(
            cmd=cmd,
            cwd=scripts_dir,
            timeout_sec=max(90, min(timeout_sec, 1800)),
        )
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
        },
        "export": {
            "output_pptx": output_pptx,
            "generator_mode": "ppt_master_native_runtime",
            "project_name": project_path.name,
        },
    }




