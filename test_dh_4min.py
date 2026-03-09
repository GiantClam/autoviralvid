#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
import time
import http.server
import socketserver
import threading

PHOTO_PATH = r"C:\Users\liula\Downloads\ComfyUI_00011_pcxyj_1764731727.png"
AUDIO_PATH = r"C:\Users\liula\Downloads\1766630274666746137-348477315510412.mp3"
FILE_SERVER_PORT = 8765
DURATION = 240  # 4 minutes

print("=" * 60)
print("Digital Human Test - 4 Minutes Video")
print("=" * 60)

# Check files
print(f"\n[1] Checking files...")
if not os.path.exists(PHOTO_PATH):
    print(f"    ERROR: Photo not found")
    sys.exit(1)
if not os.path.exists(AUDIO_PATH):
    print(f"    ERROR: Audio not found")
    sys.exit(1)
print(f"    OK: Photo: {os.path.getsize(PHOTO_PATH) / 1024:.1f}KB")
print(f"    OK: Audio: {os.path.getsize(AUDIO_PATH) / 1024 / 1024:.1f}MB")
print(f"    OK: Duration: {DURATION} seconds (4 minutes)")


# Start file server
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_server():
    try:
        with socketserver.TCPServer(("", FILE_SERVER_PORT), QuietHandler) as httpd:
            httpd.serve_forever()
    except:
        pass


server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()
time.sleep(2)

photo_url = f"http://localhost:{FILE_SERVER_PORT}/ComfyUI_00011_pcxyj_1764731727.png"
audio_url = (
    f"http://localhost:{FILE_SERVER_PORT}/1766630274666746137-348477315510412.mp3"
)
print(f"    OK: File server ready on port {FILE_SERVER_PORT}")

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})

    print("\n[2] Loading homepage...")
    page.goto("http://localhost:3000")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    page.screenshot(path="dh_01_home.png")
    print("    OK: Homepage loaded")

    print("[3] Clicking Digital Human template...")
    dh_button = page.locator('button:has-text("数字人口播")')
    if dh_button.count() > 0:
        dh_button.first.click()
        time.sleep(3)
        page.screenshot(path="dh_02_template.png")
        print("    OK: Template selected")

    print("[4] Filling form...")
    # Theme
    try:
        page.locator("textarea").first.fill("数字人直播带货测试 - 4分钟视频")
    except:
        pass

    # Fill inputs - photo and audio URLs
    inputs = page.locator('input[type="text"]').all()
    filled = 0
    for inp in inputs:
        if inp.is_visible() and filled == 0:
            inp.fill(photo_url)
            filled += 1
        elif inp.is_visible() and filled == 1:
            inp.fill(audio_url)
            filled += 1

    # Set duration to 4 minutes (240 seconds)
    try:
        page.locator('input[type="number"]').first.fill(str(DURATION))
    except:
        pass

    page.screenshot(path="dh_03_form.png")
    print(f"    OK: Form filled, duration: {DURATION}s")

    print("[5] Submitting...")
    submit_btn = page.locator('button:has-text("生成数字人视频")')
    if submit_btn.count() > 0:
        submit_btn.first.click()
        print("    OK: Submitted")

    time.sleep(5)
    page.screenshot(path="dh_04_submitted.png")

    print("\n[6] Waiting for generation...")
    print("    (4-minute video may take 5-15 minutes)\n")

    max_wait = 1200  # 20 minutes max
    check_interval = 30
    elapsed = 0

    while elapsed < max_wait:
        time.sleep(check_interval)
        elapsed += check_interval
        minutes = elapsed // 60

        page.reload()
        time.sleep(2)

        page_text = page.locator("body").inner_text()

        page.screenshot(path=f"dh_progress_{minutes:02d}min.png")
        print(f"    [{minutes:02d} min] Progress screenshot saved")

        if (
            "成功" in page_text
            or "完成" in page_text
            or "video_url" in page_text.lower()
        ):
            print(f"\n    SUCCESS! Video completed!")
            page.screenshot(path="dh_05_completed.png", full_page=True)
            break

        if "失败" in page_text or "错误" in page_text:
            print(f"\n    FAILED!")
            page.screenshot(path="dh_05_failed.png", full_page=True)
            break

    if elapsed >= max_wait:
        print(f"\n    Timeout")
        page.screenshot(path="dh_05_timeout.png", full_page=True)

    page.screenshot(path="dh_final.png", full_page=True)

    print("\nDone! Browser will close in 30 seconds...")
    time.sleep(30)
    browser.close()
