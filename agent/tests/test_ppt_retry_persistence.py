from __future__ import annotations

from pathlib import Path

from src import ppt_master_native_runtime as runtime


def test_safe_slug_keeps_ascii_and_cjk() -> None:
    value = runtime._safe_slug("霍尔木兹 Crisis 2026 / classroom", "fallback")  # noqa: SLF001
    assert value
    assert "fallback" not in value
    assert " " not in value


def test_run_cmd_reports_nonzero_without_throw(tmp_path: Path) -> None:
    script = tmp_path / "exit1.py"
    script.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    code, stdout, stderr = runtime._run_cmd(  # noqa: SLF001
        cmd=["python", str(script)],
        cwd=tmp_path,
        timeout_sec=30,
    )
    assert code == 1
    assert isinstance(stdout, str)
    assert isinstance(stderr, str)

