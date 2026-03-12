import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
FRONTEND_PORT = int(os.getenv("UI_E2E_FRONTEND_PORT", "3001"))
RENDERER_PORT = int(os.getenv("UI_E2E_RENDERER_PORT", "8124"))
FRONTEND_BASE = f"http://127.0.0.1:{FRONTEND_PORT}"
RENDERER_BASE = f"http://127.0.0.1:{RENDERER_PORT}"
SCENARIO = os.getenv("UI_E2E_SCENARIO", "openclaw")


def wait_for_port(port: int, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.5)
    raise TimeoutError(f"Port {port} was not ready within {timeout_seconds}s")


def start_process(command: list[str], cwd: Path, extra_env: dict[str, str]) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(extra_env)
    executable = shutil.which(command[0])
    if executable:
        command = [executable, *command[1:]]
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


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
                "NEXT_PUBLIC_AGENT_URL": RENDERER_BASE,
                "NEXT_PUBLIC_API_BASE": RENDERER_BASE,
                "NEXT_PUBLIC_DISABLE_API_TOKEN": "1",
            },
        )
        wait_for_port(FRONTEND_PORT, 60)
        time.sleep(3)

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ui_openclaw_remotion_e2e.py")],
            cwd=str(ROOT),
            env={
                **os.environ,
                "FRONTEND_BASE": FRONTEND_BASE,
                "RENDERER_BASE": RENDERER_BASE,
                "UI_E2E_SCENARIO": SCENARIO,
                "UI_E2E_OUTPUT_DIR": os.getenv("UI_E2E_OUTPUT_DIR", f"test_outputs/ui_{SCENARIO}"),
            },
            check=False,
        )
        return result.returncode
    finally:
        stop_process(frontend)
        stop_process(backend)


if __name__ == "__main__":
    raise SystemExit(main())
