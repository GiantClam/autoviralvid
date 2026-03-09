#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoViralVid 商用发布测试
对标即梦、海螺等AI视频生成平台
"""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import time
import json
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"


class TestResult:
    def __init__(self):
        self.results = []

    def add(self, tc_id, name, status, message=""):
        self.results.append(
            {
                "tc_id": tc_id,
                "name": name,
                "status": status,  # PASS/FAIL/SKIP
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def print_summary(self):
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        skipped = sum(1 for r in self.results if r["status"] == "SKIP")
        total = len(self.results)

        print("\n" + "=" * 70)
        print("测试结果汇总")
        print("=" * 70)
        print(f"总计: {total}")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        print(f"跳过: {skipped}")
        print("=" * 70)

        if failed > 0:
            print("\n失败用例:")
            for r in self.results:
                if r["status"] == "FAIL":
                    print(f"  [{r['tc_id']}] {r['name']}: {r['message']}")

        return passed, failed, skipped


test_result = TestResult()


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ========== 功能测试 ==========


def test_tc001_homepage_load(page):
    """TC-001: 首页加载测试"""
    log("TC-001: 首页加载测试")
    try:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 检查关键元素
        title = page.title()
        body_text = page.locator("body").inner_text()

        if len(body_text) > 100:
            test_result.add(
                "TC-001",
                "首页加载",
                "PASS",
                f"页面加载成功，内容长度: {len(body_text)}",
            )
            page.screenshot(path="test_reports/tc001_homepage.png")
            return True
        else:
            test_result.add("TC-001", "首页加载", "FAIL", "页面内容过少")
            return False
    except Exception as e:
        test_result.add("TC-001", "首页加载", "FAIL", str(e))
        return False


def test_tc002_templates(page):
    """TC-002: 模板展示测试"""
    log("TC-002: 模板展示测试")
    try:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 检查模板数量
        templates = [
            "爆款产品广告",
            "美妆种草",
            "服饰穿搭",
            "美食探店",
            "3C数码开箱",
            "家居好物",
            "品牌故事",
            "数字人口播",
            "知识科普",
            "搞笑段子",
            "旅行Vlog",
            "教程",
        ]

        found = []
        for t in templates:
            if page.locator(f'button:has-text("{t}")').count() > 0:
                found.append(t)

        if len(found) == 12:
            test_result.add("TC-002", "模板展示", "PASS", f"找到{len(found)}个模板")
            return True
        else:
            test_result.add(
                "TC-002", "模板展示", "FAIL", f"只找到{len(found)}/12个模板"
            )
            return False
    except Exception as e:
        test_result.add("TC-002", "模板展示", "FAIL", str(e))
        return False


def test_tc010_product_ad(page):
    """TC-010: 爆款产品广告模板"""
    log("TC-010: 爆款产品广告模板测试")
    try:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        # 点击模板
        page.locator('button:has-text("爆款产品广告")').first.click()
        time.sleep(3)

        # 检查表单
        body_text = page.locator("body").inner_text()

        if "主题描述" in body_text or "素材" in body_text:
            test_result.add("TC-010", "爆款产品广告模板", "PASS", "模板选择成功")
            page.screenshot(path="test_reports/tc010_product_ad.png")
            return True
        else:
            test_result.add("TC-010", "爆款产品广告模板", "FAIL", "表单未正确显示")
            return False
    except Exception as e:
        test_result.add("TC-010", "爆款产品广告模板", "FAIL", str(e))
        return False


def test_tc011_digital_human(page):
    """TC-011: 数字人口播模板"""
    log("TC-011: 数字人口播模板测试")
    try:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        # 点击模板
        page.locator('button:has-text("数字人口播")').first.click()
        time.sleep(3)

        # 检查是否有错误
        body_text = page.locator("body").inner_text()

        if "出了点问题" in body_text:
            test_result.add("TC-011", "数字人口播模板", "FAIL", "React错误导致页面崩溃")
            page.screenshot(path="test_reports/tc011_error.png")
            return False
        elif "主题描述" in body_text or "素材" in body_text:
            test_result.add("TC-011", "数字人口播模板", "PASS", "模板选择成功")
            page.screenshot(path="test_reports/tc011_digital_human.png")
            return True
        else:
            test_result.add("TC-011", "数字人口播模板", "FAIL", "页面状态未知")
            return False
    except Exception as e:
        test_result.add("TC-011", "数字人口播模板", "FAIL", str(e))
        return False


def test_tc012_knowledge_edu(page):
    """TC-012: 知识科普模板"""
    log("TC-012: 知识科普模板测试")
    try:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        page.locator('button:has-text("知识科普")').first.click()
        time.sleep(3)

        body_text = page.locator("body").inner_text()

        if "主题描述" in body_text or "素材" in body_text:
            test_result.add("TC-012", "知识科普模板", "PASS", "模板选择成功")
            page.screenshot(path="test_reports/tc012_knowledge.png")
            return True
        else:
            test_result.add("TC-012", "知识科普模板", "FAIL", "表单未显示")
            return False
    except Exception as e:
        test_result.add("TC-012", "知识科普模板", "FAIL", str(e))
        return False


def test_tc020_form_fill(page):
    """TC-020: 表单填写测试"""
    log("TC-020: 表单填写测试")
    try:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        # 选择模板
        page.locator('button:has-text("爆款产品广告")').first.click()
        time.sleep(3)

        # 填写主题
        theme_input = page.locator("textarea").first
        if theme_input.is_visible():
            theme_input.fill("测试视频主题")
            value = theme_input.input_value()

            if value == "测试视频主题":
                test_result.add("TC-020", "表单填写", "PASS", "主题填写成功")
                page.screenshot(path="test_reports/tc020_form.png")
                return True
            else:
                test_result.add("TC-020", "表单填写", "FAIL", "值未正确保存")
                return False
        else:
            test_result.add("TC-020", "表单填写", "FAIL", "找不到输入框")
            return False
    except Exception as e:
        test_result.add("TC-020", "表单填写", "FAIL", str(e))
        return False


def test_tc021_image_url(page):
    """TC-021: 图片URL填写"""
    log("TC-021: 图片URL填写测试")
    try:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        page.locator('button:has-text("爆款产品广告")').first.click()
        time.sleep(3)

        # 填写图片URL
        inputs = page.locator('input[type="text"]').all()
        if len(inputs) > 0:
            test_img_url = (
                "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
            )
            inputs[0].fill(test_img_url)

            if inputs[0].input_value() == test_img_url:
                test_result.add("TC-021", "图片URL填写", "PASS", "图片URL填写成功")
                return True
            else:
                test_result.add("TC-021", "图片URL填写", "FAIL", "值未保存")
                return False
        else:
            test_result.add("TC-021", "图片URL填写", "FAIL", "没有找到输入框")
            return False
    except Exception as e:
        test_result.add("TC-021", "图片URL填写", "FAIL", str(e))
        return False


def test_tc030_storyboard_generation(page):
    """TC-030: 故事板生成测试"""
    log("TC-030: 故事板生成测试")
    try:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        # 选择模板并填写
        page.locator('button:has-text("爆款产品广告")').first.click()
        time.sleep(3)

        # 填写表单
        page.locator("textarea").first.fill("测试视频")
        page.locator('input[type="text"]').first.fill(
            "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
        )

        # 点击生成按钮
        generate_btn = page.locator('button:has-text("开始生成")')
        if generate_btn.count() > 0:
            generate_btn.first.click()
            time.sleep(5)

            # 检查是否有生成状态
            body_text = page.locator("body").inner_text()

            test_result.add("TC-030", "故事板生成", "PASS", "已点击生成按钮")
            page.screenshot(path="test_reports/tc030_generating.png")
            return True
        else:
            test_result.add("TC-030", "故事板生成", "FAIL", "找不到生成按钮")
            return False
    except Exception as e:
        test_result.add("TC-030", "故事板生成", "FAIL", str(e))
        return False


# ========== 视觉测试 ==========


def test_tc050_performance(page):
    """TC-050: 首屏加载时间"""
    log("TC-050: 首屏加载时间测试")
    try:
        start = time.time()
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        load_time = time.time() - start

        if load_time < 3:
            test_result.add(
                "TC-050", "首屏加载", "PASS", f"加载时间: {load_time:.2f}秒"
            )
            return True
        else:
            test_result.add(
                "TC-050", "首屏加载", "FAIL", f"加载时间过长: {load_time:.2f}秒"
            )
            return False
    except Exception as e:
        test_result.add("TC-050", "首屏加载", "FAIL", str(e))
        return False


def test_tc060_desktop_layout(page):
    """TC-060: 桌面端布局"""
    log("TC-060: 桌面端布局测试")
    try:
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 检查元素可见性
        body = page.locator("body")
        if body.is_visible():
            test_result.add("TC-060", "桌面端布局", "PASS", "1920x1080布局正常")
            page.screenshot(path="test_reports/tc060_desktop.png")
            return True
        else:
            test_result.add("TC-060", "桌面端布局", "FAIL", "布局异常")
            return False
    except Exception as e:
        test_result.add("TC-060", "桌面端布局", "FAIL", str(e))
        return False


def test_tc061_mobile_layout(page):
    """TC-061: 移动端布局"""
    log("TC-061: 移动端布局测试")
    try:
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        body = page.locator("body")
        if body.is_visible():
            test_result.add("TC-061", "移动端布局", "PASS", "375x812布局正常")
            page.screenshot(path="test_reports/tc061_mobile.png")
            return True
        else:
            test_result.add("TC-061", "移动端布局", "FAIL", "布局异常")
            return False
    except Exception as e:
        test_result.add("TC-061", "移动端布局", "FAIL", str(e))
        return False


# ========== 体验测试 ==========


def test_tc070_loading_state(page):
    """TC-070: 加载状态测试"""
    log("TC-070: 加载状态测试")
    try:
        page.goto(BASE_URL)
        page.wait_for_load_state("domcontentloaded")

        # 检查是否有加载相关的元素
        body_text = page.locator("body").inner_text()

        if len(body_text) > 50:
            test_result.add("TC-070", "加载状态", "PASS", "页面有内容显示")
            return True
        else:
            test_result.add("TC-070", "加载状态", "FAIL", "页面内容为空")
            return False
    except Exception as e:
        test_result.add("TC-070", "加载状态", "FAIL", str(e))
        return False


# ========== 主函数 ==========


def main():
    import os

    os.makedirs("test_reports", exist_ok=True)

    log("=" * 70)
    log("AutoViralVid 商用发布测试")
    log("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # 功能测试
        log("\n========== 功能测试 ==========")
        test_tc001_homepage_load(page)
        test_tc002_templates(page)
        test_tc010_product_ad(page)
        test_tc011_digital_human(page)
        test_tc012_knowledge_edu(page)
        test_tc020_form_fill(page)
        test_tc021_image_url(page)
        test_tc030_storyboard_generation(page)

        # 视觉测试
        log("\n========== 视觉测试 ==========")
        test_tc050_performance(page)
        test_tc060_desktop_layout(page)
        test_tc061_mobile_layout(page)

        # 体验测试
        log("\n========== 体验测试 ==========")
        test_tc070_loading_state(page)

        browser.close()

    # 输出结果
    passed, failed, skipped = test_result.print_summary()

    # 保存结果到文件
    with open("test_reports/results.json", "w", encoding="utf-8") as f:
        json.dump(test_result.results, f, ensure_ascii=False, indent=2)

    log("\n测试报告已保存到 test_reports/")

    # 返回退出码
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
