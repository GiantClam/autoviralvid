#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoViralVid 完整视频生成测试 - 通过Web界面
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


def test_web_ui_full_generation():
    """通过Web界面完整触发视频生成"""
    log("=" * 70)
    log("Web界面完整视频生成测试")
    log("=" * 70)

    results = {"passed": 0, "failed": 0, "steps": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            # Step 1: 访问首页
            log("\n[1] 访问首页...")
            page.goto(BASE_URL)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # 检查页面内容
            body_text = page.locator("body").inner_text()
            if len(body_text) > 100:
                log(f"    ✓ 首页加载成功 (内容长度: {len(body_text)})")
                results["passed"] += 1
                results["steps"].append("首页加载")
            else:
                log(f"    ✗ 首页加载失败")
                results["failed"] += 1
                return results

            page.screenshot(path="test_reports/full_01_home.png")

            # Step 2: 选择模板
            log("\n[2] 选择模板...")
            template_btn = page.locator('button:has-text("爆款产品广告")')
            if template_btn.count() > 0:
                template_btn.first.click()
                time.sleep(3)

                # 检查是否跳转到项目页面
                body_text = page.locator("body").inner_text()
                if "主题描述" in body_text or "素材" in body_text:
                    log(f"    ✓ 模板选择成功")
                    results["passed"] += 1
                    results["steps"].append("模板选择")
                else:
                    log(f"    ✗ 模板选择后页面异常")
                    results["failed"] += 1
                    return results
            else:
                log(f"    ✗ 找不到模板按钮")
                results["failed"] += 1
                return results

            page.screenshot(path="test_reports/full_02_template.png")

            # Step 3: 填写表单
            log("\n[3] 填写表单...")

            # 填写主题
            theme_input = page.locator("textarea").first
            if theme_input.is_visible():
                theme_input.fill("自动化视频生成测试 - 完整流程验证")
                log(f"    ✓ 主题已填写")

            # 填写图片URL
            inputs = page.locator('input[type="text"]').all()
            for i, inp in enumerate(inputs):
                if inp.is_visible():
                    inp.fill(
                        "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
                    )
                    log(f"    ✓ 图片URL已填写")
                    break

            # 设置时长
            duration_input = page.locator('input[type="number"]').first
            if duration_input.is_visible():
                duration_input.fill("10")
                log(f"    ✓ 时长已设置为10秒")

            results["passed"] += 1
            results["steps"].append("表单填写")
            page.screenshot(path="test_reports/full_03_form.png")

            # Step 4: 点击生成
            log("\n[4] 点击开始生成...")

            generate_btn = page.locator('button:has-text("开始生成")')
            if generate_btn.count() > 0 and generate_btn.first.is_visible():
                generate_btn.first.click()
                log(f"    ✓ 已点击生成按钮")
                results["passed"] += 1
                results["steps"].append("点击生成")
            else:
                log(f"    ✗ 找不到生成按钮")
                results["failed"] += 1
                return results

            page.screenshot(path="test_reports/full_04_clicked.png")

            # Step 5: 等待生成过程
            log("\n[5] 等待视频生成过程...")
            log("    提示: 这将需要几分钟时间，请耐心等待...")

            max_wait = 60  # 最多等待10分钟
            generation_started = False

            for i in range(max_wait):
                time.sleep(10)

                try:
                    body_text = page.locator("body").inner_text()

                    # 检查各种状态
                    if (
                        "生成中" in body_text
                        or "处理中" in body_text
                        or "generating" in body_text.lower()
                    ):
                        if not generation_started:
                            log(f"    ✓ 生成已启动!")
                            generation_started = True
                        mins = (i + 1) * 10 // 60
                        secs = (i + 1) * 10 % 60
                        log(f"    生成进行中... {mins}分{secs}秒")

                    # 检查完成
                    if "完成" in body_text or "成功" in body_text:
                        log(f"    ✓ 视频生成完成!")
                        results["passed"] += 1
                        results["steps"].append("生成完成")
                        page.screenshot(path="test_reports/full_05_completed.png")
                        break

                    # 检查失败
                    if "失败" in body_text or "错误" in body_text:
                        log(f"    ✗ 生成过程出现错误")
                        results["failed"] += 1
                        page.screenshot(path="test_reports/full_05_error.png")
                        break

                    # 检查视频URL
                    if "http" in body_text and (
                        ".mp4" in body_text or "video" in body_text.lower()
                    ):
                        log(f"    ✓ 发现视频URL!")
                        results["passed"] += 1
                        results["steps"].append("视频就绪")
                        page.screenshot(path="test_reports/full_05_video.png")
                        break

                except Exception as e:
                    log(f"    检查状态异常: {e}")

                # 每分钟截图
                if (i + 1) % 6 == 0:
                    page.screenshot(
                        path=f"test_reports/full_progress_{(i + 1) // 6}min.png"
                    )
                    mins = (i + 1) * 10 // 60
                    log(f"    [{mins}分钟] 进度截图已保存")

            else:
                log(f"    ✗ 等待超时 (10分钟)")
                results["failed"] += 1

            # Step 6: 最终检查
            log("\n[6] 最终状态检查...")
            page.screenshot(path="test_reports/full_06_final.png")

            # 检查视频播放器
            video_player = page.locator("video").count()
            if video_player > 0:
                log(f"    ✓ 发现视频播放器")
                results["passed"] += 1
            else:
                log(f"    - 未发现视频播放器")

            # 检查下载链接
            body_text = page.locator("body").inner_text()
            if "下载" in body_text or "download" in body_text.lower():
                log(f"    ✓ 发现下载链接")
                results["passed"] += 1

        except Exception as e:
            log(f"\n✗ 测试异常: {e}")
            import traceback

            traceback.print_exc()
            results["failed"] += 1
            try:
                page.screenshot(path="test_reports/full_error.png")
            except:
                pass
        finally:
            browser.close()

    # 输出结果
    log("\n" + "=" * 70)
    log("测试结果汇总")
    log("=" * 70)
    log(f"通过: {results['passed']}")
    log(f"失败: {results['failed']}")
    log(f"步骤: {' -> '.join(results['steps'])}")
    log("=" * 70)

    return results


if __name__ == "__main__":
    import os

    os.makedirs("test_reports", exist_ok=True)

    results = test_web_ui_full_generation()

    print("\n" + "=" * 70)
    print("完整测试结束")
    print("=" * 70)
    print(f"\n执行步骤: {' -> '.join(results['steps'])}")
    print(f"通过: {results['passed']}, 失败: {results['failed']}")
