import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")
sys.path.append(str(Path(__file__).resolve().parents[1]))

os.environ["RUNNINGHUB_MAX_CONCURRENT"] = "1"
os.environ["VIDEO_QUEUE_MAX_QUEUE_RETRIES"] = "60"
os.environ["VIDEO_QUEUE_MAX_GENERAL_RETRIES"] = "6"
os.environ["VIDEO_QUEUE_POLL_INTERVAL"] = "10"

from src.project_service import ProjectService
from src.video_task_queue_supabase import get_supabase_queue, start_supabase_queue_worker


async def main():
    run_id = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "2067dea5-bc3a-4900-aaf7-b9683651751c"
    )
    print(f"RUN_ID={run_id}", flush=True)

    svc = ProjectService()
    start_supabase_queue_worker()
    q = get_supabase_queue()
    print(f"Worker running={bool(q and q._running)}", flush=True)

    poll_interval = 15
    max_polls = 200  # 50 min

    for i in range(1, max_polls + 1):
        st = await svc.get_status(run_id)
        total = st.get("total", 0)
        succ = st.get("succeeded", 0)
        fail = st.get("failed", 0)
        pend = st.get("pending", 0)
        all_done = st.get("all_done", False)

        print(
            f"POLL {i:03d}: total={total} succ={succ} fail={fail} "
            f"pending={pend} all_done={all_done}",
            flush=True,
        )
        for t in st.get("tasks", []):
            print(
                "  - clip={clip} status={status} retry={retry} "
                "provider={pid} err={err}".format(
                    clip=t.get("clip_idx"),
                    status=t.get("status"),
                    retry=t.get("retry_count"),
                    pid=t.get("provider_task_id"),
                    err=(t.get("error") or "")[:120],
                ),
                flush=True,
            )

        row = (
            svc._sb.table("autoviralvid_jobs")
            .select("status,video_url")
            .eq("run_id", run_id)
            .limit(1)
            .execute()
            .data
        )
        row = (row or [{}])[0]
        if row.get("video_url"):
            print(f"FINAL_VIDEO_URL={row.get('video_url')}", flush=True)
            print(f"PROJECT_STATUS={row.get('status')}", flush=True)
            print("DONE=success", flush=True)
            return

        if all_done and fail == 0 and total > 1 and q:
            print("All segments succeeded, triggering stitch check once...", flush=True)
            await q.check_and_trigger_stitch(run_id)

        if all_done and fail > 0 and pend == 0:
            print("DONE=failed", flush=True)
            return

        await asyncio.sleep(poll_interval)

    print("DONE=timeout", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
