#!/usr/bin/env python3
"""
数字人视频生成测试脚本 - API直接调用版
功能：通过API直接提交10分钟数字人视频生成任务

使用方法：
1. 确保代理服务器已在 localhost:8123 运行
2. 运行此脚本：python test_digital_human_api.py

文件说明：
- 照片：C:\\Users\\liula\\Downloads\\ComfyUI_00011_pcxyj_1764731727.png
- 音频：C:\\Users\\liula\\Downloads\\1766630274666746137-348477315510412.mp3
"""

import asyncio
import json
import sys
import io
import time
import os
import httpx
from datetime import datetime
import http.server
import socketserver
import threading

# 强制UTF-8输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 配置
BASE_API = "http://localhost:8123/api/v1"
FILE_SERVER_PORT = 8765
PHOTO_FILENAME = "ComfyUI_00011_pcxyj_1764731727.png"
AUDIO_FILENAME = "1766630274666746137-348477315510412.mp3"

# 文件路径
PHOTO_PATH = rf"C:\Users\liula\Downloads\{PHOTO_FILENAME}"
AUDIO_PATH = rf"C:\Users\liula\Downloads\{AUDIO_FILENAME}"


class FileServerHandler(http.server.SimpleHTTPRequestHandler):
    """处理文件请求的HTTP服务器"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=r"C:\Users\liula\Downloads", **kwargs)

    def log_message(self, format, *args):
        pass


def start_file_server(port):
    """启动文件服务器"""
    try:
        with socketserver.TCPServer(("", port), FileServerHandler) as httpd:
            print(f"  [服务器] 文件服务已启动: http://localhost:{port}")
            httpd.serve_forever()
    except Exception as e:
        print(f"  [错误] 文件服务器启动失败: {e}")


def get_file_urls(port):
    """获取文件URL"""
    return {
        "photo": f"http://localhost:{port}/{PHOTO_FILENAME}",
        "audio": f"http://localhost:{port}/{AUDIO_FILENAME}",
    }


def log(msg, level="INFO"):
    """打印日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "ℹ", "SUCCESS": "✓", "ERROR": "✗", "WARN": "⚠"}.get(level, "ℹ")
    print(f"[{timestamp}] {prefix} {msg}")


def check_files():
    """检查文件是否存在"""
    log("检查文件...")

    if os.path.exists(PHOTO_PATH):
        size = os.path.getsize(PHOTO_PATH) / 1024 / 1024
        log(f"照片文件: {size:.1f}MB ✓", "SUCCESS")
    else:
        log(f"照片文件不存在: {PHOTO_PATH}", "ERROR")
        return False

    if os.path.exists(AUDIO_PATH):
        size = os.path.getsize(AUDIO_PATH) / 1024 / 1024
        log(f"音频文件: {size:.1f}MB ✓", "SUCCESS")
    else:
        log(f"音频文件不存在: {AUDIO_PATH}", "ERROR")
        return False

    return True


async def create_project(client, file_urls):
    """创建项目"""
    log("创建数字人项目...")

    create_body = {
        "template_id": "digital-human",
        "theme": "数字人直播带货演示 - 10分钟长视频测试",
        "product_image_url": file_urls["photo"],
        "style": "现代简约",
        "duration": 600,  # 10分钟 = 600秒
        "orientation": "竖屏",
        "aspect_ratio": "9:16",
        # 数字人特定参数
        "audio_url": file_urls["audio"],
        "voice_mode": 0,  # 0=直接使用音频
        "motion_prompt": "专业主播进行产品介绍，手势自然，表情丰富，与观众眼神交流",
    }

    try:
        resp = await client.post(f"{BASE_API}/projects", json=create_body)
        log(f"创建项目响应: HTTP {resp.status_code}")

        if resp.status_code != 200:
            log(f"创建项目失败: {resp.text[:500]}", "ERROR")
            return None

        project = resp.json()

        if "error" in project:
            log(f"创建项目错误: {project['error']}", "ERROR")
            return None

        run_id = project.get("run_id")
        if not run_id:
            log("响应中没有run_id", "ERROR")
            return None

        log(f"项目创建成功! run_id: {run_id}", "SUCCESS")
        return run_id

    except Exception as e:
        log(f"创建项目异常: {e}", "ERROR")
        return None


async def submit_digital_human(client, run_id):
    """提交数字人视频生成"""
    log(f"提交数字人视频生成任务...")

    try:
        resp = await client.post(f"{BASE_API}/projects/{run_id}/digital-human")
        log(f"提交任务响应: HTTP {resp.status_code}")

        if resp.status_code != 200:
            log(f"提交任务失败: {resp.text[:500]}", "ERROR")
            return False

        result = resp.json()
        log(f"任务提交成功: {json.dumps(result, ensure_ascii=False)[:200]}", "SUCCESS")
        return True

    except Exception as e:
        log(f"提交任务异常: {e}", "ERROR")
        return False


async def poll_status(client, run_id, max_polls=360, interval=10):
    """轮询任务状态"""
    log(f"开始轮询任务状态（最多{max_polls * interval // 60}分钟）...")
    print(f"\n  提示：10分钟视频生成预计需要15-30分钟\n")

    for i in range(max_polls):
        try:
            resp = await client.get(f"{BASE_API}/projects/{run_id}/status")
            status = resp.json()

            # 提取状态信息
            total = status.get("total", 0)
            succeeded = status.get("succeeded", 0)
            failed = status.get("failed", 0)
            pending = status.get("pending", 0)
            all_done = status.get("all_done", False)

            tasks = status.get("tasks", [])
            task_statuses = [t.get("status", "?") for t in tasks]

            # 每6次轮询（约1分钟）打印一次状态
            if (i + 1) % 6 == 0 or all_done:
                minutes = (i + 1) * interval // 60
                log(
                    f"轮询 {i + 1} ({minutes}分钟): "
                    f"总计={total}, 成功={succeeded}, 待处理={pending}, 失败={failed} | "
                    f"状态: {task_statuses}"
                )

            # 检查是否全部完成
            if all_done:
                print("\n" + "=" * 70)
                log("所有任务已完成!", "SUCCESS")
                print("=" * 70)

                for t in tasks:
                    if t.get("video_url"):
                        print(f"\n  ✓ 视频URL: {t['video_url']}")
                return True

            # 检查是否失败
            if failed > 0 and pending == 0:
                print("\n" + "=" * 70)
                log("任务失败!", "ERROR")
                print("=" * 70)

                for t in tasks:
                    if t.get("error"):
                        print(f"  ✗ 错误: {t['error']}")
                return False

            await asyncio.sleep(interval)

        except Exception as e:
            log(f"轮询异常: {e}", "ERROR")
            await asyncio.sleep(interval)

    print("\n" + "=" * 70)
    log(f"轮询超时（已达到最大轮询次数）", "WARN")
    print("=" * 70)
    return False


async def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("  数字人视频生成测试 - API直接调用版")
    print("=" * 70)
    print(f"\n  照片: {PHOTO_PATH}")
    print(f"  音频: {AUDIO_PATH}")
    print(f"  目标时长: 600秒 (10分钟)")
    print(f"  API地址: {BASE_API}")
    print("=" * 70 + "\n")

    # 检查文件
    if not check_files():
        return 1

    # 启动文件服务器
    log("启动文件服务器...")
    server_thread = threading.Thread(
        target=start_file_server, args=(FILE_SERVER_PORT,), daemon=True
    )
    server_thread.start()
    time.sleep(3)

    file_urls = get_file_urls(FILE_SERVER_PORT)
    log(f"照片URL: {file_urls['photo']}")
    log(f"音频URL: {file_urls['audio']}")

    # 执行测试流程
    async with httpx.AsyncClient(timeout=60) as client:
        # 步骤1: 创建项目
        run_id = await create_project(client, file_urls)
        if not run_id:
            return 1

        print()

        # 步骤2: 提交数字人任务
        if not await submit_digital_human(client, run_id):
            return 1

        print()

        # 步骤3: 轮询状态
        success = await poll_status(client, run_id)

        print()
        print("=" * 70)
        if success:
            print("  ✓ 测试成功完成!")
        else:
            print("  ⚠ 测试完成，但视频生成未成功")
        print("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n用户中断测试")
        sys.exit(130)
    except Exception as e:
        print(f"\n未处理的异常: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
