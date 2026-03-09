#!/usr/bin/env python3
"""
数字人视频生成测试脚本
功能：通过Web界面操作，生成长达10分钟的数字人视频

使用方法：
1. 确保项目已在 localhost:3000 运行
2. 确保代理服务器已在 localhost:8123 运行
3. 运行此脚本：python test_digital_human_10min.py

文件说明：
- 照片：C:\Users\liula\Downloads\ComfyUI_00011_pcxyj_1764731727.png
- 音频：C:\Users\liula\Downloads\1766630274666746137-348477315510412.mp3
"""

from playwright.sync_api import sync_playwright
import time
import os
import sys
import http.server
import socketserver
import threading
import subprocess

# 文件路径
PHOTO_PATH = r"C:\Users\liula\Downloads\ComfyUI_00011_pcxyj_1764731727.png"
AUDIO_PATH = r"C:\Users\liula\Downloads\1766630274666746137-348477315510412.mp3"

# 启动文件服务器，使本地文件可以通过URL访问
class FileServerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # 设置根目录为Downloads文件夹
        super().__init__(*args, directory=r"C:\Users\liula\Downloads", **kwargs)
    
    def log_message(self, format, *args):
        # 静默日志
        pass

def start_file_server(port=8765):
    """启动本地文件服务器"""
    try:
        with socketserver.TCPServer(("", port), FileServerHandler) as httpd:
            print(f"文件服务器已启动: http://localhost:{port}")
            httpd.serve_forever()
    except Exception as e:
        print(f"文件服务器启动失败: {e}")

def get_file_urls(port=8765):
    """获取文件的URL"""
    return {
        'photo': f"http://localhost:{port}/ComfyUI_00011_pcxyj_1764731727.png",
        'audio': f"http://localhost:{port}/1766630274666746137-348477315510412.mp3"
    }

def wait_for_server(url, timeout=30):
    """等待服务器启动"""
    import urllib.request
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except:
            time.sleep(1)
    return False

def main():
    print("="*60)
    print("数字人视频生成测试 - 10分钟时长")
    print("="*60)
    
    # 检查文件是否存在
    if not os.path.exists(PHOTO_PATH):
        print(f"❌ 照片文件不存在: {PHOTO_PATH}")
        return 1
    
    if not os.path.exists(AUDIO_PATH):
        print(f"❌ 音频文件不存在: {AUDIO_PATH}")
        return 1
    
    print(f"✓ 照片文件: {PHOTO_PATH}")
    print(f"✓ 音频文件: {AUDIO_PATH}")
    
    # 启动文件服务器
    print("\n启动文件服务器...")
    server_port = 8765
    server_thread = threading.Thread(
        target=start_file_server,
        args=(server_port,),
        daemon=True
    )
    server_thread.start()
    time.sleep(2)  # 等待服务器启动
    
    # 检查文件服务器
    file_urls = get_file_urls(server_port)
    print(f"✓ 照片URL: {file_urls['photo']}")
    print(f"✓ 音频URL: {file_urls['audio']}")
    
    # 开始Playwright测试
    print("\n" + "="*60)
    print("开始Web自动化测试")
    print("="*60)
    
    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})
        
        try:
            # 步骤1: 访问首页
            print("\n步骤1: 访问 http://localhost:3000")
            page.goto('http://localhost:3000')
            page.wait_for_load_state('networkidle')
            time.sleep(2)
            print("✓ 页面加载完成")
            
            # 截图记录
            page.screenshot(path='test_01_homepage.png')
            
            # 步骤2: 选择数字人口播模板
            print("\n步骤2: 选择数字人口播模板")
            digital_human_button = page.locator('button:has-text("数字人口播")')
            
            if digital_human_button.count() == 0:
                print("❌ 未找到数字人口播模板按钮")
                # 尝试滚动查找
                page.evaluate('window.scrollBy(0, 500)')
                time.sleep(1)
                digital_human_button = page.locator('button:has-text("数字人口播")')
            
            if digital_human_button.count() > 0:
                digital_human_button.first.scroll_into_view_if_needed()
                time.sleep(0.5)
                digital_human_button.first.click()
                print("✓ 已点击数字人口播模板")
            else:
                print("❌ 仍然找不到数字人口播模板")
                return 1
            
            time.sleep(2)
            page.wait_for_load_state('networkidle')
            page.screenshot(path='test_02_template_selected.png')
            
            # 步骤3: 填写表单
            print("\n步骤3: 填写数字人表单")
            
            # 3.1 填写主题
            print("  - 填写主题...")
            theme_input = page.locator('textarea[placeholder*="主题"]').first
            if theme_input.count() > 0:
                theme_input.fill("电商直播带货数字人演示 - 10分钟长视频测试")
                print("    ✓ 主题已填写")
            
            # 3.2 填写数字人形象图片URL
            print("  - 填写数字人形象图片URL...")
            # 找到图片URL输入框（在数字人形象图片部分）
            image_sections = page.locator('section').all()
            for section in image_sections:
                try:
                    text = section.inner_text()
                    if '数字人形象' in text or '素材上传' in text:
                        url_input = section.locator('input[type="text"]').first
                        if url_input.count() > 0:
                            url_input.fill(file_urls['photo'])
                            print(f"    ✓ 图片URL已填写: {file_urls['photo']}")
                            break
                except:
                    continue
            
            # 3.3 填写音频文件URL
            print("  - 填写音频文件URL...")
            audio_input = page.locator('input[placeholder*="音频"]').first
            if audio_input.count() > 0:
                audio_input.fill(file_urls['audio'])
                print(f"    ✓ 音频URL已填写: {file_urls['audio']}")
            
            # 3.4 确认声音模式为"直接使用音频" (voice_mode = 0)
            print("  - 确认声音模式...")
            direct_audio_button = page.locator('button:has-text("直接使用音频")')
            if direct_audio_button.count() > 0:
                # 检查是否已选中
                classes = direct_audio_button.first.get_attribute('class') or ''
                if 'bg-[#E11D48]' not in classes and 'bg-red-500' not in classes:
                    direct_audio_button.first.click()
                    time.sleep(0.5)
                print("    ✓ 声音模式已设置为直接使用音频")
            
            # 3.5 填写动作描述
            print("  - 填写动作描述...")
            motion_input = page.locator('input[placeholder*="动作"]').first
            if motion_input.count() > 0:
                motion_input.fill("模特正在做产品展示，进行电商直播带货，表情自然，手势专业")
                print("    ✓ 动作描述已填写")
            
            # 3.6 设置时长为600秒（10分钟）
            print("  - 设置视频时长为600秒（10分钟）...")
            duration_input = page.locator('input[type="number"]').first
            if duration_input.count() > 0:
                # 清除当前值并填入600
                duration_input.fill("600")
                print("    ✓ 时长已设置为600秒")
            
            # 截图记录表单状态
            page.screenshot(path='test_03_form_filled.png')
            print("\n✓ 表单填写完成")
            
            # 步骤4: 提交生成
            print("\n步骤4: 提交数字人视频生成")
            submit_button = page.locator('button:has-text("生成数字人视频")')
            if submit_button.count() > 0:
                submit_button.first.click()
                print("✓ 已点击生成按钮")
            else:
                # 尝试查找其他可能的按钮文本
                submit_button = page.locator('button:has-text("开始生成")')
                if submit_button.count() > 0:
                    submit_button.first.click()
                    print("✓ 已点击生成按钮（开始生成）")
                else:
                    print("❌ 未找到生成按钮")
                    return 1
            
            # 步骤5: 等待生成完成
            print("\n步骤5: 等待视频生成完成...")
            print("  注意：10分钟视频生成可能需要较长时间，请耐心等待")
            print("  正在轮询任务状态...")
            
            # 等待一段时间让任务开始
            time.sleep(5)
            
            # 截图记录提交后的状态
            page.screenshot(path='test_04_submitted.png')
            
            # 检查是否有进度或状态显示
            max_wait = 1800  # 最多等待30分钟
            check_interval = 10  # 每10秒检查一次
            elapsed = 0
            
            while elapsed < max_wait:
                time.sleep(check_interval)
                elapsed += check_interval
                
                # 刷新页面获取最新状态
                page.reload()
                time.sleep(2)
                
                # 检查页面上的状态信息
                page_text = page.locator('body').inner_text()
                
                # 截图记录
                if elapsed % 60 == 0:  # 每分钟截图一次
                    page.screenshot(path=f'test_05_progress_{elapsed//60}min.png')
                    print(f"  已等待 {elapsed//60} 分钟...")
                
                # 检查是否完成或失败
                if '成功' in page_text or '完成' in page_text:
                    print(f"\n✓ 视频生成成功！")
                    page.screenshot(path='test_06_completed.png')
                    break
                elif '失败' in page_text or '错误' in page_text:
                    print(f"\n❌ 视频生成失败")
                    page.screenshot(path='test_06_failed.png')
                    break
                elif elapsed >= max_wait:
                    print(f"\n⏰ 等待超时（{max_wait//60}分钟）")
                    page.screenshot(path='test_06_timeout.png')
                    break
            
            # 最终截图
            page.screenshot(path='test_final_state.png', full_page=True)
            
            print("\n" + "="*60)
            print("测试完成!")
            print("="*60)
            print("截图已保存到当前目录")
            
            # 保持浏览器打开一段时间以便查看结果
            print("\n浏览器将在10秒后关闭...")
            time.sleep(10)
            
        except Exception as e:
            print(f"\n❌ 测试过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            page.screenshot(path='test_error.png')
            return 1
        finally:
            browser.close()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
