#!/usr/bin/env python3
"""Quick test with working public URLs"""

import asyncio, json, httpx, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8123/api/v1"

# Use public accessible URLs
PHOTO_URL = "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400"
AUDIO_URL = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"


def log(msg):
    print(msg, flush=True)


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        # Step 1: Create
        log("=== Step 1: Create project ===")
        r = await c.post(
            f"{BASE}/projects",
            json={
                "template_id": "digital-human",
                "theme": "数字人4分钟测试",
                "product_image_url": PHOTO_URL,
                "style": "现代简约",
                "duration": 240,
                "orientation": "竖屏",
                "audio_url": AUDIO_URL,
                "voice_mode": 0,
                "motion_prompt": "模特正在做产品展示",
            },
        )
        log(f"  status={r.status_code}")
        data = r.json()
        run_id = data.get("run_id")
        log(f"  run_id={run_id}")
        if not run_id:
            log(f"  ERROR: {json.dumps(data, ensure_ascii=False)[:300]}")
            return

        # Step 2: Submit DH
        log("=== Step 2: Submit Digital Human ===")
        r = await c.post(f"{BASE}/projects/{run_id}/digital-human")
        log(f"  status={r.status_code}")
        data2 = r.json()
        log(f"  response={json.dumps(data2, ensure_ascii=False)[:200]}")

        # Step 3: Poll
        log("=== Step 3: Polling (max 20 min) ===")
        for i in range(40):
            await asyncio.sleep(30)
            r = await c.get(f"{BASE}/projects/{run_id}/status")
            s = r.json()
            total = s.get("tasks_total", 0)
            succ = s.get("tasks_summary", {}).get("succeeded", 0)
            pend = s.get("tasks_summary", {}).get("pending", 0)
            fail = s.get("tasks_summary", {}).get("failed", 0)
            mins = (i + 1) * 30 // 60
            log(
                f"  [{mins:02d}min] total={total}, succ={succ}, pend={pend}, fail={fail}"
            )
            if s.get("all_succeeded"):
                log("  SUCCESS!")
                break
            if fail > 0 and pend == 0:
                log("  FAILED!")
                break

        log("=== Done ===")


asyncio.run(main())
