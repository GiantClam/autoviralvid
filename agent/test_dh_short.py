#!/usr/bin/env python3
"""Test with short audio"""

import asyncio, httpx, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8123/api/v1"

# Short audio (<45s)
PHOTO_URL = "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
AUDIO_URL = "https://actions.google.com/sounds/v1/ambiences/coffee_shop.ogg"


def log(msg):
    print(msg, flush=True)


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        log("=== Create project ===")
        r = await c.post(
            f"{BASE}/projects",
            json={
                "template_id": "digital-human",
                "theme": "数字人短视频测试",
                "product_image_url": PHOTO_URL,
                "style": "现代简约",
                "duration": 30,
                "orientation": "竖屏",
                "audio_url": AUDIO_URL,
                "voice_mode": 0,
                "motion_prompt": "模特正在做产品展示",
            },
        )
        run_id = r.json().get("run_id")
        log(f"  run_id={run_id}")

        log("=== Submit ===")
        r = await c.post(f"{BASE}/projects/{run_id}/digital-human")
        log(f"  {r.status_code}")

        log("=== Polling ===")
        for i in range(40):
            await asyncio.sleep(30)
            s = (await c.get(f"{BASE}/projects/{run_id}/status")).json()
            total = s.get("tasks_total", 0)
            succ = s.get("tasks_summary", {}).get("succeeded", 0)
            pend = s.get("tasks_summary", {}).get("pending", 0)
            fail = s.get("tasks_summary", {}).get("failed", 0)
            mins = (i + 1) * 30 // 60
            log(f"  [{mins:02d}m] t={total} s={succ} p={pend} f={fail}")

            # Check video URLs
            for t in s.get("tasks", []):
                if t.get("video_url"):
                    log(f"  VIDEO: {t['video_url']}")

            if s.get("all_succeeded"):
                log("  SUCCESS!")
                break
            if fail > 0 and pend == 0:
                log("  FAILED!")
                break


asyncio.run(main())
