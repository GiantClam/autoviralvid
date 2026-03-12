import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright


FRONTEND_BASE = os.getenv("FRONTEND_BASE", "http://127.0.0.1:3001")
RENDERER_BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8123")
OUTPUT_DIR = Path(os.getenv("UI_E2E_OUTPUT_DIR", "test_outputs/ui_openclaw"))
SCENARIO = os.getenv("UI_E2E_SCENARIO", "openclaw").strip().lower()

FIXTURE_URLS = {
    "test_dh_image_2026.png": "https://s.autoviralvid.com/test_dh_image_2026.png",
    "test_dh_audio_20s_20260310.mp3": "https://s.autoviralvid.com/uploads/test_dh_audio_20s_20260310.mp3",
}


SCENARIOS = {
    "openclaw": {
        "template_matchers": [],
        "theme": (
            "OpenClaw introduction video focused on AI-native revenue operations, "
            "recoverable task history, and production-ready workflow automation."
        ),
        "expected_duration": 18.0,
        "expected_width": 1280,
        "expected_height": 720,
        "expected_layer_count": 5,
        "expected_audio_track_count": 0,
        "payload": {
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
                "threadId": "openclaw-ui-e2e",
            }
        },
    },
    "product-ad": {
        "template_matchers": ["Product Ad", "商品广告"],
        "theme": "Short-form ecommerce promo with fast pacing, clear value props, and a direct buy-now CTA.",
        "expected_duration": 15.0,
        "expected_width": 1080,
        "expected_height": 1920,
        "expected_layer_count": 5,
        "expected_audio_track_count": 0,
        "payload": {
            "project": {
                "name": "ProductAd UI Promo",
                "width": 1080,
                "height": 1920,
                "duration": 15,
                "fps": 30,
                "backgroundColor": "#140b05",
                "tracks": [
                    {
                        "id": 1,
                        "type": "overlay",
                        "name": "Promo",
                        "items": [
                            {
                                "id": "product-title",
                                "type": "text",
                                "content": "Launch Faster",
                                "startTime": 0,
                                "duration": 3,
                                "trackId": 1,
                                "name": "Title",
                                "style": {"fontSize": 86, "color": "#fff7ed", "x": 50, "y": 18},
                            },
                            {
                                "id": "product-subtitle",
                                "type": "text",
                                "content": "AI-built promo videos ready for campaigns that need to convert now.",
                                "startTime": 1,
                                "duration": 3,
                                "trackId": 1,
                                "name": "Subtitle",
                                "style": {"fontSize": 34, "color": "#fdba74", "x": 50, "y": 29},
                            },
                            {
                                "id": "product-point-1",
                                "type": "text",
                                "content": "Storyboards, avatars, and final renders from one production workflow.",
                                "startTime": 4,
                                "duration": 4,
                                "trackId": 1,
                                "name": "Value 1",
                                "style": {"fontSize": 42, "color": "#f8fafc", "x": 50, "y": 46},
                            },
                            {
                                "id": "product-point-2",
                                "type": "text",
                                "content": "Recover every run later from task history without losing the final cut.",
                                "startTime": 8,
                                "duration": 4,
                                "trackId": 1,
                                "name": "Value 2",
                                "style": {"fontSize": 40, "color": "#f8fafc", "x": 50, "y": 60},
                            },
                            {
                                "id": "product-cta",
                                "type": "text",
                                "content": "Ship the next promo today.",
                                "startTime": 12,
                                "duration": 3,
                                "trackId": 1,
                                "name": "CTA",
                                "style": {"fontSize": 52, "color": "#fff7ed", "x": 50, "y": 78},
                            },
                        ],
                    }
                ],
                "threadId": "product-ad-ui-e2e",
            }
        },
    },
    "travel-vlog-media": {
        "template_matchers": ["Travel Vlog", "旅行 Vlog", "旅行Vlog"],
        "theme": "Travel recap with a hero still image, ambient soundtrack, and concise journey captions.",
        "expected_duration": 20.0,
        "expected_width": 1080,
        "expected_height": 1920,
        "expected_layer_count": 4,
        "expected_audio_track_count": 1,
        "payload": {
            "project": {
                "name": "TravelVlog Media UI Story",
                "width": 1080,
                "height": 1920,
                "duration": 20,
                "fps": 30,
                "backgroundColor": "#05131d",
                "tracks": [
                    {
                        "id": 1,
                        "type": "video",
                        "name": "Hero Media",
                        "items": [
                            {
                                "id": "travel-hero",
                                "type": "image",
                                "content": "fixture://test_dh_image_2026.png",
                                "startTime": 0,
                                "duration": 20,
                                "trackId": 1,
                                "name": "Hero Image",
                            }
                        ],
                    },
                    {
                        "id": 2,
                        "type": "audio",
                        "name": "Narration Bed",
                        "items": [
                            {
                                "id": "travel-bgm",
                                "type": "audio",
                                "content": "fixture://test_dh_audio_20s_20260310.mp3",
                                "startTime": 0,
                                "duration": 20,
                                "trackId": 2,
                                "name": "Ambient Track",
                                "style": {"opacity": 0.7},
                            }
                        ],
                    },
                    {
                        "id": 3,
                        "type": "overlay",
                        "name": "Captions",
                        "items": [
                            {
                                "id": "travel-title",
                                "type": "text",
                                "content": "Weekend Reset",
                                "startTime": 0,
                                "duration": 4,
                                "trackId": 3,
                                "name": "Title",
                                "style": {"fontSize": 82, "color": "#f8fafc", "x": 50, "y": 16},
                            },
                            {
                                "id": "travel-caption-1",
                                "type": "text",
                                "content": "One still frame, one soundtrack, one clear story beat at a time.",
                                "startTime": 5,
                                "duration": 7,
                                "trackId": 3,
                                "name": "Caption 1",
                                "style": {"fontSize": 36, "color": "#e2e8f0", "x": 50, "y": 72},
                            },
                            {
                                "id": "travel-caption-2",
                                "type": "text",
                                "content": "Media layers render cleanly through the same UI flow.",
                                "startTime": 13,
                                "duration": 7,
                                "trackId": 3,
                                "name": "Caption 2",
                                "style": {"fontSize": 38, "color": "#bae6fd", "x": 50, "y": 82},
                            },
                        ],
                    },
                ],
                "threadId": "travel-vlog-media-ui-e2e",
            }
        },
    },
    "knowledge-edu": {
        "template_matchers": ["Knowledge & Edu", "知识科普"],
        "theme": "Educational explainers with crisp structure, chapter breaks, and clear key takeaways.",
        "expected_duration": 12.0,
        "expected_width": 1920,
        "expected_height": 1080,
        "expected_layer_count": 5,
        "expected_audio_track_count": 0,
        "payload": {
            "project": {
                "name": "KnowledgeEdu UI Lesson",
                "width": 1920,
                "height": 1080,
                "duration": 12,
                "fps": 30,
                "backgroundColor": "#0b1020",
                "tracks": [
                    {
                        "id": 1,
                        "type": "overlay",
                        "name": "Lesson",
                        "items": [
                            {
                                "id": "lesson-title",
                                "type": "text",
                                "content": "Why AI Revenue Systems Win",
                                "startTime": 0,
                                "duration": 4,
                                "trackId": 1,
                                "name": "Lesson Title",
                                "style": {"fontSize": 68, "color": "#4ECDC4", "x": 50, "y": 20},
                            },
                            {
                                "id": "lesson-hook",
                                "type": "text",
                                "content": "Three repeatable advantages that compound every week.",
                                "startTime": 1,
                                "duration": 3,
                                "trackId": 1,
                                "name": "Hook",
                                "style": {"fontSize": 32, "color": "#f8fafc", "x": 50, "y": 32},
                            },
                            {
                                "id": "lesson-point-1",
                                "type": "text",
                                "content": "1. Faster research to outreach handoff",
                                "startTime": 4,
                                "duration": 2.5,
                                "trackId": 1,
                                "name": "Point 1",
                                "style": {"fontSize": 42, "color": "#f8fafc", "x": 14, "y": 50},
                            },
                            {
                                "id": "lesson-point-2",
                                "type": "text",
                                "content": "2. Recoverable task history for every campaign run",
                                "startTime": 6.5,
                                "duration": 2.5,
                                "trackId": 1,
                                "name": "Point 2",
                                "style": {"fontSize": 42, "color": "#f8fafc", "x": 14, "y": 62},
                            },
                            {
                                "id": "lesson-point-3",
                                "type": "text",
                                "content": "3. Production-ready output without manual stitching",
                                "startTime": 9,
                                "duration": 3,
                                "trackId": 1,
                                "name": "Point 3",
                                "style": {"fontSize": 42, "color": "#f8fafc", "x": 14, "y": 74},
                            },
                        ],
                    }
                ],
                "threadId": "knowledge-ui-e2e",
            }
        },
    },
}


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
            "-show_entries",
            "stream=codec_type,width,height:format=duration",
            "-of",
            "json",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream_count = sum(1 for stream in streams if stream.get("codec_type") == "audio")
    duration = float((payload.get("format") or {}).get("duration") or 0.0)
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)

    expected_width = int(SCENARIOS[SCENARIO]["expected_width"])
    expected_height = int(SCENARIOS[SCENARIO]["expected_height"])
    expected_duration = float(SCENARIOS[SCENARIO]["expected_duration"])
    expected_audio_track_count = int(SCENARIOS[SCENARIO].get("expected_audio_track_count", 0))

    if width != expected_width or height != expected_height:
        raise RuntimeError(
            f"Unexpected output resolution: {width}x{height}, expected {expected_width}x{expected_height}"
        )

    if not (expected_duration - 1.5 <= duration <= expected_duration + 1.5):
        raise RuntimeError(
            f"Unexpected output duration: {duration:.2f}s, expected about {expected_duration:.2f}s"
        )

    if audio_stream_count < expected_audio_track_count:
        raise RuntimeError(
            f"Unexpected audio stream count: {audio_stream_count}, expected at least {expected_audio_track_count}"
        )

    return {
        "width": width,
        "height": height,
        "duration": duration,
        "audio_stream_count": audio_stream_count,
    }


def verify_output_url(page, output_url: str) -> dict:
    if output_url.startswith("file://"):
        return {
            "status": "skipped",
            "reason": "local_file_output",
        }

    response = page.request.head(output_url)
    if not response.ok:
        raise RuntimeError(f"Output URL is not reachable: HTTP {response.status} -> {output_url}")

    content_type = response.headers.get("content-type", "")
    if "video/mp4" not in content_type.lower():
        raise RuntimeError(f"Unexpected output content-type: {content_type}")

    return {
        "status": response.status,
        "content_type": content_type,
    }


def _materialize_fixture(name: str) -> str:
    source_url = FIXTURE_URLS.get(name)
    if not source_url:
        raise RuntimeError(f"Unknown fixture reference: {name}")

    fixtures_dir = OUTPUT_DIR.parent / "_fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    local_path = fixtures_dir / name
    if not local_path.exists() or local_path.stat().st_size == 0:
        request = Request(
            source_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/132.0.0.0 Safari/537.36"
                )
            },
        )
        with urlopen(request) as response, local_path.open("wb") as handle:
            handle.write(response.read())
    return str(local_path.resolve())


def _replace_fixture_refs(node):
    if isinstance(node, dict):
        return {key: _replace_fixture_refs(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_replace_fixture_refs(value) for value in node]
    if isinstance(node, str) and node.startswith("fixture://"):
        return _materialize_fixture(node.removeprefix("fixture://"))
    return node


def main() -> int:
    if SCENARIO not in SCENARIOS:
        raise RuntimeError(f"Unsupported UI_E2E_SCENARIO: {SCENARIO}")

    scenario = SCENARIOS[SCENARIO]
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

        selected_card = None
        for matcher in scenario["template_matchers"]:
            candidate = page.locator(f"button:has-text('{matcher}')").first
            if candidate.count() > 0:
                selected_card = candidate
                break
        if selected_card is None:
            selected_card = template_cards.first
        selected_card.click()
        page.wait_for_selector("textarea")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUTPUT_DIR / "02-project-form.png"), full_page=True)

        theme = str(scenario["theme"])
        page.locator("textarea").first.fill(theme)
        print("[ui] Filled project theme in the form")

        payload = _replace_fixture_refs(json.loads(json.dumps(scenario["payload"])))
        payload["project"]["runId"] = f"{SCENARIO}-ui-{int(time.time())}"

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

        summary = body.get("summary") or {}
        expected_layer_count = scenario.get("expected_layer_count")
        expected_audio_track_count = scenario.get("expected_audio_track_count")
        if expected_layer_count is not None and summary.get("layerCount") != expected_layer_count:
            raise RuntimeError(
                f"Unexpected layerCount: {summary.get('layerCount')}, expected {expected_layer_count}"
            )
        if (
            expected_audio_track_count is not None
            and summary.get("audioTrackCount") != expected_audio_track_count
        ):
            raise RuntimeError(
                f"Unexpected audioTrackCount: {summary.get('audioTrackCount')}, expected {expected_audio_track_count}"
            )

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
        url_check = verify_output_url(page, str(final_status["output_url"]))
        print(json.dumps({"probe": probe}, indent=2))
        print(json.dumps({"output_url_check": url_check}, indent=2))

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
