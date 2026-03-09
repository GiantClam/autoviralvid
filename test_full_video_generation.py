#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoViralVid 完整视频生成测试
真正触发视频生成并等待完成
"""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import time
import asyncio
import httpx
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8123/api/v1"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def test_full_video_generation():
    """完整视频生成测试 - 通过API真正生成视频"""
    log("=" * 70)
    log("完整视频生成测试")
    log("=" * 70)

    results = {"passed": 0, "failed": 0}

    # 使用API直接创建项目并生成
    async def run_test():
        async with httpx.AsyncClient(timeout=120) as client:
            # Step 1: 创建项目
            log("\n[1] 创建项目...")
            try:
                resp = await client.post(
                    f"{API_URL}/projects",
                    json={
                        "template_id": "product-ad",
                        "theme": "测试完整流程 - 自动化测试",
                        "product_image_url": "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400",
                        "style": "现代简约",
                        "duration": 10,
                        "orientation": "竖屏",
                    },
                )

                if resp.status_code == 200:
                    project = resp.json()
                    run_id = project.get("run_id")
                    log(f"    ✓ 项目创建成功: {run_id}")
                    results["passed"] += 1
                else:
                    log(f"    ✗ 项目创建失败: {resp.status_code}")
                    results["failed"] += 1
                    return
            except Exception as e:
                log(f"    ✗ 创建项目异常: {e}")
                results["failed"] += 1
                return

            # Step 2: 触发故事板生成
            log("\n[2] 触发故事板生成...")
            try:
                resp = await client.post(f"{API_URL}/projects/{run_id}/storyboard")
                if resp.status_code == 200:
                    log(f"    ✓ 故事板生成已触发")
                    results["passed"] += 1
                else:
                    log(f"    ✗ 故事板生成失败: {resp.status_code}")
            except Exception as e:
                log(f"    ✗ 异常: {e}")

            # Step 3: 轮询等待故事板生成
            log("\n[3] 等待故事板生成...")
            for i in range(30):  # 最多等待5分钟
                await asyncio.sleep(10)
                try:
                    resp = await client.get(f"{API_URL}/projects/{run_id}")
                    if resp.status_code == 200:
                        project = resp.json()
                        phase = project.get("phase", "")
                        storyboard = project.get("storyboard", {})

                        if storyboard and len(storyboard.get("scenes", [])) > 0:
                            log(
                                f"    ✓ 故事板生成完成! 场景数: {len(storyboard['scenes'])}"
                            )
                            results["passed"] += 1
                            break
                        else:
                            log(f"    等待中... ({i + 1}/30) phase: {phase}")
                except Exception as e:
                    log(f"    查询异常: {e}")
            else:
                log(f"    ✗ 故事板生成超时")

            # Step 4: 触发图片生成
            log("\n[4] 触发图片生成...")
            try:
                resp = await client.post(f"{API_URL}/projects/{run_id}/images")
                if resp.status_code == 200:
                    log(f"    ✓ 图片生成已触发")
                    results["passed"] += 1
                else:
                    log(f"    ✗ 图片生成失败: {resp.status_code}")
            except Exception as e:
                log(f"    ✗ 异常: {e}")

            # Step 5: 轮询等待图片生成
            log("\n[5] 等待图片生成...")
            for i in range(30):
                await asyncio.sleep(10)
                try:
                    resp = await client.get(f"{API_URL}/projects/{run_id}/status")
                    if resp.status_code == 200:
                        status = resp.json()
                        tasks = status.get("tasks", [])
                        images_ready = any(
                            t.get("image_url") for t in tasks if t.get("image_url")
                        )

                        if images_ready:
                            log(f"    ✓ 图片生成完成!")
                            results["passed"] += 1
                            break
                        else:
                            log(f"    等待中... ({i + 1}/30)")
                except Exception as e:
                    log(f"    查询异常: {e}")
            else:
                log(f"    ✗ 图片生成超时")

            # Step 6: 触发视频生成
            log("\n[6] 触发视频生成...")
            try:
                resp = await client.post(f"{API_URL}/projects/{run_id}/videos")
                if resp.status_code == 200:
                    log(f"    ✓ 视频生成已触发")
                    results["passed"] += 1
                else:
                    log(f"    ✗ 视频生成失败: {resp.status_code}")
            except Exception as e:
                log(f"    ✗ 异常: {e}")

            # Step 7: 轮询等待视频生成
            log("\n[7] 等待视频生成（最多20分钟）...")
            for i in range(120):  # 最多等待20分钟
                await asyncio.sleep(10)
                try:
                    resp = await client.get(f"{API_URL}/projects/{run_id}/status")
                    if resp.status_code == 200:
                        status = resp.json()
                        total = status.get("tasks_total", 0)
                        succeeded = status.get("tasks_summary", {}).get("succeeded", 0)
                        failed = status.get("tasks_summary", {}).get("failed", 0)
                        all_done = status.get("all_succeeded", False)

                        if all_done:
                            log(f"    ✓ 视频生成完成! 成功: {succeeded}")
                            results["passed"] += 1
                            break
                        elif failed > 0:
                            log(f"    ✗ 视频生成失败: {failed}个任务失败")
                            results["failed"] += 1
                            break
                        else:
                            mins = (i + 1) * 10 // 60
                            log(
                                f"    进度: {succeeded}/{total} 完成, 等待中... ({mins}分钟)"
                            )
                except Exception as e:
                    log(f"    查询异常: {e}")
            else:
                log(f"    ✗ 视频生成超时")

            # Step 8: 检查最终视频
            log("\n[8] 检查最终视频...")
            try:
                resp = await client.get(f"{API_URL}/projects/{run_id}")
                if resp.status_code == 200:
                    project = resp.json()
                    video_url = project.get("video_url")
                    if video_url:
                        log(f"    ✓ 最终视频URL: {video_url[:50]}...")
                        results["passed"] += 1
                    else:
                        log(f"    - 最终视频URL: 暂无")
            except Exception as e:
                log(f"    查询异常: {e}")

    # 运行异步测试
    asyncio.run(run_test())

    # 输出结果
    log("\n" + "=" * 70)
    log("测试结果")
    log("=" * 70)
    log(f"通过: {results['passed']}")
    log(f"失败: {results['failed']}")
    log("=" * 70)

    return results["failed"] == 0


def test_web_ui_generation():
    """通过Web界面触发视频生成"""
    log("\n" + "=" * 70)
    log("Web界面视频生成测试")
    log("=" * 70)

    results = {"passed": 0, "failed": 0}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            # 1. 访问首页
            log("\n[1] 访问首页...")
            page.goto(BASE_URL)
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            log("    ✓ 首页加载")
            results["passed"] += 1

            # 2. 选择模板
            log("\n[2] 选择模板...")
            page.locator('button:has-text("爆款产品广告")').first.click()
            time.sleep(3)
            log("    ✓ 模板已选择")
            results["passed"] += 1

            # 3. 填写表单
            log("\n[3] 填写表单...")
            page.locator("textarea").first.fill("测试视频生成")
            page.locator('input[type="text"]').first.fill(
                "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
            )
            log("    ✓ 表单已填写")
            results["passed"] += 1
            page.screenshot(path="test_reports/full_test_form.png")

            # 4. 点击生成
            log("\n[4] 点击生成...")
            page.locator('button:has-text("开始生成")').first.click()
            log("    ✓ 已点击生成按钮")
            results["passed"] += 1

            # 5. 等待生成
            log("\n[5] 等待生成过程...")
            for i in range(60):  # 等待10分钟
                time.sleep(10)

                # 检查页面状态
                try:
                    body_text = page.locator("body").inner_text()

                    # 检查是否有进度显示
                    if "生成中" in body_text or "处理中" in body_text:
                        log(f"    生成中... ({i + 1}/60)")
                    elif "完成" in body_text or "成功" in body_text:
                        log(f"    ✓ 生成完成!")
                        results["passed"] += 1
                        break
                    elif "失败" in body_text or "错误" in body_text:
                        log(f"    ✗ 生成失败")
                        results["failed"] += 1
                        break
                    else:
                        log(f"    等待中... ({i + 1}/60)")
                except:
                    pass

                # 每分钟截图
                if (i + 1) % 6 == 0:
                    page.screenshot(path=f"test_reports/full_test_progress_{i + 1}.png")
            else:
                log(f"    ✗ 等待超时")

            page.screenshot(path="test_reports/full_test_result.png")

        except Exception as e:
            log(f"    ✗ 测试异常: {e}")
            results["failed"] += 1
        finally:
            browser.close()

    log("\n" + "=" * 70)
    log("Web测试结果")
    log("=" * 70)
    log(f"通过: {results['passed']}")
    log(f"失败: {results['failed']}")

    return results["failed"] == 0


if __name__ == "__main__":
    import os

    os.makedirs("test_reports", exist_ok=True)

    # 先测试API方式
    api_success = test_full_video_generation()

    # 再测试Web UI方式（可选，时间较长）
    # web_success = test_web_ui_generation()

    print("\n" + "=" * 70)
    print("完整测试结束")
    print("=" * 70)
