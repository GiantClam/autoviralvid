from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _live_enabled() -> bool:
    return str(os.getenv("PPT_CODEX_PPT_PARITY_LIVE", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _case_list() -> list[str]:
    raw = str(os.getenv("PPT_CODEX_PPT_PARITY_CASES", "")).strip()
    if not raw:
        return [
            "anthropic_pptx",
            "minimax_pptx_generator",
            "minimax_pptx_plugin",
            "ppt_master",
        ]
    out: list[str] = []
    for item in raw.split(","):
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def test_codex_cli_vs_project_ppt_parity_live(tmp_path: Path):
    if not _live_enabled():
        pytest.skip("set PPT_CODEX_PPT_PARITY_LIVE=1 to run codex-cli vs project ppt parity test")

    repo_root = Path(__file__).resolve().parents[2]
    output_dir = tmp_path / "codex_parity"
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "compare_codex_cli_vs_project_ppt.py"),
        "--output-dir",
        str(output_dir),
    ]
    min_score = str(os.getenv("PPT_CODEX_PPT_PARITY_MIN_SCORE", "")).strip()
    if min_score:
        cmd.extend(["--min-score", min_score])
    model_id = str(os.getenv("CONTENT_LLM_MODEL", "")).strip()
    if model_id:
        cmd.extend(["--model", model_id])
    for case in _case_list():
        cmd.extend(["--case", case])

    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(600, int(os.getenv("PPT_CODEX_PPT_PARITY_TIMEOUT_SEC", "1800"))),
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            "parity script failed\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n"
        )

    summary_path = output_dir / "summary.json"
    if not summary_path.exists():
        pytest.fail(f"summary report missing: {summary_path}")
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    cases = data.get("cases") if isinstance(data.get("cases"), list) else []
    assert len(cases) >= 1
    assert not data.get("failures")
    for row in cases:
        assert isinstance(row, dict)
        assert float(row.get("overall_score") or 0.0) > 0
