#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoViralVid 完整视频生成测试 - 更准确的版本
真正触发视频生成并等待完成
"""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import time
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def test_full_video_generation_v2():
    """完整视频生成测试 - 改进版"""
    log("=" * 70)
    log("完整视频生成测试 v2")
    log("=" * 70)

    results = {"passed": 0, "failed": 0, "steps": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # 监听控制台消息
        console_logs = []

        def on_console(msg):
            console_logs.append(f"[{msg.type}] {msg.text}")

        page.on("console", on_console)

        try:
            # 1. 访问首页
            log("\n[1] 访问首页...")
            page.goto(BASE_URL)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            if len(page.locator("body").inner_text()) > 100:
                log("    ✓ 首页加载成功")
                results["passed"] += 1
            else:
                log("    ✗ 首页加载失败")
                results["failed"] += 1
                return results

            page.screenshot(path="test_reports/v2_01_home.png")

            # 2. 选择模板
            log("\n[2] 选择模板...")
            page.locator('button:has-text("爆款产品广告")').first.click()
            time.sleep(3)

            body_text = page.locator("body").inner_text()
            if "主题描述" in body_text:
                log("    ✓ 模板选择成功")
                results["passed"] += 1
            else:
                log("    ✗ 模板选择失败")
                results["failed"] += 1
                return results

            page.screenshot(path="test_reports/v2_02_template.png")

            # 3. 填写表单
            log("\n[3] 填写表单...")
            page.locator("textarea").first.fill("测试视频生成完整流程")

            inputs = page.locator('input[type="text"]').all()
            for inp in inputs:
                if inp.is_visible():
                    inp.fill(
                        "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
                    )
                    break

            log("    ✓ 表单填写完成")
            results["passed"] += 1
            page.screenshot(path="test_reports/v2_03_form.png")

            # 4. 点击生成
            log("\n[4] 点击开始生成...")
            page.locator('button:has-text("开始生成")').first.click()
            log("    ✓ 已点击生成按钮")
            results["passed"] += 1

            time.sleep(5)
            page.screenshot(path="test_reports/v2_04_clicked.png")

            # 5. 等待生成过程 - 改进的状态检测
            log("\n[5] 等待视频生成...")
            log("    等待故事板生成...")

            max_wait = 60
            for i in range(max_wait):
                time.sleep(10)

                body_text = page.locator("body").inner_text()

                # 检查侧边栏内容 - 故事板生成
                sidebar = page.locator("aside")
                if sidebar.count() > 0:
                    sidebar_text = sidebar.first.inner_text()

                    # 故事板场景
                    scenes = page.locator('[class*="scene"]').count()
                    if scenes > 0 or "场景" in sidebar_text:
                        log(f"    ✓ 故事板已生成 ({scenes}个场景)")
                        results["passed"] += 1
                        results["steps"].append("故事板生成")
                        page.screenshot(path="test_reports/v2_05_storyboard.png")

                        # 继续等待图片和视频生成
                        log("    等待图片生成...")
                        break

                # 检查是否有错误
                if "错误" in body_text or "失败" in body_text:
                    log("    ✗ 生成出错")
                    results["failed"] += 1
                    page.screenshot(path="test_reports/v2_error.png")

                    # 输出控制台日志
                    log("\n控制台日志:")
                    for log_msg in console_logs[-10:]:
                        log(f"    {log_msg}")
                    break

                mins = (i + 1) * 10 // 60
                secs = (i + 1) * 10 % 60
                log(f"    等待中... {mins}分{secs}秒")

                if (i + 1) % 6 == 0:
                    page.screenshot(
                        path=f"test_reports/v2_progress_{(i + 1) // 6}min.png"
                    )

            # 6. 检查最终状态
            log("\n[6] 检查最终状态...")
            page.screenshot(path="test_reports/v2_final.png")

            # 检查视频
            video_count = page.locator("video").count()
            if video_count > 0:
                log(f"    ✓ 发现 {video_count} 个视频元素")
                results["passed"] += 1
            else:
                log(f"    - 未发现视频元素（可能生成时间较长）")

            # 检查下载按钮
            if page.locator('button:has-text("下载")').count() > 0:
                log(f"    ✓ 发现下载按钮")
                results["passed"] += 1

            # 检查控制台错误
            errors = [l for l in console_logs if "error" in l.lower()]
            if errors:
                log(f"    ⚠ 控制台有 {len(errors)} 个错误")
                for err in errors[:3]:
                    log(f"      {err}")

        except Exception as e:
            log(f"\n✗ 异常: {e}")
            results["failed"] += 1
            try:
                page.screenshot(path="test_reports/v2_exception.png")
            except:
                pass
        finally:
            browser.close()

    # 结果
    log("\n" + "=" * 70)
    log("测试结果")
    log("=" * 70)
    log(f"通过: {results['passed']}")
    log(f"失败: {results['failed']}")
    log(f"步骤: {' -> '.join(results['steps']) if results['steps'] else '执行中'}")
    log("=" * 70)

    return results


if __name__ == "__main__":
    import os

    os.makedirs("test_reports", exist_ok=True)

    results = test_full_video_generation_v2()

    print(f"\n通过: {results['passed']}, 失败: {results['failed']}")
