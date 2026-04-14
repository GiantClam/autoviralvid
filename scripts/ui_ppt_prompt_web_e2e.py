from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from e2e_process_utils import start_process, stop_process, wait_for_port

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
FRONTEND_PORT = int(os.getenv("UI_E2E_FRONTEND_PORT", "3001"))
RENDERER_PORT = int(os.getenv("UI_E2E_RENDERER_PORT", "8124"))
FRONTEND_BASE = f"http://127.0.0.1:{FRONTEND_PORT}"
RENDERER_BASE = f"http://127.0.0.1:{RENDERER_PORT}"
OUTPUT_DIR = Path(os.getenv("UI_E2E_OUTPUT_DIR", "test_outputs/ui_ppt_prompt_web_e2e"))
TIMEOUT_SECONDS = int(os.getenv("UI_E2E_GENERATE_TIMEOUT_SECONDS", "1200"))


def _wait_for_generation_done(page, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        phase_text = page.locator("text=Current phase:").first.inner_text(timeout=10000)
        normalized = phase_text.lower()
        if "done" in normalized:
            return
        if "error" in normalized:
            log_text = page.get_by_test_id("log-panel").inner_text(timeout=5000)
            raise RuntimeError(f"Web generation entered error phase. phase={phase_text} logs={log_text[-1200:]}")
        time.sleep(2)
    raise TimeoutError(f"Web generation did not finish within {timeout_seconds}s")


def run_web_e2e() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    screenshots = OUTPUT_DIR / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(viewport={"width": 1600, "height": 960})
        page = context.new_page()

        page.goto(f"{FRONTEND_BASE}/ppt", wait_until="domcontentloaded", timeout=120000)
        page.get_by_test_id("ppt-page-title").wait_for(timeout=120000)
        page.screenshot(path=str(screenshots / "01-page-loaded.png"), full_page=True)

        prompt_text = (
            "Create a concise 6-slide executive presentation about CNC smart manufacturing strategy, "
            "including company profile, product matrix, technology advantages, market opportunity, "
            "cooperation model, and closing contact slide."
        )
        textareas = page.locator("textarea")
        textareas.nth(0).fill(prompt_text)
        textareas.nth(1).fill(
            "1) Cover\n2) Company profile\n3) Product matrix\n4) Technology advantages\n5) Market and cooperation\n6) Closing"
        )

        page.locator("input[type='number']").first.fill("6")
        checkboxes = page.locator("input[type='checkbox']")
        for i in range(4):
            if checkboxes.nth(i).is_visible():
                checkboxes.nth(i).check()

        page.get_by_test_id("btn-generate-from-prompt").click()
        page.screenshot(path=str(screenshots / "02-after-click-generate.png"), full_page=True)

        _wait_for_generation_done(page, TIMEOUT_SECONDS)

        page.screenshot(path=str(screenshots / "03-generation-done.png"), full_page=True)

        download_link = page.locator("a:has-text('Download via API')").first
        if download_link.count() == 0:
            raise RuntimeError("Download via API link not found in result panel")

        href = str(download_link.get_attribute("href") or "").strip()
        if not href:
            raise RuntimeError("Download via API href is empty")

        resp = page.request.get(href, timeout=180000)
        if resp.status != 200:
            body = resp.text()[:500]
            raise RuntimeError(f"Download API failed: status={resp.status} body={body}")

        ppt_bytes = resp.body()
        if not ppt_bytes.startswith(b"PK"):
            raise RuntimeError(f"Downloaded file is not a pptx(zip), size={len(ppt_bytes)}")

        ppt_path = OUTPUT_DIR / "web_prompt_flow.pptx"
        ppt_path.write_bytes(ppt_bytes)

        log_text = page.get_by_test_id("log-panel").inner_text(timeout=10000)
        project_name = ""
        try:
            project_name = page.locator("text=Project").nth(0).locator("xpath=following::*[1]").inner_text(timeout=5000)
        except Exception:
            project_name = ""

        context.close()
        browser.close()

    return {
        "success": True,
        "frontend_base": FRONTEND_BASE,
        "renderer_base": RENDERER_BASE,
        "ppt_path": str(ppt_path),
        "ppt_size_bytes": ppt_path.stat().st_size,
        "download_href": href,
        "project_name": project_name,
        "log_tail": log_text[-1500:],
    }


def main() -> int:
    backend = None
    frontend = None
    summary_path = OUTPUT_DIR / "summary.json"

    try:
        print(f"Starting backend on {RENDERER_BASE} ...")
        backend = start_process(
            ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(RENDERER_PORT)],
            AGENT_DIR,
            {
                "AUTH_REQUIRED": "false",
                "CORS_ORIGIN": FRONTEND_BASE,
            },
        )
        wait_for_port(RENDERER_PORT, 90)

        print(f"Starting frontend on {FRONTEND_BASE} ...")
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
        wait_for_port(FRONTEND_PORT, 120)
        time.sleep(5)

        summary = run_web_e2e()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    except Exception as exc:
        failure = {
            "success": False,
            "frontend_base": FRONTEND_BASE,
            "renderer_base": RENDERER_BASE,
            "error": str(exc),
        }
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False))
        return 1

    finally:
        stop_process(backend)
        stop_process(frontend)


if __name__ == "__main__":
    sys.exit(main())
