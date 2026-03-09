"""
End-to-end test for the Digital Human workflow via REST API.

Steps:
  1. POST /api/v1/projects         — Create a digital-human project
  2. POST /api/v1/projects/{id}/digital-human — Submit DH video generation
  3. GET  /api/v1/projects/{id}/status        — Poll task status
"""

import asyncio
import json
import sys
import io
import time
import httpx

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8123/api/v1"

# ── Test data ──
# Use a public sample image as the digital human avatar
PERSON_IMAGE = "https://cdn.pixabay.com/photo/2016/11/29/13/14/attractive-1869761_1280.jpg"
# Use a public sample audio (short speech clip)
AUDIO_URL = "https://cdn.pixabay.com/audio/2024/11/08/audio_93a1e8eb4e.mp3"


async def main():
    async with httpx.AsyncClient(timeout=60) as client:
        # ── Step 1: Create Project ──
        print("=" * 60)
        print("Step 1: Creating digital-human project...")
        print("=" * 60)
        
        create_body = {
            "template_id": "digital-human",
            "theme": "电商直播带货数字人",
            "product_image_url": PERSON_IMAGE,
            "style": "现代简约",
            "duration": 10,
            "orientation": "竖屏",
            "aspect_ratio": "9:16",
            # Digital human params
            "audio_url": AUDIO_URL,
            "voice_mode": 0,  # 直接使用音频
            "motion_prompt": "模特正在做产品展示，进行电商直播带货",
        }
        
        resp = await client.post(f"{BASE}/projects", json=create_body)
        print(f"  Status: {resp.status_code}")
        project = resp.json()
        print(f"  Response: {json.dumps(project, indent=2, ensure_ascii=False)[:800]}")
        
        if resp.status_code != 200 or "error" in project:
            print("  [FAIL] Failed to create project!")
            return
        
        run_id = project.get("run_id")
        if not run_id:
            print("  [FAIL] No run_id in response!")
            return
        
        print(f"  [OK] Project created: run_id={run_id}")
        print()

        # ── Step 2: Submit Digital Human ──
        print("=" * 60)
        print("Step 2: Submitting digital human video generation...")
        print("=" * 60)
        
        resp = await client.post(f"{BASE}/projects/{run_id}/digital-human")
        print(f"  Status: {resp.status_code}")
        try:
            submit_result = resp.json()
            print(f"  Response: {json.dumps(submit_result, indent=2, ensure_ascii=False)[:800]}")
        except Exception:
            print(f"  Response text: {resp.text[:500]}")
            submit_result = {}
        
        if resp.status_code != 200:
            print("  [FAIL] Failed to submit digital human!")
            return
        
        print(f"  [OK] Digital human task submitted")
        print()

        # ── Step 3: Poll Status ──
        print("=" * 60)
        print("Step 3: Polling task status...")
        print("=" * 60)
        
        max_polls = 36  # 3 minutes max (36 * 5s)
        for i in range(max_polls):
            resp = await client.get(f"{BASE}/projects/{run_id}/status")
            status = resp.json()
            
            total = status.get("total", 0)
            succeeded = status.get("succeeded", 0)
            failed = status.get("failed", 0)
            pending = status.get("pending", 0)
            all_done = status.get("all_done", False)
            
            tasks = status.get("tasks", [])
            task_statuses = [t.get("status", "?") for t in tasks]
            
            print(f"  Poll {i+1}: total={total}, succeeded={succeeded}, "
                  f"pending={pending}, failed={failed}, "
                  f"task_statuses={task_statuses}")
            
            if all_done:
                print()
                print("  [OK] All tasks completed!")
                for t in tasks:
                    if t.get("video_url"):
                        print(f"     Video URL: {t['video_url']}")
                break
            
            if failed > 0 and pending == 0:
                print()
                print("  [FAIL] Tasks failed with no pending tasks!")
                for t in tasks:
                    if t.get("error"):
                        print(f"     Error: {t['error']}")
                break
            
            await asyncio.sleep(5)
        else:
            print("  ⏰ Timeout: polling stopped after max polls")
        
        print()
        print("=" * 60)
        print("Test complete!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
