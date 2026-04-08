"""Thin runtime passthrough for prompt-direct ppt-master generation.

This module is intentionally minimal:
- parse JSON request from stdin;
- forward to `src.ppt_master_blackbox_local.run_blackbox_request`;
- return normalized JSON response.

No Codex CLI orchestration is performed here.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict


def _load_env_files() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    agent_root = Path(__file__).resolve().parents[1]
    repo_root = agent_root.parent
    load_dotenv(agent_root / ".env", override=False)
    load_dotenv(repo_root / ".env", override=False)
    load_dotenv(repo_root / ".env.local", override=False)


def _read_stdin_payload() -> Dict[str, Any]:
    raw = ""
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        raw = buffer.read().decode("utf-8", errors="ignore")
    else:
        raw = sys.stdin.read()
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def _write_stdout_json(payload: Dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
    else:
        sys.stdout.write(text)
    sys.stdout.flush()


def _run(request_payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.ppt_master_blackbox_local import run_blackbox_request

    return run_blackbox_request(request_payload)


def main() -> int:
    _load_env_files()
    payload = _read_stdin_payload()
    request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    if not request_payload:
        _write_stdout_json({"ok": False, "error": "missing_request"})
        return 1
    try:
        result = _run(request_payload)
        _write_stdout_json({"ok": True, "result": result})
        return 0
    except Exception as exc:
        _write_stdout_json(
            {
                "ok": False,
                "error": str(exc) or exc.__class__.__name__,
                "traceback": traceback.format_exc(limit=10),
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
