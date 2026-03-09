#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"


def log(msg):
    print(msg, flush=True)


def test_digital_human(page):
    """详细测试数字人口播模板"""
    log("=" * 60)
    log("测试数字人口播模板")
    log("=" * 60)

    try:
        # 1. 首页
        log("\n[1] 加载首页...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 获取页面文本长度来验证内容
        text = page.locator("body").inner_text()
        log(f"    首页文本长度: {len(text)} 字符")
        page.screenshot(path="dh_test_01_home.png")

        # 2. 点击数字人口播
        log("\n[2] 点击数字人口播模板...")
        selectors = [
            'button:has-text("数字人口播")',
            "text=数字人口播",
        ]

        for selector in selectors:
            try:
                elem = page.locator(selector).first
                if elem.is_visible(timeout=3000):
                    elem.scroll_into_view_if_needed()
                    time.sleep(0.5)
                    elem.click()
                    log(f"    ✓ 使用选择器: {selector}")
                    break
            except:
                continue

        time.sleep(3)
        page.wait_for_load_state("networkidle")

        text = page.locator("body").inner_text()
        log(f"    点击后文本长度: {len(text)} 字符")

        # 检查页面结构
        page.screenshot(path="dh_test_02_clicked.png")

        # 3. 检查侧边栏
        sidebar = page.locator("aside").first
        if sidebar.is_visible():
            log("    ✓ 侧边栏可见")
            sidebar_text = sidebar.inner_text()
            log(f"    侧边栏内容长度: {len(sidebar_text)} 字符")

        # 4. 检查表单元素
        log("\n[3] 检查表单元素...")

        # 查找所有textarea
        textareas = page.locator("textarea").all()
        log(f"    textarea数量: {len(textareas)}")

        # 查找所有input
        inputs = page.locator("input").all()
        log(f"    input数量: {len(inputs)}")

        # 查找所有select
        selects = page.locator("select").all()
        log(f"    select数量: {len(selects)}")

        # 查找所有button
        buttons = page.locator("button").all()
        log(f"    button数量: {len(buttons)}")

        # 显示所有按钮文本
        button_texts = []
        for btn in buttons:
            try:
                if btn.is_visible():
                    text = btn.inner_text().strip()
                    if text:
                        button_texts.append(text)
            except:
                pass
        log(f"    可见按钮: {button_texts[:10]}")

        # 5. 填写表单
        log("\n[4] 填写表单...")

        # 填写主题
        try:
            theme = page.locator("textarea").first
            if theme.is_visible():
                theme.fill("数字人直播带货测试")
                log("    ✓ 填写主题")
        except Exception as e:
            log(f"    ✗ 填写主题失败: {e}")

        # 填写图片URL
        try:
            inputs = page.locator('input[type="text"]').all()
            for i, inp in enumerate(inputs):
                if inp.is_visible() and i == 0:
                    inp.fill(
                        "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
                    )
                    log(f"    ✓ 填写图片URL (input {i})")
                    break
        except Exception as e:
            log(f"    ✗ 填写图片URL失败: {e}")

        # 填写音频URL
        try:
            inputs = page.locator('input[type="text"]').all()
            for i, inp in enumerate(inputs):
                if inp.is_visible() and inp.input_value() == "":
                    inp.fill(
                        "https://actions.google.com/sounds/v1/ambiences/coffee_shop.ogg"
                    )
                    log(f"    ✓ 填写音频URL (input {i})")
                    break
        except Exception as e:
            log(f"    ✗ 填写音频URL失败: {e}")

        # 设置时长
        try:
            duration = page.locator('input[type="number"]').first
            if duration.is_visible():
                duration.fill("30")
                log("    ✓ 设置时长为30秒")
        except Exception as e:
            log(f"    ✗ 设置时长失败: {e}")

        page.screenshot(path="dh_test_03_filled.png")

        # 6. 点击生成
        log("\n[5] 点击生成按钮...")
        try:
            submit = page.locator('button:has-text("生成数字人视频")')
            if submit.count() > 0 and submit.first.is_visible():
                submit.first.click()
                log("    ✓ 点击生成按钮")
            else:
                # 尝试其他按钮
                submit = page.locator('button:has-text("开始生成")')
                if submit.count() > 0 and submit.first.is_visible():
                    submit.first.click()
                    log("    ✓ 点击开始生成按钮")
        except Exception as e:
            log(f"    ✗ 点击生成按钮失败: {e}")

        time.sleep(3)
        page.screenshot(path="dh_test_04_submit.png")

        log("\n[6] 检查提交结果...")
        text = page.locator("body").inner_text()

        if "生成中" in text or "处理中" in text or "loading" in text.lower():
            log("    ✓ 任务已提交，处理中")
        elif "成功" in text or "完成" in text:
            log("    ✓ 任务完成")
        else:
            log(f"    ? 页面状态未知")

        log("\n测试完成!")
        return True

    except Exception as e:
        log(f"\n✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    log("数字人口播模板详细测试")
    log("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})

        test_digital_human(page)

        log("\n浏览器将在10秒后关闭...")
        time.sleep(10)
        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
