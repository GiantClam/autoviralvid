import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


FRONTEND_BASE = os.getenv("FRONTEND_BASE", "http://127.0.0.1:3001")
RENDERER_BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8123")
OUTPUT_DIR = Path(os.getenv("UI_E2E_OUTPUT_DIR", "test_outputs/ui_openclaw"))
EXPECTED_DURATION_SECONDS = 18.0
EXPECTED_WIDTH = 1280
EXPECTED_HEIGHT = 720


def wait_for_render(page, job_id: str, timeout_seconds: int = 120) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload = None

    while time.time() < deadline:
      response = page.request.get(f"{RENDERER_BASE}/render/jobs/{job_id}")
      if not response.ok:
          raise RuntimeError(f"Failed to query render job {job_id}: HTTP {response.status}")

      last_payload = response.json()
      status = last_payload.get("status")
      print(f"[render] {job_id}: {status}")

      if status in {"completed", "failed"}:
          return last_payload

      time.sleep(1)

    raise TimeoutError(
        f"Render job {job_id} did not finish within {timeout_seconds}s. Last payload: {last_payload}"
    )


def probe_output_video(output_path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found in PATH")
    if not output_path.exists():
        raise RuntimeError(f"Expected output file does not exist: {output_path}")

    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout or "{}")
    stream = (payload.get("streams") or [{}])[0]
    duration = float((payload.get("format") or {}).get("duration") or 0.0)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)

    if width != EXPECTED_WIDTH or height != EXPECTED_HEIGHT:
        raise RuntimeError(
            f"Unexpected output resolution: {width}x{height}, expected {EXPECTED_WIDTH}x{EXPECTED_HEIGHT}"
        )

    if not (EXPECTED_DURATION_SECONDS - 1.5 <= duration <= EXPECTED_DURATION_SECONDS + 1.5):
        raise RuntimeError(
            f"Unexpected output duration: {duration:.2f}s, expected about {EXPECTED_DURATION_SECONDS:.2f}s"
        )

    return {"width": width, "height": height, "duration": duration}


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_navigation_timeout(120000)
        page.set_default_timeout(30000)
        page.on("console", lambda msg: print(f"[browser:{msg.type}] {msg.text}"))

        print(f"[ui] Opening {FRONTEND_BASE}")
        page.goto(FRONTEND_BASE, wait_until="commit")
        page.wait_for_selector("button")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUTPUT_DIR / "01-home.png"), full_page=True)

        template_cards = page.locator("button:has(h3)")
        card_count = template_cards.count()
        print(f"[ui] Found template cards: {card_count}")
        if card_count == 0:
            raise RuntimeError("No template cards found on the landing page")

        template_cards.first.click()
        page.wait_for_selector("textarea")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUTPUT_DIR / "02-project-form.png"), full_page=True)

        theme = (
            "OpenClaw introduction video focused on AI-native revenue operations, "
            "recoverable task history, and production-ready workflow automation."
        )
        page.locator("textarea").first.fill(theme)
        print("[ui] Filled project theme in the form")

        payload = {
            "project": {
                "name": "OpenClaw UI Introduction",
                "width": 1280,
                "height": 720,
                "duration": 18,
                "fps": 30,
                "backgroundColor": "#08111f",
                "tracks": [
                    {
                        "id": 1,
                        "type": "overlay",
                        "name": "Narrative",
                        "items": [
                            {
                                "id": "openclaw-title",
                                "type": "text",
                                "content": "OpenClaw",
                                "startTime": 0,
                                "duration": 4,
                                "trackId": 1,
                                "name": "Title",
                                "style": {"fontSize": 72, "color": "#f8fafc", "x": 50, "y": 28},
                            },
                            {
                                "id": "openclaw-subtitle",
                                "type": "text",
                                "content": "Build AI-native revenue systems without manual handoffs.",
                                "startTime": 1,
                                "duration": 4,
                                "trackId": 1,
                                "name": "Subtitle",
                                "style": {"fontSize": 30, "color": "#38bdf8", "x": 50, "y": 42},
                            },
                            {
                                "id": "openclaw-capability-1",
                                "type": "text",
                                "content": "OpenClaw researches accounts, drafts outreach, and keeps campaigns moving.",
                                "startTime": 5,
                                "duration": 5,
                                "trackId": 1,
                                "name": "Capability 1",
                                "style": {
                                    "fontSize": 34,
                                    "color": "#e2e8f0",
                                    "x": 50,
                                    "y": 55,
                                    "backgroundColor": "#0f172a",
                                },
                            },
                            {
                                "id": "openclaw-capability-2",
                                "type": "text",
                                "content": "Every run stays recoverable, so teams can reopen history and ship faster.",
                                "startTime": 10,
                                "duration": 4,
                                "trackId": 1,
                                "name": "Capability 2",
                                "style": {
                                    "fontSize": 34,
                                    "color": "#e2e8f0",
                                    "x": 50,
                                    "y": 55,
                                    "backgroundColor": "#0f172a",
                                },
                            },
                            {
                                "id": "openclaw-cta",
                                "type": "text",
                                "content": "OpenClaw turns prompts into production-ready revenue workflows.",
                                "startTime": 14,
                                "duration": 4,
                                "trackId": 1,
                                "name": "CTA",
                                "style": {"fontSize": 36, "color": "#f8fafc", "x": 50, "y": 72},
                            },
                        ],
                    }
                ],
                "runId": f"openclaw-ui-{int(time.time())}",
                "threadId": "openclaw-ui-e2e",
            }
        }

        print("[ui] Submitting remotion render request from browser context")
        submit_result = page.evaluate(
            """async (body) => {
                const response = await fetch('/api/render/jobs', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const json = await response.json();
                return { ok: response.ok, status: response.status, body: json };
            }""",
            payload,
        )
        print(json.dumps(submit_result, indent=2))

        if not submit_result["ok"]:
            raise RuntimeError(
                f"Render submission failed: HTTP {submit_result['status']} -> {submit_result['body']}"
            )

        body = submit_result["body"]
        if body.get("status") != "accepted":
            raise RuntimeError(f"Unexpected submission response: {body}")

        if body.get("mode") != "remote":
            raise RuntimeError(f"Expected remote mode, got: {body.get('mode')}")

        job_id = body.get("job_id")
        if not job_id:
            raise RuntimeError(f"Missing job_id in response: {body}")

        final_status = wait_for_render(page, job_id)
        print(json.dumps(final_status, indent=2))

        if final_status.get("status") != "completed":
            raise RuntimeError(f"Render job did not complete successfully: {final_status}")

        if not final_status.get("output_url"):
            raise RuntimeError(f"Render job completed without output_url: {final_status}")

        output_path = Path(str(final_status.get("output_path") or ""))
        probe = probe_output_video(output_path)
        print(json.dumps({"probe": probe}, indent=2))

        page.screenshot(path=str(OUTPUT_DIR / "03-render-submitted.png"), full_page=True)
        print(f"[ui] Render completed: {final_status['output_url']}")
        browser.close()
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ui] FAILURE: {exc}", file=sys.stderr)
        raise
