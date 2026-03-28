"""
PPT E2E 测试启动器 — 启动前后端并执行浏览器测试

运行方式:
  python scripts/run_ppt_e2e.py

环境变量:
  UI_E2E_FRONTEND_PORT  — 前端端口 (默认 3001)
  UI_E2E_RENDERER_PORT  — 后端端口 (默认 8124)
  HEADLESS              — 无头模式 (默认 true)
  SLOW_MO               — 慢动作毫秒 (默认 0)
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from e2e_process_utils import wait_for_port, start_process, stop_process

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
FRONTEND_PORT = int(os.getenv("UI_E2E_FRONTEND_PORT", "3001"))
RENDERER_PORT = int(os.getenv("UI_E2E_RENDERER_PORT", "8124"))
FRONTEND_BASE = f"http://127.0.0.1:{FRONTEND_PORT}"
RENDERER_BASE = f"http://127.0.0.1:{RENDERER_PORT}"


def main() -> int:
    backend = None
    frontend = None
    try:
        print(f"Starting backend on port {RENDERER_PORT}...")
        backend = start_process(
            [
                "uv",
                "run",
                "uvicorn",
                "main:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(RENDERER_PORT),
            ],
            AGENT_DIR,
            {
                "AUTH_REQUIRED": "false",
                "CORS_ORIGIN": FRONTEND_BASE,
            },
        )
        wait_for_port(RENDERER_PORT, 45)
        print(f"  Backend ready on {RENDERER_BASE}")

        print(f"Starting frontend on port {FRONTEND_PORT}...")
        frontend = start_process(
            ["npx", "next", "dev", "--turbopack", "-p", str(FRONTEND_PORT)],
            ROOT,
            {
                "AUTH_REQUIRED": "false",
                "REMOTION_RENDERER_URL": RENDERER_BASE,
                "AGENT_URL": RENDERER_BASE,
                "NEXT_PUBLIC_AGENT_URL": RENDERER_BASE,
                "NEXT_PUBLIC_API_BASE": RENDERER_BASE,
                "NEXT_PUBLIC_DISABLE_API_TOKEN": "1",
            },
        )
        wait_for_port(FRONTEND_PORT, 60)
        print(f"  Frontend ready on {FRONTEND_BASE}")
        time.sleep(3)

        output_dir = os.getenv("UI_E2E_OUTPUT_DIR", "test_outputs/ui_ppt_e2e")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ui_ppt_e2e.py")],
            cwd=str(ROOT),
            env={
                **os.environ,
                "FRONTEND_BASE": FRONTEND_BASE,
                "RENDERER_BASE": RENDERER_BASE,
                "UI_E2E_OUTPUT_DIR": output_dir,
            },
        )
        return result.returncode

    except Exception as exc:
        print(f"E2E test runner failed: {exc}", file=sys.stderr)
        return 1
    finally:
        stop_process(backend)
        stop_process(frontend)


if __name__ == "__main__":
    sys.exit(main())
