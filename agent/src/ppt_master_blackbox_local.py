"""Local skill runtime for prompt-direct ppt-master execution.

This module intentionally does NOT use Codex CLI. It executes a local runtime
that:
1) loads ppt-master skill metadata/workflow docs,
2) registers runtime tools,
3) executes the skill entry workflow through local project services/tools.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


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


def _run(
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
        raise RuntimeError(f"ppt_master_command_timeout: {' '.join(list(cmd)[:4])}") from exc
    return int(proc.returncode), str(proc.stdout or ""), str(proc.stderr or "")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


@dataclass
class SkillStep:
    title: str
    blocking: bool


@dataclass
class SkillDefinition:
    name: str
    description: str
    source_path: str
    workflow_steps: List[SkillStep] = field(default_factory=list)
    scripts: Dict[str, str] = field(default_factory=dict)


@dataclass
class RuntimeTraceRow:
    step: str
    tool: str
    started_at: str
    finished_at: str
    ok: bool
    meta: Dict[str, Any] = field(default_factory=dict)


class PPTMasterSkillLoader:
    def __init__(self, *, skill_root: Path) -> None:
        self.skill_root = skill_root
        self.skill_file = skill_root / "SKILL.md"

    def load(self) -> SkillDefinition:
        if not self.skill_file.exists():
            raise RuntimeError(f"ppt_master_skill_missing:{self.skill_file}")

        raw = self.skill_file.read_text(encoding="utf-8", errors="ignore")
        frontmatter = self._parse_frontmatter(raw)
        steps = self._parse_steps(raw)
        scripts = self._parse_scripts(raw)
        return SkillDefinition(
            name=_text(frontmatter.get("name"), "ppt-master"),
            description=_text(frontmatter.get("description"), "ppt-master skill"),
            source_path=str(self.skill_file),
            workflow_steps=steps,
            scripts=scripts,
        )

    @staticmethod
    def _parse_frontmatter(raw: str) -> Dict[str, str]:
        match = re.match(r"(?s)\A---\s*\n(.*?)\n---\s*\n", raw)
        if not match:
            return {}
        body = match.group(1)
        out: Dict[str, str] = {}
        for line in body.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            k = _text(key, "").lower()
            v = _text(value, "")
            if k:
                out[k] = v
        return out

    @staticmethod
    def _parse_steps(raw: str) -> List[SkillStep]:
        steps: List[SkillStep] = []
        for match in re.finditer(r"(?m)^###\s+Step\s+\d+:\s*(.+)$", raw):
            title = _text(match.group(1), "")
            if not title:
                continue
            blocking = "BLOCKING" in title.upper()
            steps.append(SkillStep(title=title, blocking=blocking))
        return steps

    @staticmethod
    def _parse_scripts(raw: str) -> Dict[str, str]:
        scripts: Dict[str, str] = {}
        in_table = False
        for line in raw.splitlines():
            row = line.strip()
            if row.startswith("| Script |"):
                in_table = True
                continue
            if in_table and not row.startswith("|"):
                break
            if in_table and row.startswith("|"):
                cells = [c.strip() for c in row.strip("|").split("|")]
                if len(cells) < 2:
                    continue
                script = _text(cells[0], "")
                purpose = _text(cells[1], "")
                if script and script != "Script" and not set(script) <= {"-"}:
                    scripts[script] = purpose
        return scripts


class SkillToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        key = _text(name, "")
        if not key:
            raise ValueError("tool_name_required")
        self._tools[key] = fn

    def list_tools(self) -> List[str]:
        return sorted(self._tools.keys())

    def invoke(self, name: str, **kwargs: Any) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise RuntimeError(f"tool_not_registered:{name}")
        return tool(**kwargs)


class PPTMasterSkillExecutor:
    def __init__(
        self,
        *,
        skill: SkillDefinition,
        registry: SkillToolRegistry,
        skill_root: Path,
    ) -> None:
        self.skill = skill
        self.registry = registry
        self.skill_root = skill_root

    def execute(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = _text(request_payload.get("prompt"), "")
        if not prompt:
            raise RuntimeError("missing_prompt")

        project_name = _text(request_payload.get("project_name"), "")
        if not project_name:
            project_name = f"ai_gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        output_base = Path(
            _text(
                request_payload.get("output_base_dir"),
                str(Path(__file__).resolve().parents[2] / "output" / "ppt_master_projects"),
            )
        )
        output_base.mkdir(parents=True, exist_ok=True)
        timeout_sec = max(120, min(7200, _to_int(request_payload.get("timeout_sec"), 3600)))
        include_images = _to_bool(request_payload.get("include_images"), False)

        trace_rows: List[RuntimeTraceRow] = []
        project_path = self._invoke_with_trace(
            trace_rows,
            step="step_2_project_init",
            tool="project.init",
            project_name=project_name,
            output_base=output_base,
            timeout_sec=min(timeout_sec, 240),
        )
        if not isinstance(project_path, Path):
            project_path = Path(str(project_path))
        project_path.mkdir(parents=True, exist_ok=True)

        runtime_request_path = project_path / "runtime_request.json"
        runtime_request_path.write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (project_path / "prompt.txt").write_text(prompt, encoding="utf-8")
        (project_path / "skill_manifest.json").write_text(
            json.dumps(
                {
                    "skill_name": self.skill.name,
                    "skill_description": self.skill.description,
                    "skill_source": self.skill.source_path,
                    "workflow_steps": [
                        {"title": row.title, "blocking": row.blocking}
                        for row in self.skill.workflow_steps
                    ],
                    "registered_tools": self.registry.list_tools(),
                    "scripts": self.skill.scripts,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        pipeline_obj = self._invoke_with_trace(
            trace_rows,
            step="step_4_6_7_pipeline_run",
            tool="pipeline.run",
            request_payload=request_payload,
            project_path=project_path,
            timeout_sec=timeout_sec,
        )
        if not isinstance(pipeline_obj, dict):
            raise RuntimeError("pipeline_result_invalid")
        (project_path / "pipeline_result.json").write_text(
            json.dumps(pipeline_obj, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        artifacts_obj = pipeline_obj.get("artifacts") if isinstance(pipeline_obj.get("artifacts"), dict) else {}
        render_payload = (
            artifacts_obj.get("render_payload")
            if isinstance(artifacts_obj.get("render_payload"), dict)
            else {}
        )
        design_spec_path = self._invoke_with_trace(
            trace_rows,
            step="step_design_spec_materialize",
            tool="design_spec.materialize",
            project_path=project_path,
            request_payload=request_payload,
            render_payload=render_payload,
        )
        if not isinstance(design_spec_path, str):
            design_spec_path = str(project_path / "design_spec.json")

        image_status = {"status": "disabled", "reason": "include_images_false"}
        if include_images:
            image_status_obj = self._invoke_with_trace(
                trace_rows,
                step="step_5_image_generator",
                tool="image.generate_cover",
                project_path=project_path,
                request_payload=request_payload,
                timeout_sec=min(timeout_sec, 240),
            )
            if isinstance(image_status_obj, dict):
                image_status = {
                    "status": _text(image_status_obj.get("status"), "failed"),
                    "reason": _text(image_status_obj.get("reason"), "unknown"),
                }
            else:
                image_status = {"status": "failed", "reason": "image_tool_invalid_result"}

        runtime_trace_path = project_path / "runtime_trace.json"
        runtime_trace_path.write_text(
            json.dumps(
                {
                    "started_at": trace_rows[0].started_at if trace_rows else _utc_now(),
                    "finished_at": _utc_now(),
                    "rows": [
                        {
                            "step": row.step,
                            "tool": row.tool,
                            "started_at": row.started_at,
                            "finished_at": row.finished_at,
                            "ok": row.ok,
                            "meta": row.meta,
                        }
                        for row in trace_rows
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        export_obj = pipeline_obj.get("export") if isinstance(pipeline_obj.get("export"), dict) else {}
        export = dict(export_obj)
        export["generator_mode"] = "ppt_master_skill_runtime_local_skill"
        export["project_name"] = project_path.name

        notes_total_path = str(project_path / "notes" / "total.md")
        if not Path(notes_total_path).exists():
            notes_total_path = ""

        result = {
            "export": export,
            "artifacts": {
                "project_path": str(project_path),
                "source_md": "",
                "design_spec": design_spec_path,
                "notes_total": notes_total_path,
                "research_notes": "",
                "runtime_request": str(runtime_request_path),
                "pipeline_result": str(project_path / "pipeline_result.json"),
                "runtime_trace": str(runtime_trace_path),
                "skill_manifest": str(project_path / "skill_manifest.json"),
                "image_status": image_status["status"],
                "image_reason": image_status["reason"],
            },
        }
        (project_path / "runtime_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result

    def _invoke_with_trace(
        self,
        trace_rows: List[RuntimeTraceRow],
        *,
        step: str,
        tool: str,
        **kwargs: Any,
    ) -> Any:
        started_at = _utc_now()
        try:
            out = self.registry.invoke(tool, **kwargs)
            finished_at = _utc_now()
            trace_rows.append(
                RuntimeTraceRow(
                    step=step,
                    tool=tool,
                    started_at=started_at,
                    finished_at=finished_at,
                    ok=True,
                    meta={"keys": sorted(list(kwargs.keys()))},
                )
            )
            return out
        except Exception as exc:
            finished_at = _utc_now()
            trace_rows.append(
                RuntimeTraceRow(
                    step=step,
                    tool=tool,
                    started_at=started_at,
                    finished_at=finished_at,
                    ok=False,
                    meta={"error": str(exc), "keys": sorted(list(kwargs.keys()))},
                )
            )
            raise


def _tool_project_init(
    *,
    project_name: str,
    output_base: Path,
    timeout_sec: int,
) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / "vendor" / "minimax-skills" / "skills" / "ppt-master" / "scripts"
    cmd = [
        sys.executable,
        str(scripts_dir / "project_manager.py"),
        "init",
        project_name,
        "--format",
        "ppt169",
        "--dir",
        str(output_base),
    ]
    code, stdout, stderr = _run(cmd=cmd, cwd=scripts_dir, timeout_sec=timeout_sec)
    if code != 0:
        raise RuntimeError(f"ppt_master_project_init_failed:{_text(stderr or stdout, f'exit_{code}')}")
    match = re.search(r"Project initialized:\s*(.+)", f"{stdout}\n{stderr}")
    if match:
        candidate = Path(match.group(1).strip())
        if candidate.exists():
            return candidate
    date_str = datetime.now().strftime("%Y%m%d")
    fallback = output_base / f"{project_name}_ppt169_{date_str}"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _tool_web_search(*, query: str, language: str) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    adapter = repo_root / "agent" / "src" / "ppt_master_web_adapter.py"
    cmd = [
        sys.executable,
        str(adapter),
        "search",
        "--query",
        _text(query, ""),
        "--num",
        "5",
        "--language",
        "zh-CN" if _text(language, "zh-CN") == "zh-CN" else "en-US",
    ]
    code, stdout, stderr = _run(cmd=cmd, cwd=adapter.parent, timeout_sec=30)
    if code != 0:
        return {"ok": False, "error": _text(stderr or stdout, f"exit_{code}"), "items": []}
    try:
        parsed = json.loads(stdout) if stdout.strip() else {}
    except Exception:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {"ok": False, "error": "invalid_search_output", "items": []}


def _tool_web_fetch(*, url: str) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    adapter = repo_root / "agent" / "src" / "ppt_master_web_adapter.py"
    cmd = [
        sys.executable,
        str(adapter),
        "fetch",
        "--url",
        _text(url, ""),
        "--max-chars",
        "6000",
    ]
    code, stdout, stderr = _run(cmd=cmd, cwd=adapter.parent, timeout_sec=30)
    if code != 0:
        return {"ok": False, "error": _text(stderr or stdout, f"exit_{code}")}
    try:
        parsed = json.loads(stdout) if stdout.strip() else {}
    except Exception:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {"ok": False, "error": "invalid_fetch_output"}


def _tool_run_pipeline(
    *,
    request_payload: Dict[str, Any],
    project_path: Path,
    timeout_sec: int,
) -> Dict[str, Any]:
    from src.ppt_service_v2 import PPTService
    from src.schemas.ppt_pipeline import PPTPipelineRequest

    prompt = _text(request_payload.get("prompt"), "")
    if not prompt:
        raise RuntimeError("pipeline_missing_prompt")

    total_pages = max(3, min(50, _to_int(request_payload.get("total_pages"), 12)))
    language = "en-US" if _text(request_payload.get("language"), "zh-CN") == "en-US" else "zh-CN"
    style = _text(request_payload.get("style"), "academic" if language == "zh-CN" else "professional")
    template_family = _text(request_payload.get("template_family"), "auto")

    route_mode = _text(
        request_payload.get("route_mode"),
        _text(os.getenv("PPT_MASTER_ROUTE_MODE", "refine"), "refine"),
    )
    if route_mode not in {"auto", "fast", "standard", "refine"}:
        route_mode = "refine"

    quality_profile = _text(
        request_payload.get("quality_profile"),
        _text(os.getenv("PPT_MASTER_QUALITY_PROFILE", "high_density_consulting"), "high_density_consulting"),
    )
    execution_profile = _text(
        request_payload.get("execution_profile"),
        _text(os.getenv("PPT_MASTER_EXECUTION_PROFILE", "prod_safe"), "prod_safe"),
    )
    if execution_profile not in {"auto", "dev_strict", "prod_safe"}:
        execution_profile = "prod_safe"

    if language == "zh-CN":
        audience_default = "大学课堂"
        purpose_default = "课堂展示课件"
    else:
        audience_default = "college classroom"
        purpose_default = "classroom presentation"
    audience = _text(request_payload.get("audience"), audience_default)
    purpose = _text(request_payload.get("purpose"), purpose_default)

    constraints: List[str] = []
    raw_constraints = request_payload.get("constraints")
    if isinstance(raw_constraints, list):
        for item in raw_constraints:
            row = _text(item, "")
            if row and row not in constraints:
                constraints.append(row)
    elif isinstance(raw_constraints, str):
        row = _text(raw_constraints, "")
        if row:
            constraints.append(row)
    if not constraints:
        if language == "zh-CN":
            constraints = [
                "按大学课堂讲授节奏组织内容",
                "包含地缘背景、关键事件时间线、国际关系影响机制",
                "给出案例、数据证据与政策建议",
            ]
        else:
            constraints = [
                "Use classroom pacing and clear sectioning",
                "Include geopolitical background, timeline, and IR impact mechanisms",
                "Include case evidence, key data points, and policy implications",
            ]

    web_enrichment = _to_bool(
        request_payload.get("web_enrichment"),
        _to_bool(os.getenv("PPT_MASTER_WEB_ENRICHMENT", "true"), True),
    )
    image_asset_enrichment = _to_bool(
        request_payload.get("image_asset_enrichment"),
        _to_bool(os.getenv("PPT_MASTER_IMAGE_ASSET_ENRICHMENT", "true"), True),
    )

    # Ensure local direct-runtime execution and avoid Codex CLI dependency.
    os.environ["PPT_DIRECT_SKILL_RUNTIME_MODE"] = "builtin"
    os.environ["PPT_DIRECT_SKILL_RUNTIME_REQUIRE"] = "true"
    os.environ["PPT_INSTALLED_SKILL_EXECUTOR_ENABLED"] = "true"
    os.environ["PPT_DEV_FAST_FAIL"] = "false"
    os.environ["PPT_DIRECT_SKILL_RUNTIME_BIN"] = str(Path(sys.executable).resolve())
    os.environ["PPT_DIRECT_SKILL_RUNTIME_ARGS"] = "-m src.ppt_direct_skill_runtime"
    os.environ["PPT_DIRECT_SKILL_RUNTIME_CWD"] = str(Path(__file__).resolve().parents[1])

    req = PPTPipelineRequest(
        topic=prompt,
        audience=audience,
        purpose=purpose,
        style_preference=style,
        constraints=constraints,
        web_enrichment=web_enrichment,
        image_asset_enrichment=image_asset_enrichment,
        total_pages=total_pages,
        language=language,
        title=prompt.strip()[:120],
        author="AutoViralVid",
        route_mode=route_mode,  # type: ignore[arg-type]
        export_channel="local",
        with_export=True,
        save_artifacts=True,
        template_family=template_family or "auto",
        force_ppt_master=True,
        quality_profile=quality_profile,
        execution_profile=execution_profile,  # type: ignore[arg-type]
    )
    service = PPTService()
    pipeline_timeout = max(120, min(int(timeout_sec or 3600), 7200))
    try:
        pipeline_result = asyncio.run(
            asyncio.wait_for(service.run_ppt_pipeline(req), timeout=float(pipeline_timeout))
        )
    except TimeoutError as exc:
        raise RuntimeError(f"pipeline_timeout_after:{pipeline_timeout}s") from exc

    payload = (
        pipeline_result.model_dump()
        if hasattr(pipeline_result, "model_dump")
        else dict(pipeline_result or {})
    )
    if not isinstance(payload, dict):
        raise RuntimeError("pipeline_output_not_dict")

    # Persist pipeline output under project path for runtime artifact consistency.
    (project_path / "pipeline_result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _tool_design_spec_materialize(
    *,
    project_path: Path,
    request_payload: Dict[str, Any],
    render_payload: Dict[str, Any],
) -> str:
    from src.ppt_master_design_spec import build_design_spec

    theme = render_payload.get("theme") if isinstance(render_payload.get("theme"), dict) else {}
    style_variant = _text(render_payload.get("style_variant"), "soft")
    theme_recipe = _text(render_payload.get("theme_recipe"), "auto")
    tone = _text(render_payload.get("tone"), "auto")
    template_family = _text(render_payload.get("template_family"), _text(request_payload.get("template_family"), "auto"))
    spec = build_design_spec(
        theme=theme,
        template_family=template_family,
        style_variant=style_variant,
        theme_recipe=theme_recipe,
        tone=tone,
        topic=_text(request_payload.get("prompt"), ""),
    )
    target = project_path / "design_spec.json"
    target.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def _tool_image_generate_cover(
    *,
    project_path: Path,
    request_payload: Dict[str, Any],
    timeout_sec: int,
) -> Dict[str, str]:
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / "vendor" / "minimax-skills" / "skills" / "ppt-master" / "scripts"
    image_script = scripts_dir / "image_gen.py"
    if not image_script.exists():
        return {"status": "failed", "reason": "image_gen_script_missing"}

    images_dir = project_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    model = _text(os.getenv("PPT_MASTER_IMAGE_MODEL"), "gemini-3.1-flash-image-preview")
    prompt = _text(request_payload.get("prompt"), "")[:240] or "presentation cover image"
    cmd = [
        sys.executable,
        str(image_script),
        prompt,
        "--aspect_ratio",
        "16:9",
        "--image_size",
        "1K",
        "-o",
        str(images_dir),
        "--backend",
        "openai",
        "--model",
        model,
    ]
    env = dict(os.environ)
    if _text(env.get("AIBERM_API_KEY"), ""):
        env["OPENAI_API_KEY"] = _text(env.get("AIBERM_API_KEY"), "")
    if _text(env.get("AIBERM_API_BASE"), ""):
        env["OPENAI_BASE_URL"] = _text(env.get("AIBERM_API_BASE"), "")
    code, stdout, stderr = _run(
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


def _build_tool_registry() -> SkillToolRegistry:
    registry = SkillToolRegistry()
    registry.register("project.init", _tool_project_init)
    registry.register("web.search", _tool_web_search)
    registry.register("web.fetch", _tool_web_fetch)
    registry.register("pipeline.run", _tool_run_pipeline)
    registry.register("design_spec.materialize", _tool_design_spec_materialize)
    registry.register("image.generate_cover", _tool_image_generate_cover)
    return registry


def run_blackbox_request(request_payload: Dict[str, Any]) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    skill_root = repo_root / "vendor" / "minimax-skills" / "skills" / "ppt-master"
    if not skill_root.exists():
        raise RuntimeError("ppt_master_assets_missing")

    loader = PPTMasterSkillLoader(skill_root=skill_root)
    skill = loader.load()
    registry = _build_tool_registry()
    executor = PPTMasterSkillExecutor(skill=skill, registry=registry, skill_root=skill_root)
    return executor.execute(dict(request_payload))
