"""Prompt -> PPT facade backed by black-box ppt-master skill runtime."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


class PPTMasterService:
    """Prompt-to-PPT service that directly invokes the ppt-master skill runtime."""

    def __init__(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.ppt_master_root = (
            self.repo_root / "vendor" / "minimax-skills" / "skills" / "ppt-master"
        )
        if not self.ppt_master_root.exists():
            raise RuntimeError(f"ppt-master not found at {self.ppt_master_root}")

        self.templates_dir = self.ppt_master_root / "templates"
        self.output_base = self.repo_root / "output" / "ppt_master_projects"
        self.output_base.mkdir(parents=True, exist_ok=True)

    async def generate_from_prompt(
        self,
        prompt: str,
        total_pages: int = 10,
        style: str = "professional",
        color_scheme: Optional[str] = None,
        language: str = "zh-CN",
        template_name: Optional[str] = None,
        template_family: Optional[str] = None,
        include_images: bool = False,
        web_enrichment: Optional[bool] = None,
        image_asset_enrichment: Optional[bool] = None,
    ) -> Dict[str, Any]:
        start_time = datetime.now()
        project_name = f"ai_gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        resolved_template = str(template_name or template_family or "").strip() or "auto"

        try:
            req = self._build_skill_runtime_request(
                prompt=prompt,
                project_name=project_name,
                total_pages=total_pages,
                style=style,
                color_scheme=color_scheme,
                language=language,
                template_family=resolved_template,
                include_images=include_images,
                web_enrichment=web_enrichment,
                image_asset_enrichment=image_asset_enrichment,
            )
            runtime_payload = await self._run_skill_runtime(req)
            if not isinstance(runtime_payload, dict):
                raise RuntimeError("ppt_master_skill_runtime_invalid_payload")

            export_data = dict(runtime_payload.get("export") or {})
            artifacts = dict(runtime_payload.get("artifacts") or {})

            project_path_raw = str(artifacts.get("project_path") or "").strip()
            project_path = (
                Path(project_path_raw)
                if project_path_raw
                else self.output_base / project_name
            )
            project_path.mkdir(parents=True, exist_ok=True)

            output_pptx = await self._materialize_pptx(
                export_data=export_data,
                project_path=project_path,
                project_name=project_name,
            )
            if output_pptx is None:
                raise RuntimeError("ppt_master_skill_runtime_missing_pptx")

            source_md = str(artifacts.get("source_md") or "").strip()
            design_spec_path = str(artifacts.get("design_spec") or "").strip()

            generated_content = {
                "prompt": prompt,
                "source_md": source_md,
                "design_spec": design_spec_path,
            }
            (project_path / "prompt.txt").write_text(prompt, encoding="utf-8")
            (project_path / "skill_result.json").write_text(
                json.dumps(runtime_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            end_time = datetime.now()
            generation_time = (end_time - start_time).total_seconds()

            return {
                "success": True,
                "project_name": project_path.name,
                "project_path": str(project_path),
                "total_slides": max(3, min(50, int(total_pages))),
                "generated_content": generated_content,
                "design_spec": {
                    "file": design_spec_path,
                    "content": "",
                    "total_pages": max(3, min(50, int(total_pages))),
                    "style": style,
                    "color_scheme": color_scheme,
                    "language": language,
                    "template_family": resolved_template,
                },
                "svg_files": list(export_data.get("slide_image_urls") or []),
                "output_pptx": str(output_pptx),
                "image_generation": {
                    "enabled": bool(include_images),
                    "status": (
                        str(artifacts.get("image_status") or "enabled")
                        if include_images
                        else "disabled"
                    ),
                    "reason": "handled_by_ppt_master_blackbox",
                },
                "artifacts": {
                    "project_path": str(project_path),
                    "skill_result": str(project_path / "skill_result.json"),
                    "prompt": str(project_path / "prompt.txt"),
                    "design_spec": design_spec_path,
                    "source_md": source_md,
                    "notes_total": str(artifacts.get("notes_total") or "").strip(),
                    "research_notes": str(artifacts.get("research_notes") or "").strip(),
                },
                "generation_time_seconds": generation_time,
            }
        except Exception as exc:
            failed_path = self.output_base / project_name
            failed_path.mkdir(parents=True, exist_ok=True)
            return {
                "success": False,
                "error": str(exc),
                "project_name": project_name,
                "project_path": str(failed_path),
            }

    def _build_skill_runtime_request(
        self,
        *,
        prompt: str,
        project_name: str,
        total_pages: int,
        style: str,
        color_scheme: Optional[str],
        language: str,
        template_family: str,
        include_images: bool,
        web_enrichment: Optional[bool],
        image_asset_enrichment: Optional[bool],
    ) -> Dict[str, Any]:
        resolved_web_enrichment = (
            bool(web_enrichment)
            if web_enrichment is not None
            else _env_bool("PPT_MASTER_WEB_ENRICHMENT", True)
        )
        resolved_image_asset_enrichment = (
            bool(image_asset_enrichment)
            if image_asset_enrichment is not None
            else _env_bool("PPT_MASTER_IMAGE_ASSET_ENRICHMENT", True)
        )
        return {
            "prompt": str(prompt or "").strip(),
            "project_name": project_name,
            "output_base_dir": str(self.output_base),
            "total_pages": max(3, min(50, int(total_pages))),
            "style": str(style or "professional").strip() or "professional",
            "color_scheme": str(color_scheme or "").strip(),
            "language": "en-US" if str(language).strip() == "en-US" else "zh-CN",
            "template_family": str(template_family or "auto").strip() or "auto",
            "include_images": bool(include_images),
            "web_enrichment": resolved_web_enrichment,
            "image_asset_enrichment": resolved_image_asset_enrichment,
            "timeout_sec": max(
                120,
                _env_int(
                    "PPT_MASTER_SKILL_TIMEOUT_SEC",
                    _env_int("PPT_MASTER_RUNTIME_TIMEOUT_SEC", 3600),
                ),
            ),
        }

    def _ensure_runtime_env(self) -> None:
        agent_root = Path(__file__).resolve().parents[1]
        os.environ.setdefault("PYTHONUTF8", "1")
        os.environ.setdefault("PPT_MASTER_SKILL_RUNTIME_BIN", str(Path(sys.executable).resolve()))
        os.environ.setdefault("PPT_MASTER_SKILL_RUNTIME_ARGS", "-m src.ppt_master_pipeline_runtime")
        os.environ.setdefault("PPT_MASTER_SKILL_RUNTIME_CWD", str(agent_root))

    async def _run_skill_runtime(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        runtime_mode = str(os.getenv("PPT_MASTER_RUNTIME_MODE") or "inproc").strip().lower()
        if runtime_mode in {"inproc", "local"}:
            from src.ppt_master_blackbox_local import run_blackbox_request

            return await asyncio.to_thread(run_blackbox_request, dict(request_payload))

        self._ensure_runtime_env()
        cmd = self._runtime_command()
        cwd = self._runtime_cwd()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=dict(os.environ),
        )
        payload = json.dumps({"request": request_payload}, ensure_ascii=False).encode("utf-8")
        stdout, stderr = await proc.communicate(payload)
        stdout_text = stdout.decode("utf-8", errors="ignore").strip()
        stderr_text = stderr.decode("utf-8", errors="ignore").strip()

        parsed_stdout: Dict[str, Any] = {}
        if stdout_text:
            try:
                maybe = json.loads(stdout_text)
                if isinstance(maybe, dict):
                    parsed_stdout = maybe
            except Exception:
                parsed_stdout = {}

        if proc.returncode != 0:
            if parsed_stdout:
                detail = str(parsed_stdout.get("error") or "").strip()
                if detail:
                    raise RuntimeError(detail)
            detail = stderr_text or stdout_text
            raise RuntimeError(f"ppt_master_skill_runtime_failed: {detail or f'exit_{proc.returncode}'}")

        parsed: Dict[str, Any]
        if parsed_stdout:
            parsed = parsed_stdout
        else:
            try:
                parsed = json.loads(stdout_text) if stdout_text else {}
            except Exception as exc:
                raise RuntimeError(
                    f"ppt_master_skill_runtime_invalid_json: {stdout_text[:300]}"
                ) from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("ppt_master_skill_runtime_invalid_response_type")
        if not bool(parsed.get("ok")):
            raise RuntimeError(str(parsed.get("error") or "unknown_runtime_error"))

        result = parsed.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("ppt_master_skill_runtime_missing_result")
        return result

    def _runtime_command(self) -> List[str]:
        runtime_bin = str(
            os.getenv("PPT_MASTER_SKILL_RUNTIME_BIN") or Path(sys.executable).resolve()
        ).strip()
        args_raw = str(
            os.getenv("PPT_MASTER_SKILL_RUNTIME_ARGS")
            or "-m src.ppt_master_pipeline_runtime"
        ).strip()
        if not args_raw:
            return [runtime_bin]
        try:
            maybe_json = json.loads(args_raw)
            if isinstance(maybe_json, list):
                return [runtime_bin, *[str(item) for item in maybe_json if str(item).strip()]]
        except Exception:
            pass
        return [runtime_bin, *shlex.split(args_raw, posix=False)]

    def _runtime_cwd(self) -> Path:
        raw = str(
            os.getenv("PPT_MASTER_SKILL_RUNTIME_CWD")
            or Path(__file__).resolve().parents[1]
        ).strip()
        return Path(raw)

    async def _materialize_pptx(
        self,
        *,
        export_data: Dict[str, Any],
        project_path: Path,
        project_name: str,
    ) -> Optional[Path]:
        for key in ("output_pptx", "pptx_path", "local_path", "file_path", "path"):
            value = str(export_data.get(key) or "").strip()
            if not value:
                continue
            candidate = Path(value)
            if candidate.exists() and candidate.is_file():
                target = project_path / candidate.name
                if candidate.resolve() != target.resolve():
                    target.write_bytes(candidate.read_bytes())
                return target

        pptx_base64 = str(export_data.get("pptx_base64") or "").strip()
        if pptx_base64:
            target = project_path / f"{project_name}.pptx"
            target.write_bytes(base64.b64decode(pptx_base64))
            return target

        for key in ("pptx_url", "url"):
            url = str(export_data.get(key) or "").strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                continue
            target = project_path / f"{project_name}.pptx"
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                target.write_bytes(resp.content)
            return target
        return None

    def list_available_templates(self) -> List[Dict[str, str]]:
        layouts_dir = self.templates_dir / "layouts"
        if not layouts_dir.exists():
            return []
        templates: List[Dict[str, str]] = []
        for template_dir in sorted(layouts_dir.iterdir(), key=lambda p: p.name.lower()):
            if not template_dir.is_dir() or template_dir.name == "__pycache__":
                continue
            design_spec = template_dir / "design_spec.md"
            description = ""
            if design_spec.exists():
                description = (
                    design_spec.read_text(encoding="utf-8", errors="ignore").splitlines()[:1]
                    or [""]
                )[0]
            templates.append(
                {
                    "name": template_dir.name,
                    "path": str(template_dir),
                    "description": description,
                }
            )
        return templates

    def _resolve_project_path(self, project_name: str) -> Path:
        name = str(project_name or "").strip()
        if not re.match(r"^[A-Za-z0-9._-]+$", name):
            raise ValueError("invalid project_name format")
        target = (self.output_base / name).resolve()
        base = self.output_base.resolve()
        if base not in target.parents:
            raise ValueError("invalid project_name path")
        return target

    @staticmethod
    def _read_excerpt(path: Path, max_chars: int = 5000) -> str:
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars].strip()

    def resolve_output_pptx_path(self, project_name: str) -> Path:
        project_path = self._resolve_project_path(project_name)
        if not project_path.exists():
            raise FileNotFoundError(f"project not found: {project_name}")
        candidates = sorted(
            project_path.glob("*.pptx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError(f"pptx not found for project: {project_name}")
        return candidates[0]

    def get_project_preview(self, project_name: str) -> Dict[str, Any]:
        project_path = self._resolve_project_path(project_name)
        if not project_path.exists():
            raise FileNotFoundError(f"project not found: {project_name}")

        skill_result_path = project_path / "skill_result.json"
        skill_payload: Dict[str, Any] = {}
        if skill_result_path.exists():
            try:
                parsed = json.loads(
                    skill_result_path.read_text(encoding="utf-8", errors="ignore")
                )
                if isinstance(parsed, dict):
                    skill_payload = parsed
            except Exception:
                skill_payload = {}

        artifacts = (
            skill_payload.get("artifacts")
            if isinstance(skill_payload.get("artifacts"), dict)
            else {}
        )
        export = (
            skill_payload.get("export")
            if isinstance(skill_payload.get("export"), dict)
            else {}
        )

        design_spec_path = project_path / "design_spec.md"
        source_md_path: Optional[Path] = None
        notes_total_path = project_path / "notes" / "total.md"

        source_raw = str(artifacts.get("source_md") or "").strip()
        if source_raw:
            source_candidate = Path(source_raw)
            if source_candidate.exists() and source_candidate.is_file():
                source_md_path = source_candidate
        if source_md_path is None:
            source_candidates = sorted(
                (project_path / "sources").glob("*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if source_candidates:
                source_md_path = source_candidates[0]

        design_raw = str(artifacts.get("design_spec") or "").strip()
        if design_raw:
            design_candidate = Path(design_raw)
            if design_candidate.exists() and design_candidate.is_file():
                design_spec_path = design_candidate

        source_excerpt = (
            self._read_excerpt(source_md_path) if source_md_path else ""
        )
        design_excerpt = self._read_excerpt(design_spec_path)
        notes_excerpt = self._read_excerpt(notes_total_path)

        preview_images = []
        for item in export.get("slide_image_urls") or []:
            value = str(item or "").strip()
            if value.startswith("http://") or value.startswith("https://"):
                preview_images.append(value)

        svg_count = len(list((project_path / "svg_final").glob("*.svg")))
        output_pptx = ""
        try:
            output_pptx = str(self.resolve_output_pptx_path(project_name))
        except Exception:
            output_pptx = ""

        return {
            "project_name": project_path.name,
            "project_path": str(project_path),
            "output_pptx": output_pptx,
            "source_excerpt": source_excerpt,
            "design_excerpt": design_excerpt,
            "notes_excerpt": notes_excerpt,
            "preview_image_urls": preview_images,
            "svg_count": svg_count,
        }


async def generate_ppt_from_prompt(
    prompt: str, total_pages: int = 10, style: str = "professional", **kwargs: Any
) -> Dict[str, Any]:
    service = PPTMasterService()
    return await service.generate_from_prompt(
        prompt=prompt,
        total_pages=total_pages,
        style=style,
        **kwargs,
    )
