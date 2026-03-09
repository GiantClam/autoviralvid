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

# 文件路径
PHOTO_PATH = r"C:\Users\liula\Downloads\ComfyUI_00011_pcxyj_1764731727.png"
AUDIO_PATH = r"C:\Users\liula\Downloads\1766630274666746137-348477315510412.mp3"
FILE_SERVER_PORT = 8765

print("=" * 60)
print("Digital Human Test - Simple Version")
print("=" * 60)

# 检查文件
print(f"\n[1] Checking files...")
if os.path.exists(PHOTO_PATH):
    print(f"    OK: Photo exists ({os.path.getsize(PHOTO_PATH) / 1024:.1f}KB)")
else:
    print(f"    ERROR: Photo not found: {PHOTO_PATH}")
    sys.exit(1)

if os.path.exists(AUDIO_PATH):
    print(f"    OK: Audio exists ({os.path.getsize(AUDIO_PATH) / 1024 / 1024:.1f}MB)")
else:
    print(f"    ERROR: Audio not found: {AUDIO_PATH}")
    sys.exit(1)

# 启动文件服务器
print(f"\n[2] Starting file server on port {FILE_SERVER_PORT}...")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_server():
    try:
        with socketserver.TCPServer(("", FILE_SERVER_PORT), QuietHandler) as httpd:
            print(f"    OK: Server running on http://localhost:{FILE_SERVER_PORT}")
            httpd.serve_forever()
    except Exception as e:
        print(f"    ERROR: {e}")


server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()
time.sleep(2)

photo_url = f"http://localhost:{FILE_SERVER_PORT}/ComfyUI_00011_pcxyj_1764731727.png"
audio_url = (
    f"http://localhost:{FILE_SERVER_PORT}/1766630274666746137-348477315510412.mp3"
)
print(f"    Photo URL: {photo_url}")
print(f"    Audio URL: {audio_url}")

# 启动浏览器测试
print(f"\n[3] Starting browser automation...")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})

    print("    Navigating to http://localhost:3000...")
    page.goto("http://localhost:3000")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    page.screenshot(path="test_01_home.png")
    print("    OK: Homepage loaded and screenshot saved")

    # 查找数字人口播按钮
    print("\n[4] Finding Digital Human template...")
    try:
        # 尝试多种选择器
        dh_button = page.locator('button:has-text("数字人口播")')
        if dh_button.count() > 0:
            print("    Found: '数字人口播' button")
            dh_button.first.click()
        else:
            # 滚动查找
            print("    Button not visible, scrolling...")
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 500)")
                time.sleep(1)
                dh_button = page.locator('button:has-text("数字人口播")')
                if dh_button.count() > 0:
                    print("    Found after scroll")
                    dh_button.first.click()
                    break
    except Exception as e:
        print(f"    Error: {e}")

    time.sleep(3)
    page.wait_for_load_state("networkidle")
    page.screenshot(path="test_02_after_click.png")
    print("    OK: Template clicked, screenshot saved")

    # 填写表单
    print("\n[5] Filling form...")

    # 找到所有输入框并填写
    inputs = page.locator('input[type="text"]').all()
    print(f"    Found {len(inputs)} text inputs")

    # 填写主题
    try:
        theme_input = page.locator("textarea").first
        if theme_input.is_visible():
            theme_input.fill("数字人直播带货测试 - 10分钟视频")
            print("    OK: Theme filled")
    except Exception as e:
        print(f"    Theme error: {e}")

    # 填写图片URL - 找第二个可见的输入框
    try:
        for i, inp in enumerate(inputs):
            if inp.is_visible():
                placeholder = inp.get_attribute("placeholder") or ""
                inp.fill(photo_url)
                print(f"    OK: Filled input {i} with photo URL")
                break
    except Exception as e:
        print(f"    Photo URL error: {e}")

    # 填写音频URL
    try:
        for i, inp in enumerate(inputs):
            if inp.is_visible() and inp.input_value() == "":
                inp.fill(audio_url)
                print(f"    OK: Filled input {i} with audio URL")
                break
    except Exception as e:
        print(f"    Audio URL error: {e}")

    # 设置时长为600秒
    try:
        duration_input = page.locator('input[type="number"]').first
        if duration_input.is_visible():
            duration_input.fill("600")
            print("    OK: Duration set to 600s")
    except Exception as e:
        print(f"    Duration error: {e}")

    page.screenshot(path="test_03_form_filled.png")
    print("    OK: Form filled, screenshot saved")

    # 点击生成按钮
    print("\n[6] Submitting...")
    try:
        submit_btn = page.locator('button:has-text("生成数字人视频")')
        if submit_btn.count() > 0:
            submit_btn.first.click()
            print("    OK: Clicked generate button")
        else:
            # 尝试其他按钮
            submit_btn = page.locator('button:has-text("开始生成")')
            if submit_btn.count() > 0:
                submit_btn.first.click()
                print("    OK: Clicked start button")
    except Exception as e:
        print(f"    Submit error: {e}")

    time.sleep(5)
    page.screenshot(path="test_04_submitted.png")
    print("    OK: Submitted, screenshot saved")

    print("\n[7] Waiting for generation (manual check needed)...")
    print("    Browser will stay open for 30 seconds...")
    time.sleep(30)

    browser.close()
    print("\nDone!")
