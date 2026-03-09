"""Poll the latest DH project status."""
import asyncio, json, httpx, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8123/api/v1"
RUN_ID = "b9d8e58c-a8ed-4616-8f68-c04607553322"

async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        for i in range(24):  # 2 min
            r = await c.get(f"{BASE}/projects/{RUN_ID}/status")
            s = r.json()
            tasks = s.get("tasks", [])
            for t in tasks:
                st = t.get("status")
                vid = (t.get("video_url") or "")[:80]
                err = (t.get("error") or "")[:80]
                pid = t.get("provider_task_id", "")
                print(f"  poll {i+1}: status={st}, task_id={pid}, video={vid}, err={err}", flush=True)
            if not tasks:
                print(f"  poll {i+1}: no tasks", flush=True)
            if s.get("all_succeeded"):
                print("  ALL DONE!", flush=True)
                break
            done = all(t.get("status") in ("succeeded","failed") for t in tasks) if tasks else False
            if done:
                print("  ALL TASKS FINISHED", flush=True)
                break
            await asyncio.sleep(5)
    print("Done.", flush=True)

asyncio.run(main())
