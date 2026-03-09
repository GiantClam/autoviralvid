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
    run_id = sys.argv[1]
    loops = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    interval = int(sys.argv[3]) if len(sys.argv) > 3 else 15

    svc = ProjectService()
    start_supabase_queue_worker()
    q = get_supabase_queue()
    print(f"run_id={run_id} worker_running={bool(q and q._running)}")

    for i in range(1, loops + 1):
        st = await svc.get_status(run_id)
        total = st.get("total", 0)
        succ = st.get("succeeded", 0)
        fail = st.get("failed", 0)
        pend = st.get("pending", 0)
        all_done = st.get("all_done", False)

        if i == 1 or i % 4 == 0 or all_done:
            print(
                f"tick={i} total={total} succ={succ} fail={fail} "
                f"pending={pend} all_done={all_done}"
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
            print(f"final_video_url={row.get('video_url')}")
            print(f"project_status={row.get('status')}")
            return

        if all_done and fail == 0 and total > 1 and q:
            await q.check_and_trigger_stitch(run_id)
        if all_done and fail > 0 and pend == 0:
            print("done_failed=true")
            return

        await asyncio.sleep(interval)

    # Final snapshot for this batch
    st = await svc.get_status(run_id)
    print(
        f"batch_end total={st.get('total',0)} succ={st.get('succeeded',0)} "
        f"fail={st.get('failed',0)} pending={st.get('pending',0)}"
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: uv run python scripts/advance_run_once.py <run_id> [loops] [interval]")
    asyncio.run(main())
