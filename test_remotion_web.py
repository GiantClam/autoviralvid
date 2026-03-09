"""
Web端测试Remotion功能 - 生成1分钟视频
"""

from playwright.sync_api import sync_playwright
import time
import json


def test_remotion_1min_video():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("1. 打开网页...")
        page.goto("http://localhost:3001")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="test_outputs/01_home.png", full_page=True)

        print("2. 等待页面加载...")
        time.sleep(2)

        # 查找项目表单
        print("3. 检查页面元素...")

        # 查看页面结构
        buttons = page.locator("button").all()
        print(f"找到 {len(buttons)} 个按钮")

        # 截图查看界面
        page.screenshot(path="test_outputs/02_explore.png", full_page=True)

        # 查找输入框
        inputs = page.locator("input").all()
        print(f"找到 {len(inputs)} 个输入框")

        # 查找文本框
        textareas = page.locator("textarea").all()
        print(f"找到 {len(textareas)} 个文本框")

        # 直接调用API生成视频
        print("\n4. 通过API生成1分钟视频...")

        # 先创建项目，然后直接提交渲染任务
        render_response = page.request.post(
            "http://localhost:3001/api/render/jobs",
            data=json.dumps(
                {
                    "project": {
                        "name": "Web Test 1min Video",
                        "width": 1920,
                        "height": 1080,
                        "duration": 60,
                        "fps": 30,
                        "backgroundColor": "#4ECDC4",
                        "tracks": [
                            {
                                "id": 2,
                                "type": "overlay",
                                "name": "Text",
                                "items": [
                                    {
                                        "id": "title1",
                                        "type": "text",
                                        "content": "Chapter 1: Introduction",
                                        "startTime": 0,
                                        "duration": 15,
                                        "trackId": 2,
                                        "name": "Title 1",
                                        "style": {"fontSize": 72, "color": "#ffffff"},
                                    },
                                    {
                                        "id": "title2",
                                        "type": "text",
                                        "content": "Chapter 2: Main Content",
                                        "startTime": 15,
                                        "duration": 15,
                                        "trackId": 2,
                                        "name": "Title 2",
                                        "style": {"fontSize": 72, "color": "#ffffff"},
                                    },
                                    {
                                        "id": "title3",
                                        "type": "text",
                                        "content": "Chapter 3: Deep Dive",
                                        "startTime": 30,
                                        "duration": 15,
                                        "trackId": 2,
                                        "name": "Title 3",
                                        "style": {"fontSize": 72, "color": "#ffffff"},
                                    },
                                    {
                                        "id": "title4",
                                        "type": "text",
                                        "content": "Chapter 4: Conclusion",
                                        "startTime": 45,
                                        "duration": 15,
                                        "trackId": 2,
                                        "name": "Title 4",
                                        "style": {"fontSize": 72, "color": "#ffffff"},
                                    },
                                ],
                            }
                        ],
                        "runId": f"web-test-{int(time.time())}",
                    }
                }
            ),
            headers={"Content-Type": "application/json"},
        )

        result = render_response.json()
        print(f"渲染响应: {json.dumps(result, indent=2)}")

        job_id = result.get("job_id")
        print(f"\n5. 任务已提交, Job ID: {job_id}")

        # 等待渲染完成
        print("6. 等待渲染完成...")
        start_time = time.time()

        while True:
            status_response = page.request.get(
                f"http://localhost:8123/render/jobs/{job_id}"
            )
            status = status_response.json()
            elapsed = time.time() - start_time

            print(f"[{elapsed:.1f}s] 状态: {status.get('status')}")

            if status.get("status") == "completed":
                print(f"\n✅ 渲染完成!")
                print(f"输出文件: {status.get('output_path')}")
                print(f"输出URL: {status.get('output_url')}")
                break
            elif status.get("status") == "failed":
                print(f"\n❌ 渲染失败: {status.get('error')}")
                break

            time.sleep(2)

        total_time = time.time() - start_time
        print(f"\n总耗时: {total_time:.2f}秒")

        # 性能指标
        video_duration = 60
        real_time_factor = video_duration / total_time
        print(f"实时倍率: {real_time_factor:.2f}x")

        page.screenshot(path="test_outputs/03_complete.png", full_page=True)

        browser.close()
        print("\n测试完成!")


if __name__ == "__main__":
    import os

    os.makedirs("test_outputs", exist_ok=True)
    test_remotion_1min_video()
