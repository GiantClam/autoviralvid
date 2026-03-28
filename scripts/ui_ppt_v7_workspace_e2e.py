import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Route, sync_playwright


FRONTEND_BASE = os.getenv("FRONTEND_BASE", "http://127.0.0.1:3001")
OUTPUT_DIR = Path(os.getenv("UI_E2E_OUTPUT_DIR", "test_outputs/ui_ppt_v7_workspace"))
HEADLESS = os.getenv("HEADLESS", "true").lower() not in ("0", "false", "no")
SLOW_MO = int(os.getenv("SLOW_MO", "0"))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    calls = {"generate": 0, "tts": 0, "export": 0}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
        page = browser.new_page()
        page.set_default_navigation_timeout(120000)
        page.set_default_timeout(30000)
        page.on("console", lambda msg: print(f"[browser:{msg.type}] {msg.text}"))

        def fulfill_json(route: Route, body: dict) -> None:
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps(body),
            )

        def handle_generate(route: Route) -> None:
            calls["generate"] += 1
            run_idx = calls["generate"]
            fulfill_json(
                route,
                {
                    "success": True,
                    "data": {
                        "title": f"Mock PPT V7 #{run_idx}",
                        "design_system": "default",
                        "slides": [
                            {
                                "id": f"s-{run_idx}-1",
                                "title": "Intro",
                                "narration": "Mock narration",
                            }
                        ],
                    },
                },
            )

        def handle_tts(route: Route) -> None:
            calls["tts"] += 1
            fulfill_json(
                route,
                {
                    "success": True,
                    "data": {
                        "slides": [
                            {
                                "id": f"tts-{calls['tts']}-1",
                                "title": "Intro",
                                "narration": "Mock narration",
                                "narrationAudioUrl": "https://example.com/mock.mp3",
                            }
                        ]
                    },
                },
            )

        def handle_export(route: Route) -> None:
            calls["export"] += 1
            run_idx = calls["export"]
            fulfill_json(
                route,
                {
                    "success": True,
                    "data": {
                        "run_id": f"ppt-v7-run-{run_idx}",
                        "pptx_url": f"https://example.com/ppt-v7-{run_idx}.pptx",
                        "slide_image_urls": [
                            f"https://picsum.photos/seed/ppt-v7-{run_idx}-1/640/360",
                            f"https://picsum.photos/seed/ppt-v7-{run_idx}-2/640/360",
                        ],
                        "slide_count": 2,
                    },
                },
            )

        page.route("**/api/projects/v7/generate", handle_generate)
        page.route("**/api/projects/v7/tts", handle_tts)
        page.route("**/api/projects/v7/export", handle_export)

        print(f"[ui] Opening {FRONTEND_BASE}")
        page.goto(FRONTEND_BASE, wait_until="commit")
        page.wait_for_selector("button")

        template = page.locator("button:has-text('PPT & Video V7')").first
        assert_true(template.count() > 0, "PPT & Video V7 template card not found")
        template.click()
        page.wait_for_selector("aside textarea")

        page.locator("aside textarea").first.fill(
            "Create a short PPT about quarterly growth metrics and strategic focus."
        )

        submit = page.locator("aside div.border-t button").first
        assert_true(submit.count() > 0, "Submit button not found")
        submit.click()

        page.wait_for_selector("text=PPT V7 Workspace")
        page.wait_for_selector("text=ppt-v7-run-1")
        page.wait_for_selector("a:has-text('Download PPTX')")

        page.screenshot(path=str(OUTPUT_DIR / "01-first-run.png"), full_page=True)

        retry = page.get_by_role("button", name="Retry")
        assert_true(retry.count() > 0, "Retry button not found")
        retry.click()

        page.wait_for_selector("text=ppt-v7-run-2")
        page.screenshot(path=str(OUTPUT_DIR / "02-retry-run.png"), full_page=True)

        assert_true(calls["generate"] >= 2, "Generate API should be called twice")
        assert_true(calls["tts"] >= 2, "TTS API should be called twice")
        assert_true(calls["export"] >= 2, "Export API should be called twice")

        history_text = page.locator("text=Recent Runs")
        assert_true(history_text.count() > 0, "Recent Runs panel not found")
        assert_true(page.locator("text=ppt-v7-run-1").count() > 0, "Run #1 missing in UI")
        assert_true(page.locator("text=ppt-v7-run-2").count() > 0, "Run #2 missing in UI")

        result = {
            "status": "ok",
            "calls": calls,
            "artifacts": {
                "first_run": str(OUTPUT_DIR / "01-first-run.png"),
                "retry_run": str(OUTPUT_DIR / "02-retry-run.png"),
            },
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))

        browser.close()
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ui] FAILURE: {exc}", file=sys.stderr)
        raise
