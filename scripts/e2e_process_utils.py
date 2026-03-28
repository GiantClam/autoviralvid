from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path


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
