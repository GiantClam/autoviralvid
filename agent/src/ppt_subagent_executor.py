"""LangGraph-based subagent executor for per-slide PPT retry refinement.

This module reads a slide task payload and returns a JSON object with
`slide_patch` / `load_skills` so Node-side orchestrator can merge changes
before slide re-render.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypedDict

from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from openai import OpenAI


def _strip_surrogate_chars(text: str) -> str:
    if not text:
        return text
    return "".join(ch for ch in text if not 0xD800 <= ord(ch) <= 0xDFFF)


def _sanitize_tree_surrogates(value: Any) -> Any:
    if isinstance(value, str):
        return _strip_surrogate_chars(value)
    if isinstance(value, list):
        return [_sanitize_tree_surrogates(item) for item in value]
    if isinstance(value, dict):
        return {
            _strip_surrogate_chars(str(key)): _sanitize_tree_surrogates(item)
            for key, item in value.items()
        }
    return value


def _normalize_text(value: Any, fallback: str = "") -> str:
    text = _strip_surrogate_chars(str(value or "")).strip()
    return text or fallback


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _resolve_content_model(default: str) -> str:
    return _normalize_text(os.getenv("CONTENT_LLM_MODEL", default), default)


def _normalize_openai_model_id(model_id: str) -> str:
    model = _normalize_text(model_id, "")
    if "/" in model:
        _, tail = model.split("/", 1)
        return _normalize_text(tail, model)
    return model


def _dedupe_skills(values: Any) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in _as_list(values):
        text = _normalize_text(item, "").lower()
        text = "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in text)
        text = text.strip("-")
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


@tool("recommend_render_path")
def recommend_render_path(slide_type: str, current_render_path: str) -> str:
    """Recommend render path by slide semantics."""
    _ = _normalize_text(slide_type, "content").lower()
    _ = _normalize_text(current_render_path, "svg").lower()
    return "svg"


@tool("recommend_layout_grid")
def recommend_layout_grid(slide_type: str, layout_grid: str) -> str:
    """Recommend layout grid when slide does not provide one."""
    slide = _normalize_text(slide_type, "content").lower()
    layout = _normalize_text(layout_grid, "")
    if layout:
        return layout
    if slide == "cover":
        return "full_bleed"
    if slide == "summary":
        return "split_2"
    return "split_2"


class SubagentState(TypedDict, total=False):
    task_payload: Dict[str, Any]
    prompt: str
    skill_hints: List[str]
    skill_docs: List[Dict[str, Any]]
    skill_content: str
    page_guidance: str
    skill_runtime_patch: Dict[str, Any]
    skill_runtime_context: Dict[str, Any]
    skill_runtime_trace: List[Dict[str, Any]]
    tool_patch: Dict[str, Any]
    llm_patch: Dict[str, Any]
    notes: str
    skipped: bool
    runtime_error: bool
    reason: str
    output: Dict[str, Any]


ModelInvoke = Callable[[Dict[str, Any]], Dict[str, Any]]

_SKILL_ALIASES: Dict[str, str] = {
    "pptx": "pptx-generator",
}


def _parse_env_paths(raw_value: str) -> List[Path]:
    text = _normalize_text(raw_value, "")
    if not text:
        return []
    out: List[Path] = []
    for item in text.split(os.pathsep):
        value = _normalize_text(item, "")
        if value:
            out.append(Path(value))
    return out


def _skill_search_roots() -> List[Path]:
    roots: List[Path] = []
    roots.extend(_parse_env_paths(os.getenv("PPT_SUBAGENT_SKILL_ROOTS", "")))

    repo_root = Path(__file__).resolve().parents[2]
    roots.extend(
        [
            repo_root / "vendor" / "minimax-skills" / "plugins" / "pptx-plugin" / "skills",
            repo_root / "vendor" / "minimax-skills" / "skills",
            repo_root / "skills",
        ]
    )
    unique: List[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _load_skill_content(skill_name: str) -> Dict[str, Any]:
    normalized = _normalize_text(skill_name, "").lower()
    if not normalized:
        return {"name": "", "found": False, "path": "", "content": ""}
    names = [normalized]
    alias = _normalize_text(_SKILL_ALIASES.get(normalized), "")
    if alias:
        names.append(alias)
    for root in _skill_search_roots():
        for name in names:
            skill_file = root / name / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                content = skill_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            cleaned = _normalize_text(content, "")
            if not cleaned:
                continue
            return {
                "name": normalized,
                "found": True,
                "path": str(skill_file),
                "content": cleaned,
            }
    return {"name": normalized, "found": False, "path": "", "content": ""}


def _load_skill_docs(load_skills: List[str]) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for skill in load_skills:
        item = _load_skill_content(skill)
        if item.get("found"):
            docs.append(item)
    return docs


def _build_skill_content_text(skill_docs: List[Dict[str, Any]]) -> str:
    if not skill_docs:
        return ""
    max_chars_raw = _normalize_text(os.getenv("PPT_SUBAGENT_SKILL_CONTENT_MAX_CHARS", "40000"), "40000")
    try:
        max_chars = max(2000, int(max_chars_raw))
    except Exception:
        max_chars = 40000
    sections: List[str] = []
    for item in skill_docs:
        name = _normalize_text(item.get("name"), "unknown")
        path = _normalize_text(item.get("path"), "")
        content = _normalize_text(item.get("content"), "")
        if not content:
            continue
        sections.append(f"## Skill: {name}\nSource: {path}\n\n{content}")
    joined = "\n\n---\n\n".join(sections)
    if len(joined) <= max_chars:
        return joined
    return joined[: max_chars - 14] + "\n\n[TRUNCATED]"


def _build_page_guidance_text(payload: Dict[str, Any], runtime_context: Dict[str, Any] | None = None) -> str:
    lines: List[str] = []
    slide_type = _normalize_text(payload.get("slide_type"), "content")
    layout_grid = _normalize_text(payload.get("layout_grid"), "split_2")
    render_path = _normalize_text(payload.get("render_path"), "svg")
    lines.append(f"Slide type: {slide_type}")
    lines.append(f"Layout grid: {layout_grid}")
    lines.append(f"Render path: {render_path}")

    runtime_ctx = runtime_context if isinstance(runtime_context, dict) else {}
    directives_raw = runtime_ctx.get("page_skill_directives")
    if not isinstance(directives_raw, list):
        directives_raw = payload.get("skill_directives")
    directives = [
        _normalize_text(item, "")
        for item in _as_list(directives_raw)
        if _normalize_text(item, "")
    ]
    if directives:
        lines.append("Page directives:")
        lines.extend([f"- {item}" for item in directives])

    text_constraints = runtime_ctx.get("text_constraints")
    if not isinstance(text_constraints, dict):
        text_constraints = payload.get("text_constraints")
    if isinstance(text_constraints, dict) and text_constraints:
        lines.append("Text constraints:")
        for key, value in text_constraints.items():
            lines.append(f"- {key}: {value}")

    image_policy = runtime_ctx.get("image_policy")
    if not isinstance(image_policy, dict):
        image_policy = payload.get("image_policy")
    if isinstance(image_policy, dict) and image_policy:
        lines.append("Image policy:")
        for key, value in image_policy.items():
            lines.append(f"- {key}: {value}")

    page_design_intent = _normalize_text(
        runtime_ctx.get("page_design_intent") or payload.get("page_design_intent"),
        "",
    )
    if page_design_intent:
        lines.append(f"Page design intent: {page_design_intent}")

    text = "\n".join(lines).strip()
    return text


def _build_llm_input(
    payload: Dict[str, Any],
    prompt: str,
    skill_hints: List[str],
    skill_content: str,
    page_guidance: str,
) -> Dict[str, Any]:
    prompt_text = _normalize_text(prompt, "")
    hints = [_normalize_text(item, "") for item in _as_list(skill_hints) if _normalize_text(item, "")]
    skill_context = _normalize_text(skill_content, "")
    user_skill_block = (
        "Loaded skill specifications:\n\n"
        f"{skill_context}\n\n"
        if skill_context
        else "Loaded skill specifications:\nnone\n\n"
    )
    return {
        "model": _resolve_content_model(""),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a PPT slide retry specialist. "
                    "When skill specifications are provided, treat them as implementation constraints. "
                    "Return strict JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt_text}\n\n"
                    f"Skill hints:\n- " + "\n- ".join(hints or ["none"]) + "\n\n"
                    + (
                        "Page-specific guidance:\n"
                        f"{_normalize_text(page_guidance, 'none')}\n\n"
                    )
                    + user_skill_block +
                    "Return JSON with keys: "
                    "slide_patch(object), load_skills(string[] optional), notes(string optional)."
                ),
            },
        ],
        "task_payload": payload,
    }


def _create_openai_client() -> tuple[Optional[OpenAI], str, str]:
    aiberm_base = _normalize_text(os.getenv("AIBERM_API_BASE", ""), "")
    aiberm_key = _normalize_text(os.getenv("AIBERM_API_KEY", ""), "")
    if aiberm_base and aiberm_key:
        model = _resolve_content_model("openai/gpt-4.1-mini")
        client = OpenAI(
            api_key=aiberm_key,
            base_url=aiberm_base,
        )
        return client, model, "aiberm"

    openrouter_key = _normalize_text(os.getenv("OPENROUTER_API_KEY", ""), "")
    if openrouter_key:
        model = _resolve_content_model("openai/gpt-4.1-mini")
        client = OpenAI(
            api_key=openrouter_key,
            base_url=_normalize_text(os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"), "https://openrouter.ai/api/v1"),
        )
        return client, model, "openrouter"

    openai_key = _normalize_text(os.getenv("OPENAI_API_KEY", ""), "")
    if openai_key:
        model = _normalize_openai_model_id(_resolve_content_model("gpt-4.1-mini"))
        client = OpenAI(api_key=openai_key)
        return client, model, "openai"
    return None, "", ""


def _parse_json_object(raw_text: str) -> Dict[str, Any]:
    text = _normalize_text(raw_text, "")
    if not text:
        return {}
    try:
        obj = json.loads(text)
        obj = _sanitize_tree_surrogates(obj)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    for line in reversed(text.splitlines()):
        row = line.strip()
        if not row.startswith("{"):
            continue
        try:
            obj = json.loads(row)
            obj = _sanitize_tree_surrogates(obj)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


def _invoke_llm_with_openai(llm_input: Dict[str, Any]) -> Dict[str, Any]:
    client, model, _provider = _create_openai_client()
    if client is None:
        return {"skipped": True, "reason": "llm_credentials_missing"}
    messages = llm_input.get("messages") if isinstance(llm_input.get("messages"), list) else []
    messages = _sanitize_tree_surrogates(messages) if isinstance(messages, list) else []
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = ""
        choices = getattr(response, "choices", None) or []
        if choices:
            content = _normalize_text(getattr(choices[0].message, "content", ""), "")
        parsed = _parse_json_object(content)
        if parsed:
            return parsed
        return {"skipped": True, "reason": "llm_invalid_json"}
    except Exception as exc:
        return {"skipped": True, "reason": _normalize_text(str(exc), "llm_invoke_failed")}


def _sanitize_patch(patch: Any) -> Dict[str, Any]:
    if not isinstance(patch, dict):
        return {}
    mojibake_tokens = ("?", "\ufffd", "?", "?", "?", "?", "?", "?")

    def _has_mojibake(value: Any) -> bool:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return False
            if any(token in text for token in mojibake_tokens):
                return True
            question_count = text.count("?")
            return question_count >= 3 and (question_count / max(1, len(text))) >= 0.15
        if isinstance(value, list):
            return any(_has_mojibake(item) for item in value)
        if isinstance(value, dict):
            return any(_has_mojibake(item) for item in value.values())
        return False

    allowed = {
        "slide_type",
        "layout_grid",
        "template_family",
        "skill_profile",
        "render_path",
    }
    out: Dict[str, Any] = {}
    for key, value in patch.items():
        if key in allowed:
            out[key] = value
    return out


def _merge_slide_payload(payload: Dict[str, Any], *patches: Dict[str, Any]) -> Dict[str, Any]:
    base = dict(payload or {})
    slide_data = base.get("slide_data") if isinstance(base.get("slide_data"), dict) else {}
    merged_slide_data = dict(slide_data)
    for patch in patches:
        safe = _sanitize_patch(patch)
        if not safe:
            continue
        base.update(safe)
        merged_slide_data.update(safe)
    base["slide_data"] = merged_slide_data
    return base


def _skill_runtime_enabled() -> bool:
    return _normalize_text(os.getenv("PPT_SUBAGENT_ENABLE_SKILL_RUNTIME", "true"), "true").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _runtime_role() -> str:
    explicit = _normalize_text(os.getenv("PPT_EXECUTION_ROLE", "auto"), "auto").lower()
    if explicit in {"worker", "web"}:
        return explicit
    if _normalize_text(os.getenv("VERCEL", ""), "") or _normalize_text(os.getenv("VERCEL_ENV", ""), ""):
        return "web"
    return "worker"


def _installed_skill_exec_enabled() -> bool:
    explicit = _normalize_text(os.getenv("PPT_INSTALLED_SKILL_EXECUTOR_ENABLED", ""), "").lower()
    if explicit:
        return explicit not in {"0", "false", "no", "off"}
    # Strict alignment: enabled by default across roles.
    return True


def _parse_command_args(raw_value: str) -> List[str]:
    text = _normalize_text(raw_value, "")
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [_normalize_text(item, "") for item in parsed if _normalize_text(item, "")]
    except Exception:
        pass
    try:
        return [item for item in shlex.split(text, posix=False) if _normalize_text(item, "")]
    except Exception:
        return [item for item in text.split() if _normalize_text(item, "")]


def _invoke_installed_skill_executor(
    *,
    payload: Dict[str, Any],
    requested_skills: List[str],
) -> Dict[str, Any]:
    enabled = _installed_skill_exec_enabled()
    if not enabled:
        return {
            "enabled": False,
            "reason": "installed_skill_executor_disabled",
            "patch": {},
            "trace": [],
            "context": {},
        }

    bin_name = _normalize_text(os.getenv("PPT_INSTALLED_SKILL_EXECUTOR_BIN", ""), "uv")
    args = _parse_command_args(os.getenv("PPT_INSTALLED_SKILL_EXECUTOR_ARGS", ""))
    if not args:
        args = ["run", "python", "-m", "src.installed_skill_executor"]

    req_payload = {
        "version": 1,
        "requested_skills": requested_skills,
        "slide": payload,
    }
    cwd = _normalize_text(os.getenv("PPT_INSTALLED_SKILL_EXECUTOR_CWD", ""), "")
    if not cwd:
        cwd = str(Path(__file__).resolve().parents[1])
    try:
        proc = subprocess.run(
            [bin_name, *args],
            input=json.dumps(req_payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, int(os.getenv("PPT_INSTALLED_SKILL_EXECUTOR_TIMEOUT_SEC", "30"))),
            check=False,
            cwd=cwd,
        )
    except Exception as exc:
        return {
            "enabled": True,
            "reason": f"installed_skill_executor_failed:{_normalize_text(str(exc), 'invoke_error')}",
            "patch": {},
            "trace": [],
            "context": {},
        }

    if int(proc.returncode) != 0:
        stderr = _normalize_text(proc.stderr, "")
        stdout = _normalize_text(proc.stdout, "")
        detail = stderr or stdout or f"exit_{proc.returncode}"
        return {
            "enabled": True,
            "reason": f"installed_skill_executor_nonzero:{detail[:180]}",
            "patch": {},
            "trace": [],
            "context": {},
        }

    parsed = _parse_json_object(_normalize_text(proc.stdout, ""))
    if not parsed:
        return {
            "enabled": True,
            "reason": "installed_skill_executor_invalid_output",
            "patch": {},
            "trace": [],
            "context": {},
        }

    patch = _sanitize_patch(parsed.get("patch") or parsed.get("slide_patch"))
    context = parsed.get("context") if isinstance(parsed.get("context"), dict) else {}
    trace: List[Dict[str, Any]] = []
    results = parsed.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            skill = _normalize_text(item.get("skill"), "")
            if not skill:
                continue
            row_patch = _sanitize_patch(item.get("patch") or item.get("slide_patch"))
            note = _normalize_text(item.get("note"), "")
            status = _normalize_text(item.get("status"), "noop").lower()
            trace.append(
                {
                    "skill": skill,
                    "status": status or ("applied" if row_patch else "noop"),
                    "patch_keys": sorted(row_patch.keys()),
                    "note": note,
                    "source": "installed_skill_executor",
                }
            )
            if row_patch:
                patch.update(row_patch)
    else:
        for skill in requested_skills:
            trace.append(
                {
                    "skill": skill,
                    "status": "applied" if patch else "noop",
                    "patch_keys": sorted(patch.keys()),
                    "note": _normalize_text(parsed.get("note"), ""),
                    "source": "installed_skill_executor",
                }
            )
    return {
        "enabled": True,
        "reason": "",
        "patch": patch,
        "trace": trace,
        "context": context,
    }


def build_subagent_graph(model_invoke: Optional[ModelInvoke] = None):
    def prepare(state: SubagentState) -> SubagentState:
        payload = state.get("task_payload") or {}
        load_skills = _dedupe_skills(payload.get("load_skills"))
        prompt = _normalize_text(payload.get("prompt"), "Refine this slide.")
        skill_docs = _load_skill_docs(load_skills)
        skill_content = _build_skill_content_text(skill_docs)
        skill_hints = [f"load_skill:{item}" for item in load_skills]
        loaded_names = [
            _normalize_text(item.get("name"), "")
            for item in skill_docs
            if _normalize_text(item.get("name"), "")
        ]
        if loaded_names:
            skill_hints.append("loaded_skill_specs:" + ",".join(loaded_names))
        page_guidance = _build_page_guidance_text(payload)
        return {
            "task_payload": payload,
            "prompt": prompt,
            "skill_hints": skill_hints,
            "skill_docs": skill_docs,
            "skill_content": skill_content,
            "page_guidance": page_guidance,
            "skill_runtime_patch": {},
            "skill_runtime_context": {},
            "skill_runtime_trace": [],
            "tool_patch": {},
            "llm_patch": {},
            "skipped": False,
            "runtime_error": False,
            "reason": "",
            "notes": "",
        }

    def run_skill_runtime(state: SubagentState) -> SubagentState:
        payload = state.get("task_payload") or {}
        requested_skills = _dedupe_skills(payload.get("load_skills"))
        if not _skill_runtime_enabled() or not requested_skills:
            return {"skill_runtime_patch": {}, "skill_runtime_trace": []}

        runtime_patch: Dict[str, Any] = {}
        trace: List[Dict[str, Any]] = []
        skill_hints = list(state.get("skill_hints") or [])

        installed = _invoke_installed_skill_executor(
            payload=_merge_slide_payload(payload),
            requested_skills=requested_skills,
        )
        if not bool(installed.get("enabled")):
            reason = _normalize_text(installed.get("reason"), "installed_skill_executor_disabled")
            return {
                "skill_runtime_patch": {},
                "skill_runtime_trace": [
                    {
                        "skill": "installed-skill-executor",
                        "status": "error",
                        "reason": reason,
                        "source": "installed_skill_executor",
                    }
                ],
                "runtime_error": True,
                "skipped": True,
                "reason": reason,
            }
        installed_patch = _sanitize_patch(installed.get("patch"))
        installed_context = (
            _sanitize_tree_surrogates(installed.get("context"))
            if isinstance(installed.get("context"), dict)
            else {}
        )
        if installed_patch:
            runtime_patch.update(installed_patch)
        installed_trace = installed.get("trace") if isinstance(installed.get("trace"), list) else []
        installed_applied_skills: set[str] = set()
        for item in installed_trace:
            if not isinstance(item, dict):
                continue
            skill = _normalize_text(item.get("skill"), "").lower()
            if not skill:
                continue
            status = _normalize_text(item.get("status"), "noop").lower()
            if status in {"applied", "noop"}:
                installed_applied_skills.add(skill)
            trace.append(item)

        reason = _normalize_text(installed.get("reason"), "")
        if reason:
            trace.append(
                {
                    "skill": "installed-skill-executor",
                    "status": "error",
                    "reason": reason,
                    "source": "installed_skill_executor",
                }
            )
            return {
                "skill_runtime_patch": runtime_patch,
                "skill_runtime_context": installed_context,
                "skill_runtime_trace": trace,
                "runtime_error": True,
                "skipped": True,
                "reason": reason,
            }

        unresolved_skills = [skill for skill in requested_skills if skill not in installed_applied_skills]
        if unresolved_skills:
            unresolved = ",".join(unresolved_skills)
            unresolved_reason = f"installed_skill_unresolved:{unresolved}"
            trace.append(
                {
                    "skill": "installed-skill-executor",
                    "status": "error",
                    "reason": unresolved_reason,
                    "source": "installed_skill_executor",
                }
            )
            return {
                "skill_runtime_patch": runtime_patch,
                "skill_runtime_context": installed_context,
                "skill_runtime_trace": trace,
                "runtime_error": True,
                "skipped": True,
                "reason": unresolved_reason,
            }
        page_guidance = _build_page_guidance_text(
            payload,
            installed_context,
        )
        return {
            "skill_runtime_patch": runtime_patch,
            "skill_runtime_context": installed_context,
            "skill_runtime_trace": trace,
            "page_guidance": page_guidance,
            "skill_hints": skill_hints,
            "task_payload": {
                **payload,
                "load_skills": requested_skills,
            },
        }

    def apply_tools(state: SubagentState) -> SubagentState:
        payload = state.get("task_payload") or {}
        payload_view = _merge_slide_payload(payload, state.get("skill_runtime_patch") or {})
        slide_type = _normalize_text(payload_view.get("slide_type"), "content")
        render_path = _normalize_text(payload_view.get("render_path"), "svg")
        slide_data = payload_view.get("slide_data") if isinstance(payload_view.get("slide_data"), dict) else {}
        layout_grid = _normalize_text(
            payload_view.get("layout_grid") or slide_data.get("layout_grid"),
            "",
        )
        recommended_render_path = recommend_render_path.invoke(
            {"slide_type": slide_type, "current_render_path": render_path}
        )
        recommended_layout = recommend_layout_grid.invoke(
            {"slide_type": slide_type, "layout_grid": layout_grid}
        )
        tool_patch: Dict[str, Any] = {}
        if _normalize_text(recommended_render_path, "").lower() != render_path.lower():
            tool_patch["render_path"] = _normalize_text(
                recommended_render_path, "svg"
            ).lower()
        if recommended_layout and recommended_layout != layout_grid:
            tool_patch["layout_grid"] = recommended_layout
        skill_hints = list(state.get("skill_hints") or [])
        if tool_patch:
            skill_hints.append(f"tool_patch:{json.dumps(tool_patch, ensure_ascii=False)}")
        return {"tool_patch": tool_patch, "skill_hints": skill_hints}

    def call_llm(state: SubagentState) -> SubagentState:
        if bool(state.get("runtime_error", False)):
            return {
                "llm_patch": {},
                "notes": _normalize_text(state.get("notes"), ""),
                "skipped": True,
                "reason": _normalize_text(state.get("reason"), "runtime_error"),
            }
        payload = state.get("task_payload") or {}
        payload_view = _merge_slide_payload(
            payload,
            state.get("skill_runtime_patch") or {},
            state.get("tool_patch") or {},
        )
        llm_input = _build_llm_input(
            payload_view,
            _normalize_text(state.get("prompt"), "Refine this slide."),
            state.get("skill_hints") or [],
            _normalize_text(state.get("skill_content"), ""),
            _normalize_text(state.get("page_guidance"), ""),
        )
        llm_output = model_invoke(llm_input) if callable(model_invoke) else _invoke_llm_with_openai(llm_input)
        skipped = bool(llm_output.get("skipped"))
        reason = _normalize_text(llm_output.get("reason"), "")
        llm_patch = _sanitize_patch(llm_output.get("slide_patch"))
        notes = _normalize_text(llm_output.get("notes"), "")
        llm_skills = _dedupe_skills(llm_output.get("load_skills"))
        existing_skills = _as_list(payload.get("load_skills"))
        return {
            "llm_patch": llm_patch,
            "notes": notes,
            "skipped": skipped,
            "reason": reason,
            "task_payload": {
                **payload,
                "load_skills": _dedupe_skills([*existing_skills, *llm_skills]),
            },
        }

    def finalize(state: SubagentState) -> SubagentState:
        payload = state.get("task_payload") or {}
        skill_runtime_patch = _sanitize_patch(state.get("skill_runtime_patch"))
        tool_patch = _sanitize_patch(state.get("tool_patch"))
        llm_patch = _sanitize_patch(state.get("llm_patch"))
        slide_patch = {**skill_runtime_patch, **tool_patch, **llm_patch}
        output = {
            "ok": not bool(state.get("runtime_error", False)),
            "skipped": bool(state.get("skipped", False)),
            "reason": _normalize_text(state.get("reason"), ""),
            "slide_patch": slide_patch,
            "load_skills": _dedupe_skills(payload.get("load_skills", [])),
            "notes": _normalize_text(state.get("notes"), ""),
            "skill_runtime": {
                "enabled": _skill_runtime_enabled(),
                "trace": state.get("skill_runtime_trace") if isinstance(state.get("skill_runtime_trace"), list) else [],
            },
        }
        return {"output": output}

    graph = StateGraph(SubagentState)
    graph.add_node("prepare", prepare)
    graph.add_node("run_skill_runtime", run_skill_runtime)
    graph.add_node("apply_tools", apply_tools)
    graph.add_node("call_llm", call_llm)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "run_skill_runtime")
    graph.add_edge("run_skill_runtime", "apply_tools")
    graph.add_edge("apply_tools", "call_llm")
    graph.add_edge("call_llm", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def execute_subagent_task(task_payload: Dict[str, Any], model_invoke: Optional[ModelInvoke] = None) -> Dict[str, Any]:
    app = build_subagent_graph(model_invoke=model_invoke)
    result = app.invoke({"task_payload": task_payload if isinstance(task_payload, dict) else {}})
    output = result.get("output") if isinstance(result, dict) else None
    if isinstance(output, dict):
        return output
    return {"ok": False, "skipped": True, "reason": "executor_output_missing", "slide_patch": {}}


def _read_stdin_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    obj = _parse_json_object(raw)
    return obj if isinstance(obj, dict) else {}


def _write_json_stdout(payload: Dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(raw.encode("utf-8", errors="replace"))
    else:
        sys.stdout.write(raw)
    sys.stdout.flush()


def main() -> int:
    payload = _read_stdin_payload()
    output = execute_subagent_task(payload)
    _write_json_stdout(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
