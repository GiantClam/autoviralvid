import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")
sys.path.append(str(Path(__file__).resolve().parents[1]))

# Queue tuning for long-audio E2E stability
os.environ["RUNNINGHUB_MAX_CONCURRENT"] = "3"
os.environ["VIDEO_QUEUE_MAX_QUEUE_RETRIES"] = "60"
os.environ["VIDEO_QUEUE_MAX_GENERAL_RETRIES"] = "6"
os.environ["VIDEO_QUEUE_POLL_INTERVAL"] = "10"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

from src.project_service import ProjectService
from src.video_task_queue_supabase import get_supabase_queue, start_supabase_queue_worker

PHOTO_URL = os.getenv("E2E_DH_PHOTO_URL", "https://s.autoviralvid.com/test_dh_image_2026.png")
AUDIO_URL = os.getenv("E2E_DH_AUDIO_URL", "https://s.autoviralvid.com/uploads/test_dh_audio_5min_17f4de4f.mp3")
DURATION_SECONDS = int(os.getenv("E2E_DH_DURATION_SECONDS", "325"))
THEME = os.getenv("E2E_DH_THEME", "E2E digital human long audio test")
MOTION_PROMPT = os.getenv(
    "E2E_DH_MOTION_PROMPT",
    "Presenter speaks steadily about product highlights with a stable medium shot.",
)
POLL_INTERVAL_SECONDS = int(os.getenv("E2E_DH_POLL_INTERVAL_SECONDS", "20"))
MAX_POLLS = int(os.getenv("E2E_DH_MAX_POLLS", "180"))


async def read_project_row(svc: ProjectService, run_id: str):
    res = (
        svc._sb.table("autoviralvid_jobs")
        .select("*")
        .eq("run_id", run_id)
        .limit(1)
        .execute()
    )
    return (res.data or [{}])[0]


async def main():
    print("=== E2E Digital Human (>3min) START ===", flush=True)
    print(f"Time: {datetime.now().isoformat()}", flush=True)
    print(f"AUDIO_URL={AUDIO_URL}", flush=True)

    svc = ProjectService()

    # Start queue worker in the current event loop.
    start_supabase_queue_worker()
    queue = get_supabase_queue()
    print(f"Worker running={bool(queue and queue._running)}", flush=True)

    project = await svc.create_project(
        "digital-human",
        {
            "theme": THEME,
            "product_image_url": PHOTO_URL,
            "style": "modern clean",
            "duration": DURATION_SECONDS,
            "orientation": "portrait",
            "audio_url": AUDIO_URL,
            "voice_mode": 0,
            "motion_prompt": MOTION_PROMPT,
        },
    )

    run_id = project.get("run_id")
    if not run_id:
        print(f"CREATE_FAILED: {project}", flush=True)
        return

    print(f"RUN_ID={run_id}", flush=True)

    submitted = await svc.submit_digital_human(run_id)
    print(f"SUBMIT_RESULT_COUNT={len(submitted)}", flush=True)
    print(
        f"SUBMIT_RESULT_SAMPLE={json.dumps(submitted[:3], ensure_ascii=False)}",
        flush=True,
    )

    last_summary = None

    for i in range(1, MAX_POLLS + 1):
        st = await svc.get_status(run_id)
        total = st.get("total", 0)
        succ = st.get("succeeded", 0)
        fail = st.get("failed", 0)
        pend = st.get("pending", 0)
        all_done = st.get("all_done", False)

        summary = (total, succ, fail, pend)
        if summary != last_summary or i % 3 == 0:
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
            last_summary = summary

        row = await read_project_row(svc, run_id)
        final_url = row.get("video_url") or ""
        project_status = row.get("status")

        if final_url:
            print(f"FINAL_VIDEO_URL={final_url}", flush=True)
            print(f"PROJECT_STATUS={project_status}", flush=True)
            print("=== E2E SUCCESS ===", flush=True)
            return

        if all_done and fail > 0 and pend == 0:
            print("=== E2E DONE WITH FAILURES ===", flush=True)
            print(f"PROJECT_STATUS={project_status}", flush=True)
            print("No final video_url present.", flush=True)
            return

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    row = await read_project_row(svc, run_id)
    print("=== E2E TIMEOUT ===", flush=True)
    print(f"PROJECT_STATUS={row.get('status')}", flush=True)
    print(f"PROJECT_VIDEO_URL={row.get('video_url')}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
