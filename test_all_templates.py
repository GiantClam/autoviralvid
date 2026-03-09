#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import time
from playwright.sync_api import sync_playwright

# 测试配置
BASE_URL = "http://localhost:3000"

# 所有模板及其描述
TEMPLATES = [
    ("product-ad", "爆款产品广告"),
    ("beauty-review", "美妆种草"),
    ("fashion-style", "服饰穿搭"),
    ("food-showcase", "美食探店"),
    ("tech-unbox", "3C数码开箱"),
    ("home-living", "家居好物"),
    ("brand-story", "品牌故事"),
    ("digital-human", "数字人口播"),
    ("knowledge-edu", "知识科普"),
    ("funny-skit", "搞笑段子"),
    ("travel-vlog", "旅行Vlog"),
    ("tutorial", "教程"),
]


def log(msg):
    print(msg, flush=True)


def test_template(page, template_id, template_name):
    """测试单个模板"""
    log(f"\n{'=' * 50}")
    log(f"测试模板: {template_name} ({template_id})")
    log("=" * 50)

    try:
        # 1. 导航到首页
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        page.screenshot(path=f"test_{template_id}_01_home.png")
        log(f"  ✓ 首页加载完成")

        # 2. 查找并点击模板按钮
        # 尝试多种选择器
        selectors = [
            f'button:has-text("{template_name}")',
            f"text={template_name}",
            f'[data-template="{template_id}"]',
        ]

        clicked = False
        for selector in selectors:
            try:
                elem = page.locator(selector).first
                if elem.is_visible(timeout=3000):
                    elem.scroll_into_view_if_needed()
                    time.sleep(0.5)
                    elem.click()
                    log(f"  ✓ 点击模板: {template_name}")
                    clicked = True
                    break
            except:
                continue

        if not clicked:
            # 滚动查找
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 500)")
                time.sleep(1)
                try:
                    elem = page.locator(f'button:has-text("{template_name}")').first
                    if elem.is_visible(timeout=2000):
                        elem.click()
                        log(f"  ✓ 滚动后点击模板: {template_name}")
                        clicked = True
                        break
                except:
                    continue

        if not clicked:
            log(f"  ✗ 无法找到模板按钮")
            return False

        time.sleep(3)
        page.wait_for_load_state("networkidle")
        page.screenshot(path=f"test_{template_id}_02_clicked.png")

        # 3. 检查表单是否出现
        # 检查是否有表单元素
        form_elements = page.locator('textarea, input[type="text"], select').all()
        log(f"  ✓ 表单元素数量: {len(form_elements)}")

        page.screenshot(path=f"test_{template_id}_03_form.png")

        # 4. 填写基本表单信息（如果模板有表单）
        if len(form_elements) > 0:
            # 填写主题
            try:
                theme_input = page.locator("textarea").first
                if theme_input.is_visible():
                    theme_input.fill(f"测试{template_name} - 自动化测试")
                    log(f"  ✓ 填写主题")
            except:
                pass

            # 填写产品图片URL
            try:
                inputs = page.locator('input[type="text"]').all()
                for i, inp in enumerate(inputs):
                    if inp.is_visible() and i == 0:
                        inp.fill(
                            "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
                        )
                        log(f"  ✓ 填写图片URL")
                        break
            except:
                pass

        page.screenshot(path=f"test_{template_id}_04_filled.png")

        # 5. 查找并点击生成按钮
        button_selectors = [
            'button:has-text("开始生成")',
            'button:has-text("生成")',
            'button[type="submit"]',
        ]

        for selector in button_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    log(f"  ✓ 点击生成按钮")
                    break
            except:
                continue

        time.sleep(3)
        page.screenshot(path=f"test_{template_id}_05_submitted.png")

        log(f"  ✓ {template_name} 测试完成!")
        return True

    except Exception as e:
        log(f"  ✗ 测试失败: {e}")
        try:
            page.screenshot(path=f"test_{template_id}_error.png")
        except:
            pass
        return False


def main():
    log("=" * 60)
    log("视频生成模板测试")
    log("=" * 60)

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})

        # 测试每个模板
        for template_id, template_name in TEMPLATES:
            success = test_template(page, template_id, template_name)
            results[template_name] = success

            # 等待一下再测试下一个
            time.sleep(2)

        browser.close()

    # 输出测试结果
    log("\n" + "=" * 60)
    log("测试结果汇总")
    log("=" * 60)

    for template_name, success in results.items():
        status = "✓ 通过" if success else "✗ 失败"
        log(f"  {status}: {template_name}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    log(f"\n总计: {passed}/{total} 通过")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
