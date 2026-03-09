#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"


def log(msg):
    print(msg, flush=True)


def main():
    log("测试数字人口播并捕获错误...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        # 创建带控制台日志的上下文
        context = browser.new_context()
        page = context.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})

        # 监听控制台消息
        console_messages = []

        def on_console(msg):
            console_messages.append(f"[{msg.type}] {msg.text}")

        page.on("console", on_console)

        # 监听页面错误
        page_errors = []

        def on_error(error):
            page_errors.append(str(error))

        page.on("pageerror", on_error)

        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        log("首页加载完成")

        # 点击数字人口播
        dh = page.locator('button:has-text("数字人口播")')
        if dh.count() > 0:
            dh.first.click()
            log("点击了数字人口播按钮")

        time.sleep(5)
        page.screenshot(path="error_check.png")

        # 输出控制台消息
        log("\n控制台消息:")
        for msg in console_messages[-20:]:
            log(f"  {msg}")

        # 输出页面错误
        log("\n页面错误:")
        for err in page_errors:
            log(f"  {err}")

        # 检查页面内容
        text = page.locator("body").inner_text()
        log(f"\n页面文本: {text[:200]}")

        time.sleep(10)
        browser.close()


main()
