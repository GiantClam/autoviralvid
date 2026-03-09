#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

"""
数字人视频生成测试脚本 - 增强版
功能：通过Web界面操作，生成长达10分钟的数字人视频

使用方法：
1. 确保项目已在 localhost:3000 运行
2. 确保代理服务器已在 localhost:8123 运行
3. 运行此脚本：python test_digital_human_10min_v2.py

文件说明：
- 照片：C:\\Users\\liula\\Downloads\\ComfyUI_00011_pcxyj_1764731727.png
- 音频：C:\\Users\\liula\\Downloads\\1766630274666746137-348477315510412.mp3
"""

from playwright.sync_api import sync_playwright, expect
import time
import os
import sys
import json
import http.server
import socketserver
import threading
from datetime import datetime

# 文件路径
PHOTO_PATH = r"C:\Users\liula\Downloads\ComfyUI_00011_pcxyj_1764731727.png"
AUDIO_PATH = r"C:\Users\liula\Downloads\1766630274666746137-348477315510412.mp3"

# 全局变量
file_server_port = 8765
base_url = "http://localhost:3000"
api_base = "http://localhost:8123/api/v1"


class FileServerHandler(http.server.SimpleHTTPRequestHandler):
    """处理文件请求的HTTP服务器"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=r"C:\Users\liula\Downloads", **kwargs)

    def log_message(self, format, *args):
        pass


def start_file_server(port):
    """在后台线程中启动文件服务器"""
    try:
        with socketserver.TCPServer(("", port), FileServerHandler) as httpd:
            print(f"  ✓ 文件服务器运行在 http://localhost:{port}")
            httpd.serve_forever()
    except Exception as e:
        print(f"  ❌ 文件服务器错误: {e}")


def get_file_urls(port):
    """获取本地文件的HTTP URL"""
    return {
        "photo": f"http://localhost:{port}/ComfyUI_00011_pcxyj_1764731727.png",
        "audio": f"http://localhost:{port}/1766630274666746137-348477315510412.mp3",
    }


def log_step(step_num, message):
    """打印步骤日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{timestamp}] 步骤{step_num}: {message}")


def log_substep(message):
    """打印子步骤日志"""
    print(f"  → {message}")


def check_prerequisites():
    """检查前提条件"""
    log_step(0, "检查前提条件")

    all_ok = True

    # 检查照片文件
    if os.path.exists(PHOTO_PATH):
        size_mb = os.path.getsize(PHOTO_PATH) / 1024 / 1024
        log_substep(f"✓ 照片文件存在: {size_mb:.1f}MB")
    else:
        log_substep(f"❌ 照片文件不存在: {PHOTO_PATH}")
        all_ok = False

    # 检查音频文件
    if os.path.exists(AUDIO_PATH):
        size_mb = os.path.getsize(AUDIO_PATH) / 1024 / 1024
        log_substep(f"✓ 音频文件存在: {size_mb:.1f}MB")
    else:
        log_substep(f"❌ 音频文件不存在: {AUDIO_PATH}")
        all_ok = False

    return all_ok


def select_digital_human_template(page):
    """选择数字人口播模板"""
    log_step(2, "选择数字人口播模板")

    # 尝试查找并点击数字人口播按钮
    selectors = [
        'button:has-text("数字人口播")',
        "text=数字人口播",
        '[data-template="digital-human"]',
        'button:has-text("数字人")',
    ]

    for selector in selectors:
        try:
            element = page.locator(selector).first
            if element.is_visible(timeout=2000):
                element.scroll_into_view_if_needed()
                time.sleep(0.5)
                element.click()
                log_substep("✓ 已点击数字人口播模板")
                time.sleep(2)
                return True
        except:
            continue

    # 如果没找到，尝试滚动页面
    log_substep("正在滚动查找模板...")
    for _ in range(3):
        page.evaluate("window.scrollBy(0, 400)")
        time.sleep(1)

        try:
            element = page.locator('button:has-text("数字人口播")').first
            if element.is_visible(timeout=2000):
                element.click()
                log_substep("✓ 已找到并点击数字人口播模板")
                time.sleep(2)
                return True
        except:
            continue

    return False


def fill_project_form(page, file_urls):
    """填写项目表单"""
    log_step(3, "填写项目表单")

    # 3.1 填写主题
    try:
        # 查找主题输入框（通常是textarea）
        theme_selectors = [
            'textarea[placeholder*="主题"]',
            'textarea[placeholder*="视频"]',
            "textarea",
        ]

        for selector in theme_selectors:
            theme_input = page.locator(selector).first
            if theme_input.count() > 0 and theme_input.is_visible(timeout=1000):
                theme_input.fill("数字人直播带货演示 - 10分钟长视频测试")
                log_substep("✓ 主题已填写")
                break
    except Exception as e:
        log_substep(f"⚠ 主题填写可能失败: {e}")

    # 3.2 填写数字人形象图片URL
    try:
        # 找到包含"数字人形象"或"素材上传"的section
        sections = page.locator("section").all()
        for section in sections:
            try:
                text = section.inner_text()
                if any(
                    keyword in text for keyword in ["数字人形象", "素材上传", "图片"]
                ):
                    url_input = section.locator('input[type="text"]').first
                    if url_input.count() > 0:
                        url_input.fill(file_urls["photo"])
                        log_substep(f"✓ 数字人形象图片URL已填写")
                        break
            except:
                continue
        else:
            # 如果没找到，尝试直接查找所有文本输入框
            inputs = page.locator('input[type="text"]').all()
            for i, inp in enumerate(inputs):
                try:
                    placeholder = inp.get_attribute("placeholder") or ""
                    if any(
                        kw in placeholder.lower()
                        for kw in ["url", "链接", "图片", "image"]
                    ):
                        inp.fill(file_urls["photo"])
                        log_substep(f"✓ 图片URL已填写到第{i + 1}个输入框")
                        break
                except:
                    continue
    except Exception as e:
        log_substep(f"⚠ 图片URL填写可能失败: {e}")

    # 3.3 填写音频文件URL
    try:
        # 查找音频输入框
        audio_selectors = [
            'input[placeholder*="音频"]',
            'input[placeholder*="audio"]',
        ]

        for selector in audio_selectors:
            audio_input = page.locator(selector).first
            if audio_input.count() > 0 and audio_input.is_visible(timeout=1000):
                audio_input.fill(file_urls["audio"])
                log_substep(f"✓ 音频文件URL已填写")
                break
        else:
            # 如果没找到特定占位符，尝试查找所有可见的文本输入框
            inputs = page.locator('input[type="text"]').all()
            for inp in inputs:
                try:
                    if inp.is_visible(timeout=1000):
                        val = inp.input_value()
                        if not val:  # 如果为空，可能是音频输入框
                            inp.fill(file_urls["audio"])
                            log_substep(f"✓ 音频URL已填写")
                            break
                except:
                    continue
    except Exception as e:
        log_substep(f"⚠ 音频URL填写可能失败: {e}")

    # 3.4 确认声音模式为"直接使用音频"
    try:
        direct_button = page.locator('button:has-text("直接使用音频")')
        if direct_button.count() > 0:
            # 检查是否已经选中
            classes = direct_button.first.get_attribute("class") or ""
            if "bg-[#E11D48]" not in classes and "border-[#E11D48]" not in classes:
                direct_button.first.click()
                time.sleep(0.5)
            log_substep("✓ 声音模式已设置为直接使用音频")
    except Exception as e:
        log_substep(f"⚠ 声音模式设置可能失败: {e}")

    # 3.5 填写动作描述
    try:
        motion_selectors = [
            'input[placeholder*="动作"]',
            'input[placeholder*="motion"]',
        ]

        for selector in motion_selectors:
            motion_input = page.locator(selector).first
            if motion_input.count() > 0:
                motion_input.fill(
                    "专业主播进行产品介绍，手势自然，表情丰富，眼神与观众交流"
                )
                log_substep("✓ 动作描述已填写")
                break
    except Exception as e:
        log_substep(f"⚠ 动作描述填写可能失败: {e}")

    # 3.6 设置时长为600秒（10分钟）
    try:
        duration_input = page.locator('input[type="number"]').first
        if duration_input.count() > 0:
            duration_input.fill("600")
            log_substep("✓ 视频时长已设置为600秒（10分钟）")
    except Exception as e:
        log_substep(f"⚠ 时长设置可能失败: {e}")

    # 截图记录
    page.screenshot(path="test_form_filled.png")
    log_substep("✓ 表单截图已保存: test_form_filled.png")


def submit_generation(page):
    """提交视频生成"""
    log_step(4, "提交视频生成")

    submit_button = page.locator('button:has-text("生成数字人视频")')
    if submit_button.count() > 0:
        submit_button.first.click()
        log_substep("✓ 已点击生成按钮")
        return True
    else:
        # 尝试其他可能的按钮文本
        alt_buttons = [
            'button:has-text("开始生成")',
            'button[type="submit"]',
        ]
        for selector in alt_buttons:
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible(timeout=2000):
                btn.click()
                log_substep(f"✓ 已点击生成按钮")
                return True

    return False


def wait_for_completion(page, max_wait_seconds=1800):
    """等待视频生成完成"""
    log_step(5, f"等待视频生成完成（最多等待{max_wait_seconds // 60}分钟）")
    print(f"\n  提示：10分钟视频生成可能需要15-30分钟，请耐心等待...")
    print(f"  期间会每分钟自动截图记录进度\n")

    elapsed = 0
    check_interval = 10  # 每10秒检查一次
    screenshot_interval = 60  # 每分钟截图一次
    last_screenshot = 0

    while elapsed < max_wait_seconds:
        time.sleep(check_interval)
        elapsed += check_interval

        # 每分钟截图
        if elapsed - last_screenshot >= screenshot_interval:
            last_screenshot = elapsed
            minutes = elapsed // 60
            page.screenshot(path=f"test_progress_{minutes:02d}min.png")
            print(f"    [{minutes:02d}分钟] 进度截图已保存")

        # 检查页面状态
        try:
            page_text = page.locator("body").inner_text()

            # 检查成功/失败标志
            if any(word in page_text for word in ["成功", "完成", "下载", "video_url"]):
                print(f"\n  ✓ 视频生成成功！")
                page.screenshot(path="test_completed.png")
                return True
            elif any(word in page_text for word in ["失败", "错误", "error", "failed"]):
                print(f"\n  ❌ 视频生成失败")
                page.screenshot(path="test_failed.png")
                return False

        except Exception as e:
            print(f"    检查状态时出错: {e}")

    print(f"\n  ⏰ 等待超时（{max_wait_seconds // 60}分钟）")
    page.screenshot(path="test_timeout.png")
    return False


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("  数字人视频生成测试 - 10分钟长视频")
    print("=" * 70)
    print(f"\n  照片: {PHOTO_PATH}")
    print(f"  音频: {AUDIO_PATH}")
    print(f"  目标时长: 600秒 (10分钟)")
    print("=" * 70)

    # 检查前提条件
    if not check_prerequisites():
        print("\n❌ 前提条件检查失败，请检查文件路径")
        return 1

    # 启动文件服务器
    log_step(1, "启动本地文件服务器")
    server_thread = threading.Thread(
        target=start_file_server, args=(file_server_port,), daemon=True
    )
    server_thread.start()
    time.sleep(3)  # 等待服务器启动

    file_urls = get_file_urls(file_server_port)
    log_substep(f"照片URL: {file_urls['photo']}")
    log_substep(f"音频URL: {file_urls['audio']}")

    # 开始Playwright测试
    print("\n" + "=" * 70)
    print("  开始Web自动化测试")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})

        try:
            # 访问首页
            log_step(1, "访问项目首页")
            page.goto(base_url)
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            page.screenshot(path="test_01_homepage.png")
            log_substep(f"✓ 已加载 {base_url}")

            # 选择模板
            if not select_digital_human_template(page):
                print("\n❌ 无法找到数字人口播模板")
                return 1

            page.wait_for_load_state("networkidle")
            page.screenshot(path="test_02_template_selected.png")

            # 填写表单
            fill_project_form(page, file_urls)

            # 提交生成
            if not submit_generation(page):
                print("\n❌ 无法找到生成按钮")
                return 1

            time.sleep(3)
            page.screenshot(path="test_03_submitted.png")

            # 等待完成
            success = wait_for_completion(page, max_wait_seconds=1800)

            # 最终截图
            page.screenshot(path="test_final_result.png", full_page=True)

            print("\n" + "=" * 70)
            if success:
                print("  ✓ 测试成功完成!")
            else:
                print("  ⚠ 测试完成，但视频生成未成功")
            print("=" * 70)
            print("\n  截图文件:")
            print("    - test_01_homepage.png")
            print("    - test_02_template_selected.png")
            print("    - test_form_filled.png")
            print("    - test_03_submitted.png")
            print("    - test_progress_*.png")
            print("    - test_completed.png / test_failed.png")
            print("    - test_final_result.png")

            # 保持浏览器打开
            print("\n  浏览器将在5秒后关闭...")
            time.sleep(5)

        except Exception as e:
            print(f"\n❌ 测试过程中发生错误: {e}")
            import traceback

            traceback.print_exc()
            try:
                page.screenshot(path="test_error.png")
            except:
                pass
            return 1
        finally:
            browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
