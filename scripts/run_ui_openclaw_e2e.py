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
SCENARIO = os.getenv("UI_E2E_SCENARIO", "openclaw")
ALL_SCENARIOS = [
    "openclaw",
    "product-ad",
    "brand-story-video",
    "travel-vlog-media",
    "knowledge-edu",
]


def main() -> int:
    backend = None
    frontend = None
    try:
        backend = start_process(
            ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(RENDERER_PORT)],
            AGENT_DIR,
            {
                "AUTH_REQUIRED": "false",
                "CORS_ORIGIN": FRONTEND_BASE,
            },
        )
        wait_for_port(RENDERER_PORT, 45)

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
        time.sleep(3)

        scenarios = ALL_SCENARIOS if SCENARIO == "all" else [SCENARIO]
        for scenario_name in scenarios:
            output_dir = os.getenv(
                "UI_E2E_OUTPUT_DIR",
                f"test_outputs/ui_{scenario_name}" if SCENARIO != "all" else f"test_outputs/ui_all/{scenario_name}",
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "ui_openclaw_remotion_e2e.py")],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    "FRONTEND_BASE": FRONTEND_BASE,
                    "RENDERER_BASE": RENDERER_BASE,
                    "UI_E2E_SCENARIO": scenario_name,
                    "UI_E2E_OUTPUT_DIR": output_dir,
                },
                check=False,
            )
            if result.returncode != 0:
                return result.returncode
        return 0
    finally:
        stop_process(frontend)
        stop_process(backend)


if __name__ == "__main__":
    raise SystemExit(main())
