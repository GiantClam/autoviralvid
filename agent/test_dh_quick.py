"""Quick test: create project + submit digital human + poll once."""
import asyncio, json, httpx, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8123/api/v1"
LOG = open("test_dh_log.txt", "w", encoding="utf-8")

def log(msg):
    print(msg, flush=True)
    LOG.write(msg + "\n")
    LOG.flush()

async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        # Step 1: Create
        log("=== Step 1: Create ===")
        r = await c.post(f"{BASE}/projects", json={
            "template_id": "digital-human",
            "theme": "test digital human",
            "product_image_url": "https://cdn.pixabay.com/photo/2016/11/29/13/14/attractive-1869761_1280.jpg",
            "style": "modern",
            "duration": 10,
            "orientation": "portrait",
            "audio_url": "https://cdn.pixabay.com/audio/2024/11/08/audio_93a1e8eb4e.mp3",
            "voice_mode": 0,
            "motion_prompt": "model presenting product for e-commerce",
        })
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
        try:
            data2 = r.json()
            log(f"  response={json.dumps(data2, ensure_ascii=False)[:300]}")
        except Exception:
            log(f"  text={r.text[:300]}")
            return

        # Step 3: Poll 5 times
        log("=== Step 3: Poll status ===")
        for i in range(5):
            await asyncio.sleep(5)
            r = await c.get(f"{BASE}/projects/{run_id}/status")
            s = r.json()
            tasks = s.get("tasks", [])
            task_info = [(t.get("status"), (t.get("video_url") or "")[:50]) for t in tasks]
            log(f"  poll {i+1}: total={s.get('tasks_total',0)}, "
                f"succeeded={s.get('tasks_summary',{}).get('succeeded',0)}, "
                f"pending={s.get('tasks_summary',{}).get('pending',0)}, "
                f"failed={s.get('tasks_summary',{}).get('failed',0)}, "
                f"tasks={task_info}")
            if s.get("all_succeeded"):
                log("  ALL SUCCEEDED!")
                break

    log("=== Done ===")
    LOG.close()

asyncio.run(main())
