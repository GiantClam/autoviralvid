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
    log("检查首页结构...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})

        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 获取所有按钮
        log("\n所有按钮:")
        buttons = page.locator("button").all()
        for i, btn in enumerate(buttons):
            try:
                text = btn.inner_text().strip()
                if text:
                    log(f"  [{i}] {text[:50]}")
            except:
                pass

        # 查找数字人口播按钮
        log("\n查找数字人口播按钮...")
        dh = page.locator('button:has-text("数字人口播")')
        if dh.count() > 0:
            log(f"找到 {dh.count()} 个")
            dh.first.click()
            time.sleep(5)

            page.screenshot(path="after_click.png")

            # 检查页面结构
            log("\n点击后页面结构:")
            log(f"  URL: {page.url}")

            # 获取所有可见文本
            text = page.locator("body").inner_text()
            log(f"  文本长度: {len(text)}")
            log(f"  文本内容: {text[:200]}...")

            # 检查是否有aside
            aside = page.locator("aside").count()
            log(f"  aside数量: {aside}")

        time.sleep(10)
        browser.close()


main()
