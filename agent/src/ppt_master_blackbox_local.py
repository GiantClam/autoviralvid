"""Thin local wrapper for ppt-master native runtime.

This module does not implement strategist/executor orchestration.
It initializes project folder, then delegates end-to-end execution to
`src.ppt_master_native_runtime.run_native_pipeline`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


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


def _project_init(*, project_name: str, output_base: Path, timeout_sec: int) -> Path:
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


def run_blackbox_request(request_payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.ppt_master_native_runtime import run_native_pipeline

    payload = dict(request_payload or {})
    prompt = _text(payload.get("prompt"), "")
    if not prompt:
        raise RuntimeError("missing_prompt")

    project_name = _text(payload.get("project_name"), "")
    if not project_name:
        project_name = f"ai_gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    output_base = Path(
        _text(
            payload.get("output_base_dir"),
            str(Path(__file__).resolve().parents[2] / "output" / "ppt_master_projects"),
        )
    )
    output_base.mkdir(parents=True, exist_ok=True)
    timeout_sec = max(120, min(7200, _to_int(payload.get("timeout_sec"), 3600)))

    project_path = _project_init(
        project_name=project_name,
        output_base=output_base,
        timeout_sec=min(timeout_sec, 240),
    )
    project_path.mkdir(parents=True, exist_ok=True)

    runtime_request_path = project_path / "runtime_request.json"
    runtime_request_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "prompt.txt").write_text(prompt, encoding="utf-8")

    native_out = run_native_pipeline(
        request_payload=payload,
        project_path=project_path,
        timeout_sec=timeout_sec,
    )
    if not isinstance(native_out, dict):
        raise RuntimeError("pipeline_result_invalid")

    artifacts = native_out.get("artifacts") if isinstance(native_out.get("artifacts"), dict) else {}
    merged_artifacts = dict(artifacts)
    merged_artifacts.setdefault("project_path", str(project_path))
    merged_artifacts.setdefault("runtime_request", str(runtime_request_path))

    export = native_out.get("export") if isinstance(native_out.get("export"), dict) else {}
    merged_export = dict(export)
    merged_export["project_name"] = project_path.name
    merged_export["generator_mode"] = "ppt_master_skill_runtime_local_skill"

    result = {
        "run_id": _text(native_out.get("run_id"), ""),
        "stages": list(native_out.get("stages") or []),
        "artifacts": merged_artifacts,
        "export": merged_export,
    }

    (project_path / "runtime_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result
