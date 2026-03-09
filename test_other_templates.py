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


def test_product_ad(page):
    """测试爆款产品广告模板"""
    log("=" * 60)
    log("测试爆款产品广告模板")
    log("=" * 60)

    try:
        # 1. 首页
        log("\n[1] 加载首页...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        page.screenshot(path="product_test_01_home.png")

        # 2. 点击爆款产品广告
        log("\n[2] 点击爆款产品广告模板...")
        dh = page.locator('button:has-text("爆款产品广告")')
        if dh.count() > 0:
            dh.first.scroll_into_view_if_needed()
            time.sleep(0.5)
            dh.first.click()
            log("    ✓ 点击成功")

        time.sleep(3)
        page.wait_for_load_state("networkidle")
        page.screenshot(path="product_test_02_clicked.png")

        # 3. 检查表单
        log("\n[3] 检查表单...")
        text = page.locator("body").inner_text()
        log(f"    页面文本: {text[:200]}...")

        # 检查aside侧边栏
        aside = page.locator("aside")
        if aside.count() > 0 and aside.first.is_visible():
            log("    ✓ 侧边栏可见")
            aside_text = aside.first.inner_text()
            log(f"    侧边栏内容长度: {len(aside_text)}")

        # 4. 填写表单
        log("\n[4] 填写表单...")

        # 主题
        try:
            theme = page.locator("textarea").first
            if theme.is_visible():
                theme.fill("测试爆款产品广告")
                log("    ✓ 填写主题")
        except Exception as e:
            log(f"    - 填写主题: {e}")

        # 图片URL
        try:
            inputs = page.locator('input[type="text"]').all()
            for i, inp in enumerate(inputs):
                if inp.is_visible():
                    inp.fill(
                        "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
                    )
                    log(f"    ✓ 填写图片URL (input {i})")
                    break
        except Exception as e:
            log(f"    - 填写图片URL: {e}")

        page.screenshot(path="product_test_03_filled.png")

        # 5. 点击生成
        log("\n[5] 点击生成...")
        try:
            btn = page.locator('button:has-text("开始生成")')
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                log("    ✓ 点击开始生成")
        except Exception as e:
            log(f"    - 点击开始生成: {e}")

        time.sleep(3)
        page.screenshot(path="product_test_04_submit.png")

        log("\n测试完成!")
        return True

    except Exception as e:
        log(f"\n错误: {e}")
        return False


def test_knowledge_edu(page):
    """测试知识科普模板"""
    log("\n" + "=" * 60)
    log("测试知识科普模板")
    log("=" * 60)

    try:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 点击知识科普
        log("\n[1] 点击知识科普模板...")
        btn = page.locator('button:has-text("知识科普")')
        if btn.count() > 0:
            btn.first.scroll_into_view_if_needed()
            time.sleep(0.5)
            btn.first.click()
            log("    ✓ 点击成功")

        time.sleep(3)
        page.wait_for_load_state("networkidle")
        page.screenshot(path="knowledge_test_01_clicked.png")

        # 检查表单
        aside = page.locator("aside")
        if aside.count() > 0 and aside.first.is_visible():
            log("    ✓ 侧边栏可见")

        # 填写
        try:
            theme = page.locator("textarea").first
            if theme.is_visible():
                theme.fill("测试知识科普视频")
                log("    ✓ 填写主题")
        except:
            pass

        page.screenshot(path="knowledge_test_02_filled.png")

        # 提交
        try:
            btn = page.locator('button:has-text("开始生成")')
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                log("    ✓ 点击开始生成")
        except:
            pass

        time.sleep(3)
        page.screenshot(path="knowledge_test_03_submit.png")

        log("\n知识科普测试完成!")
        return True

    except Exception as e:
        log(f"错误: {e}")
        return False


def main():
    log("继续测试其他模板")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})

        # 测试爆款产品广告
        test_product_ad(page)

        time.sleep(3)

        # 测试知识科普
        test_knowledge_edu(page)

        log("\n浏览器将在10秒后关闭...")
        time.sleep(10)
        browser.close()


main()
