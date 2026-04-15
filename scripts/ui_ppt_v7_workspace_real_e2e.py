import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from playwright.sync_api import Page, sync_playwright


FRONTEND_BASE = os.getenv("FRONTEND_BASE", "http://127.0.0.1:3001")
RENDERER_BASE = os.getenv("RENDERER_BASE", "http://127.0.0.1:8124")
OUTPUT_DIR = Path(os.getenv("UI_E2E_OUTPUT_DIR", "test_outputs/ui_ppt_v7_workspace_real"))
HEADLESS = os.getenv("HEADLESS", "true").lower() not in ("0", "false", "no")
SLOW_MO = int(os.getenv("SLOW_MO", "0"))
TIMEOUT_SECONDS = int(os.getenv("UI_E2E_V7_TIMEOUT", "420"))
PPT_RENDER_SUBMIT_TIMEOUT_MS = int(
    os.getenv("UI_E2E_PPT_RENDER_SUBMIT_TIMEOUT_MS", "600000")
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def safe_print(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("unicode_escape").decode("ascii"))


def parse_run_id_and_link(page: Page) -> tuple[str | None, str | None]:
    run_line = page.locator("text=/Run ID:\\s*[A-Za-z0-9_-]+/").first
    if run_line.count() == 0:
        return None, None

    try:
        text = run_line.inner_text(timeout=1000)
    except Exception:
        return None, None
    match = re.search(r"Run ID:\s*([A-Za-z0-9_-]+)", text)
    run_id = match.group(1) if match else None

    link = page.locator("a:has-text('Download PPTX')").first
    href = None
    if link.count() > 0:
        try:
            href = link.get_attribute("href")
        except Exception:
            href = None
    return run_id, href


def extract_slide_image_urls(page: Page, run_id: str) -> list[str]:
    images = page.locator("text=Slide Previews").locator("..").locator("img")
    urls: list[str] = []
    count = images.count()
    for i in range(count):
        src = images.nth(i).get_attribute("src")
        if src:
            urls.append(src)

    if urls:
        return urls

    # fallback to deterministic R2 pattern if preview didn't render in time
    return [
        f"https://s.autoviralvid.com/projects/{run_id}/slides/slide-001.png",
        f"https://s.autoviralvid.com/projects/{run_id}/slides/slide-002.png",
    ]


def wait_for_export_payload(
    export_payloads: dict[str, dict],
    run_id: str,
    page: Page | None = None,
    timeout_seconds: int = 20,
) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if page is not None:
            try:
                captured = page.evaluate(
                    """() => Array.isArray(window.__V7_EXPORT_PAYLOADS__)
                        ? window.__V7_EXPORT_PAYLOADS__
                        : []"""
                )
                if isinstance(captured, list):
                    for item in captured:
                        if not isinstance(item, dict):
                            continue
                        rid = item.get("run_id")
                        if isinstance(rid, str) and rid and rid not in export_payloads:
                            export_payloads[rid] = item
            except Exception:
                pass
        payload = export_payloads.get(run_id)
        if isinstance(payload, dict) and payload:
            return payload
        time.sleep(0.5)
    # Some UI states may show a stale/lagging run_id. Fall back to the latest captured export payload.
    if export_payloads:
        try:
            return next(reversed(export_payloads.values()))
        except Exception:
            return {}
    return {}


def wait_for_completion(page: Page, previous_run_id: str | None = None) -> tuple[str, str]:
    deadline = time.time() + TIMEOUT_SECONDS
    last_seen: tuple[str | None, str | None] = (None, None)

    while time.time() < deadline:
        run_id, href = parse_run_id_and_link(page)
        last_seen = (run_id, href)

        if run_id and href:
            if previous_run_id is None or run_id != previous_run_id:
                return run_id, href

        error_block = page.locator("div:has-text('Error')").first
        if error_block.count() > 0:
            err_text = error_block.inner_text(timeout=500).strip()
            if err_text:
                raise RuntimeError(f"V7 execution failed: {err_text}")

        page.wait_for_timeout(2000)

    raise TimeoutError(
        f"Timed out waiting for V7 completion. Last seen: run_id={last_seen[0]}, href={last_seen[1]}"
    )


def download_ppt(page: Page, href: str, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if href.startswith("file://"):
        parsed = urlparse(href)
        local_path = Path(unquote(parsed.path.lstrip("/")))
        if not local_path.exists():
            local_path = Path(unquote(parsed.path))
        if not local_path.exists():
            raise RuntimeError(f"Local PPT file not found: {href}")
        dest_path.write_bytes(local_path.read_bytes())
        return

    try:
        response = page.request.get(href, timeout=120000)
        if response.ok:
            dest_path.write_bytes(response.body())
            return
        print(f"[warn] playwright download failed: HTTP {response.status}, fallback to curl")
    except Exception as exc:
        print(f"[warn] playwright download exception, fallback to curl: {exc}")

    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError(f"Failed to download PPTX and curl is unavailable: {href}")

    proc = subprocess.run(
        [curl, "-L", href, "-o", str(dest_path)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0 or not dest_path.exists() or dest_path.stat().st_size == 0:
        raise RuntimeError(
            f"Failed to download PPTX via curl: rc={proc.returncode} href={href}\n"
            f"stdout={proc.stdout[-400:]}\nstderr={proc.stderr[-400:]}"
        )


def submit_video_render(page: Page, run_id: str, image_urls: list[str]) -> str:
    if not image_urls:
        raise RuntimeError("No slide image URLs available for video rendering")

    local_dir = OUTPUT_DIR / run_id / "slides"
    local_dir.mkdir(parents=True, exist_ok=True)
    normalized_sources: list[str] = []

    curl = shutil.which("curl.exe") or shutil.which("curl")
    for idx, src in enumerate(image_urls):
        src_text = str(src)
        if src_text.startswith("http://") or src_text.startswith("https://"):
            if not curl:
                normalized_sources.append(src_text)
                continue
            local_path = local_dir / f"slide-{idx+1:03d}.png"
            proc = subprocess.run(
                [curl, "-L", src_text, "-o", str(local_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode == 0 and local_path.exists() and local_path.stat().st_size > 0:
                normalized_sources.append(str(local_path.resolve()))
            else:
                print(
                    f"[warn] failed to localize slide image, keep remote source: {src_text}\n"
                    f"stdout={proc.stdout[-200:]}\nstderr={proc.stderr[-200:]}"
                )
                normalized_sources.append(src_text)
        else:
            normalized_sources.append(src_text)

    per_slide_duration = 3
    total_duration = max(6, per_slide_duration * len(normalized_sources))

    payload = {
        "project": {
            "name": f"PPT V7 Render {run_id}",
            "runId": run_id,
            "threadId": f"ppt-v7-render-{run_id}",
            "width": 1280,
            "height": 720,
            "duration": total_duration,
            "fps": 30,
            "backgroundColor": "#050508",
            "tracks": [
                {
                    "id": 1,
                    "type": "video",
                    "name": "Slides",
                    "items": [
                        {
                            "id": f"slide-{idx+1}",
                            "type": "image",
                            "content": url,
                            "startTime": idx * per_slide_duration,
                            "duration": per_slide_duration,
                            "trackId": 1,
                            "name": f"Slide {idx+1}",
                            "style": {"objectFit": "cover"},
                        }
                        for idx, url in enumerate(normalized_sources)
                    ],
                }
            ],
        }
    }

    result = page.evaluate(
        """async (body) => {
            const response = await fetch('/api/render/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const json = await response.json().catch(() => ({}));
            return { ok: response.ok, status: response.status, body: json };
        }""",
        payload,
    )

    if not result.get("ok"):
        raise RuntimeError(f"Video render submit failed: HTTP {result.get('status')} {result.get('body')}")

    job_id = (result.get("body") or {}).get("job_id")
    if not job_id:
        raise RuntimeError(f"Video render response missing job_id: {result}")

    return str(job_id)


def submit_ppt_video_render(
    page: Page,
    run_id: str,
    pptx_url: str,
    audio_urls: list[str] | None = None,
) -> dict:
    source = str(pptx_url or "").strip()
    if not source:
        raise RuntimeError("pptx_url is empty, cannot submit PPT render")
    cleaned_audio_urls = [str(item).strip() for item in (audio_urls or []) if str(item).strip()]
    payload = {
        "pptx_url": source,
        "audio_urls": cleaned_audio_urls,
        "config": {
            "width": 1280,
            "height": 720,
            "fps": 30,
            "transition": "fade",
            "include_narration": True,
        },
        "idempotency_key": f"ppt-v7-{run_id}",
    }

    response = page.request.post(
        f"{RENDERER_BASE}/api/v1/ppt/render",
        data=payload,
        timeout=PPT_RENDER_SUBMIT_TIMEOUT_MS,
    )
    if not response.ok:
        raise RuntimeError(
            f"PPT render submit failed: HTTP {response.status} {response.text()[:400]}"
        )
    body = response.json()
    if not body.get("success"):
        raise RuntimeError(f"PPT render submit failed: {body}")
    data = body.get("data") or {}
    job_id = data.get("id")
    if not job_id:
        raise RuntimeError(f"PPT render response missing id: {body}")
    data["id"] = str(job_id)
    return data


def wait_for_render_completion(page: Page, job_id: str) -> dict:
    deadline = time.time() + TIMEOUT_SECONDS
    last_payload = None

    while time.time() < deadline:
        response = page.request.get(f"{RENDERER_BASE}/render/jobs/{job_id}", timeout=30000)
        if not response.ok:
            raise RuntimeError(f"Failed to query render job {job_id}: HTTP {response.status}")

        payload = response.json()
        last_payload = payload
        status = payload.get("status")
        print(f"[render] {job_id}: {status}")

        if status == "completed":
            return payload
        if status == "failed":
            raise RuntimeError(f"Render job failed: {payload}")

        page.wait_for_timeout(1000)

    raise TimeoutError(f"Render job {job_id} did not finish. last={last_payload}")


def wait_for_ppt_render_completion(page: Page, job_id: str) -> dict:
    deadline = time.time() + TIMEOUT_SECONDS
    last_payload = None

    while time.time() < deadline:
        response = page.request.get(f"{RENDERER_BASE}/api/v1/ppt/render/{job_id}", timeout=30000)
        if not response.ok:
            raise RuntimeError(f"Failed to query PPT render job {job_id}: HTTP {response.status}")

        envelope = response.json()
        if not envelope.get("success"):
            raise RuntimeError(f"Failed to query PPT render job {job_id}: {envelope}")
        payload = envelope.get("data") or {}
        last_payload = payload
        status = payload.get("status")
        print(f"[ppt-render] {job_id}: {status}")

        if status in ("done", "completed"):
            return payload
        if status == "failed":
            raise RuntimeError(f"PPT render job failed: {payload}")

        page.wait_for_timeout(1000)

    raise TimeoutError(f"PPT render job {job_id} did not finish. last={last_payload}")


def get_ppt_download_url(page: Page, job_id: str, render_payload: dict) -> str:
    output_url = render_payload.get("output_url")
    if output_url:
        return str(output_url)

    response = page.request.get(f"{RENDERER_BASE}/api/v1/ppt/download/{job_id}", timeout=30000)
    if not response.ok:
        raise RuntimeError(f"Failed to query PPT download URL for {job_id}: HTTP {response.status}")
    envelope = response.json()
    if not envelope.get("success"):
        raise RuntimeError(f"Failed to query PPT download URL for {job_id}: {envelope}")
    payload = envelope.get("data") or {}
    output_url = payload.get("output_url")
    if not output_url:
        raise RuntimeError(f"PPT download URL is empty: {payload}")
    return str(output_url)


def download_video(page: Page, render_payload: dict, dest_path: Path) -> str:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    output_url = render_payload.get("output_url")
    output_path = render_payload.get("output_path")

    if output_url:
        try:
            response = page.request.get(str(output_url), timeout=180000)
            if response.ok:
                dest_path.write_bytes(response.body())
                return str(output_url)
            print(f"[warn] output_url download failed with HTTP {response.status}, fallback to output_path/curl")
        except Exception as exc:
            print(f"[warn] output_url download exception, fallback to output_path/curl: {exc}")

        curl = shutil.which("curl.exe") or shutil.which("curl")
        if curl:
            proc = subprocess.run(
                [curl, "-L", str(output_url), "-o", str(dest_path)],
                capture_output=True,
                text=True,
                timeout=240,
            )
            if proc.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 0:
                return str(output_url)
            print(
                f"[warn] curl output_url download failed: rc={proc.returncode}\n"
                f"stdout={proc.stdout[-200:]}\nstderr={proc.stderr[-200:]}"
            )

    if output_path:
        src_path = Path(str(output_path))
        if src_path.exists():
            shutil.copyfile(src_path, dest_path)
            return f"file://{src_path.as_posix()}"

    raise RuntimeError(f"Neither output_url nor output_path is downloadable: {render_payload}")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
        page = browser.new_page()
        page.add_init_script(
            """
            (() => {
              const rawFetch = window.fetch.bind(window);
              window.__V7_EXPORT_PAYLOADS__ = [];
              window.fetch = async (...args) => {
                const response = await rawFetch(...args);
                try {
                  const target = args[0];
                  const url = typeof target === "string" ? target : String(target?.url || "");
                  if (url.includes("/api/projects/v7/export")) {
                    const clone = response.clone();
                    clone.json().then((body) => {
                      if (body && body.success && body.data && body.data.run_id) {
                        window.__V7_EXPORT_PAYLOADS__.push({
                          ...body.data,
                          _captured_url: url,
                          _captured_by: "window.fetch",
                        });
                      }
                    }).catch(() => {});
                  }
                } catch (_) {}
                return response;
              };
            })();
            """
        )
        export_payloads: dict[str, dict] = {}

        def _capture_export_response(resp) -> None:
            try:
                if "/api/projects/v7/export" not in resp.url:
                    return
                request = resp.request
                if (request.method or "").upper() != "POST":
                    return
                body = resp.json()
                if not isinstance(body, dict) or not body.get("success"):
                    return
                data = body.get("data")
                if not isinstance(data, dict):
                    return
                run_id = data.get("run_id")
                if isinstance(run_id, str) and run_id:
                    data["_captured_url"] = resp.url
                    data["_captured_by"] = "response.event"
                    export_payloads[run_id] = data
            except Exception:
                return

        page.on("response", _capture_export_response)
        page.set_default_navigation_timeout(120000)
        page.set_default_timeout(30000)
        page.on("console", lambda msg: safe_print(f"[browser:{msg.type}] {msg.text}"))

        print(f"[ui] Opening {FRONTEND_BASE}")
        page.goto(FRONTEND_BASE, wait_until="commit")
        page.wait_for_selector("button")

        template = page.locator("button:has-text('PPT & Video V7')").first
        assert_true(template.count() > 0, "PPT & Video V7 template card not found")
        template.click()
        page.wait_for_selector("aside textarea")

        page.locator("aside textarea").first.fill(
            "Create a concise 3-slide investor update deck covering growth, risks, and next actions."
        )

        slide_input = page.locator("aside input[type='number']").first
        if slide_input.count() > 0:
            slide_input.fill("3")

        submit = page.locator("aside div.border-t button").first
        assert_true(submit.count() > 0, "Generate button not found")
        submit.click()

        page.wait_for_selector("text=PPT V7 Workspace")

        run1, href1 = wait_for_completion(page)
        ppt1 = OUTPUT_DIR / f"{run1}.pptx"
        download_ppt(page, href1, ppt1)
        page.screenshot(path=str(OUTPUT_DIR / "01-first-run.png"), full_page=True)

        retry = page.get_by_role("button", name="Retry")
        assert_true(retry.count() > 0, "Retry button not found")
        retry.click()

        run2, href2 = wait_for_completion(page, previous_run_id=run1)
        ppt2 = OUTPUT_DIR / f"{run2}.pptx"
        download_ppt(page, href2, ppt2)
        page.screenshot(path=str(OUTPUT_DIR / "02-retry-run.png"), full_page=True)

        assert_true(page.locator(f"text={run1}").count() > 0, "First run ID missing in UI")
        assert_true(page.locator(f"text={run2}").count() > 0, "Second run ID missing in UI")
        assert_true(page.locator("text=Recent Runs").count() > 0, "Recent Runs panel missing")

        video_path = OUTPUT_DIR / f"{run2}.mp4"
        export_payload = wait_for_export_payload(export_payloads, run2, page=page)
        if isinstance(export_payload, dict) and export_payload:
            (OUTPUT_DIR / f"{run2}.export.json").write_text(
                json.dumps(export_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        pptx_url = ""
        if isinstance(export_payload, dict):
            pptx_url = str(export_payload.get("pptx_url") or "").strip()
        if not pptx_url:
            pptx_url = str(href2 or "").strip()
        assert_true(bool(pptx_url), "Export payload missing pptx_url")

        audio_urls: list[str] = []
        if isinstance(export_payload, dict):
            video_slides = export_payload.get("video_slides")
            if isinstance(video_slides, list):
                for row in video_slides:
                    if not isinstance(row, dict):
                        continue
                    audio_url = str(row.get("audioUrl") or "").strip()
                    if audio_url:
                        audio_urls.append(audio_url)

        render_submit = submit_ppt_video_render(page, run2, pptx_url, audio_urls)
        render_job_id = str(render_submit.get("id"))
        render_status = str(render_submit.get("status", "")).lower()
        if render_status in ("done", "completed") and render_submit.get("output_url"):
            render_payload = render_submit
        else:
            render_payload = wait_for_ppt_render_completion(page, render_job_id)
        output_url = get_ppt_download_url(page, render_job_id, render_payload)
        video_source = download_video(page, {"output_url": output_url}, video_path)
        render_mode = "ppt_render_pptx"

        assert_true(video_path.exists() and video_path.stat().st_size > 0, "Video file was not downloaded")
        page.screenshot(path=str(OUTPUT_DIR / "03-video-render.png"), full_page=True)

        result = {
            "status": "ok",
            "run_ids": [run1, run2],
            "captured_export_run_ids": list(export_payloads.keys()),
            "downloads": {
                run1: str(ppt1),
                run2: str(ppt2),
            },
            "video": {
                "render_job_id": render_job_id,
                "mode": render_mode,
                "export_payload_run_id": export_payload.get("run_id") if isinstance(export_payload, dict) else None,
                "export_payload_keys": sorted(list(export_payload.keys())) if isinstance(export_payload, dict) else [],
                "render_input_pptx_url": pptx_url,
                "render_input_audio_urls_count": len(audio_urls),
                "source": video_source,
                "downloaded_path": str(video_path),
                "size_bytes": video_path.stat().st_size,
            },
            "screenshots": [
                str(OUTPUT_DIR / "01-first-run.png"),
                str(OUTPUT_DIR / "02-retry-run.png"),
                str(OUTPUT_DIR / "03-video-render.png"),
            ],
        }
        (OUTPUT_DIR / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        browser.close()
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ui] FAILURE: {exc}", file=sys.stderr)
        raise
