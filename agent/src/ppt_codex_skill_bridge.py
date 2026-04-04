"""Utilities to bridge local skill specs with Codex CLI JSON execution."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Sequence


def normalize_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def normalize_skill_key(value: Any) -> str:
    text = normalize_text(value, "").lower()
    text = "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in text)
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")


def dedupe_skills(values: Any) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in as_list(values):
        key = normalize_skill_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def normalize_codex_cli_model_id(model_id: str) -> str:
    model = normalize_text(model_id, "")
    if "/" in model:
        _, tail = model.split("/", 1)
        return normalize_text(tail, model)
    return model


def parse_command_args(raw_value: str) -> List[str]:
    text = normalize_text(raw_value, "")
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [normalize_text(item, "") for item in parsed if normalize_text(item, "")]
    except Exception:
        pass
    try:
        return [item for item in shlex.split(text, posix=False) if normalize_text(item, "")]
    except Exception:
        return [item for item in text.split() if normalize_text(item, "")]


def parse_json_object(raw_text: str) -> Dict[str, Any]:
    text = normalize_text(raw_text, "")
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    if "```" in text:
        blocks = text.split("```")
        for block in blocks:
            candidate = block.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    for line in reversed(text.splitlines()):
        row = line.strip()
        if not row.startswith("{"):
            continue
        try:
            parsed = json.loads(row)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def parse_env_paths(raw_value: str) -> List[Path]:
    text = normalize_text(raw_value, "")
    if not text:
        return []
    out: List[Path] = []
    for item in text.split(os.pathsep):
        row = normalize_text(item, "")
        if row:
            out.append(Path(row))
    return out


def resolve_skill_roots(
    *,
    env_key: str,
    default_roots: Sequence[Path],
) -> List[Path]:
    roots: List[Path] = []
    roots.extend(parse_env_paths(os.getenv(env_key, "")))
    roots.extend(default_roots)
    out: List[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def load_skill_specs(
    *,
    requested_skills: Sequence[str],
    skill_roots: Sequence[Path],
    aliases: Dict[str, str] | None = None,
) -> List[Dict[str, Any]]:
    alias_map = aliases or {}
    docs: List[Dict[str, Any]] = []
    for raw_skill in requested_skills:
        skill = normalize_skill_key(raw_skill)
        if not skill:
            continue
        names = [skill]
        alias = normalize_skill_key(alias_map.get(skill, ""))
        if alias and alias not in names:
            names.append(alias)
        found = False
        for root in skill_roots:
            for name in names:
                skill_file = root / name / "SKILL.md"
                if not skill_file.exists():
                    continue
                try:
                    content = skill_file.read_text(encoding="utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if not content:
                    continue
                docs.append(
                    {
                        "skill": skill,
                        "resolved_name": name,
                        "path": str(skill_file),
                        "content": content,
                    }
                )
                found = True
                break
            if found:
                break
        if not found:
            docs.append({"skill": skill, "resolved_name": "", "path": "", "content": ""})
    return docs


def build_skill_specs_block(
    docs: Sequence[Dict[str, Any]],
    *,
    max_chars: int,
) -> str:
    sections: List[str] = []
    for item in docs:
        skill = normalize_text(item.get("skill"), "unknown")
        path = normalize_text(item.get("path"), "")
        content = normalize_text(item.get("content"), "")
        if not content:
            sections.append(f"## Skill: {skill}\nStatus: missing SKILL.md")
            continue
        sections.append(f"## Skill: {skill}\nSource: {path}\n\n{content}")
    joined = "\n\n---\n\n".join(sections)
    if len(joined) <= max_chars:
        return joined
    return joined[: max(0, max_chars - 14)] + "\n\n[TRUNCATED]"


def invoke_codex_cli_json(
    *,
    prompt: str,
    schema: Dict[str, Any] | None = None,
    model_id: str = "",
    bin_name: str = "codex",
    extra_args: Sequence[str] | None = None,
    cwd: Path | None = None,
    timeout_sec: int = 90,
) -> Dict[str, Any]:
    args = list(extra_args or [])
    if not args:
        args = ["exec", "--skip-git-repo-check", "--sandbox", "read-only"]
    if args[0] != "exec":
        args = ["exec", *args]

    with tempfile.TemporaryDirectory(prefix="ppt_codex_bridge_") as tmp_dir:
        tmp = Path(tmp_dir)
        output_path = tmp / "last_message.txt"
        cmd: List[str] = [bin_name, *args]
        if schema:
            schema_path = tmp / "schema.json"
            schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
            cmd.extend(["--output-schema", str(schema_path)])
        cmd.extend(["--output-last-message", str(output_path)])
        model = normalize_codex_cli_model_id(model_id)
        if model:
            cmd.extend(["-m", model])
        cmd.append("-")

        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(15, int(timeout_sec)),
            check=False,
            cwd=str(cwd) if cwd else None,
        )
        raw_output = ""
        if output_path.exists():
            try:
                raw_output = output_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                raw_output = ""
        parsed = parse_json_object(raw_output)
        if proc.returncode != 0:
            detail = normalize_text(proc.stderr, "") or normalize_text(proc.stdout, "") or f"exit_{proc.returncode}"
            return {
                "ok": False,
                "reason": f"codex_cli_nonzero:{detail[:240]}",
                "data": {},
                "stdout": normalize_text(proc.stdout, ""),
                "stderr": normalize_text(proc.stderr, ""),
                "cmd": cmd,
            }
        if not parsed:
            return {
                "ok": False,
                "reason": "codex_cli_invalid_json",
                "data": {},
                "stdout": normalize_text(proc.stdout, ""),
                "stderr": normalize_text(proc.stderr, ""),
                "cmd": cmd,
            }
        return {
            "ok": True,
            "reason": "",
            "data": parsed,
            "stdout": normalize_text(proc.stdout, ""),
            "stderr": normalize_text(proc.stderr, ""),
            "cmd": cmd,
        }
