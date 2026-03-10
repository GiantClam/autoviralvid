import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import api_routes


@pytest.mark.asyncio
async def test_get_project_status_triggers_stitch_self_heal():
    sb = MagicMock()

    job_chain = MagicMock()
    job_chain.select.return_value = job_chain
    job_chain.eq.return_value = job_chain
    job_chain.single.return_value = job_chain
    job_chain.execute.side_effect = [
        MagicMock(
            data={"run_id": "run-123", "status": "processing", "updated_at": "2026-03-10T00:00:00+00:00", "video_url": None}
        ),
        MagicMock(
            data={"run_id": "run-123", "status": "completed", "updated_at": "2026-03-10T00:02:00+00:00", "video_url": "https://cdn/final.mp4"}
        ),
    ]

    tasks_chain = MagicMock()
    tasks_chain.select.return_value = tasks_chain
    tasks_chain.eq.return_value = tasks_chain
    tasks_chain.order.return_value = tasks_chain
    tasks_chain.execute.return_value = MagicMock(
        data=[
            {
                "id": "task-1",
                "clip_idx": 0,
                "status": "succeeded",
                "video_url": "https://provider/video.mp4",
                "error": None,
                "retry_count": 0,
                "updated_at": "2026-03-10T00:01:00+00:00",
            }
        ]
    )

    def table_side_effect(name):
        if name == "autoviralvid_jobs":
            return job_chain
        if name == "autoviralvid_video_tasks":
            return tasks_chain
        raise AssertionError(f"Unexpected table access: {name}")

    sb.table.side_effect = table_side_effect

    svc = MagicMock()
    svc.get_status = AsyncMock(return_value={"run_id": "run-123", "all_done": True})
    queue = MagicMock()
    queue.check_and_trigger_stitch = AsyncMock()

    with patch.object(api_routes, "supabase", sb), patch(
        "src.video_task_queue_supabase.ensure_supabase_queue_worker",
        return_value={"running": True},
    ) as ensure_worker, patch(
        "src.video_task_queue_supabase.get_supabase_queue",
        return_value=queue,
    ), patch.object(api_routes, "_get_project_service", return_value=svc):
        result = await api_routes.get_project_status("run-123", SimpleNamespace(id="u1"))

    assert result["all_succeeded"] is True
    assert result["project_status"] == "completed"
    ensure_worker.assert_any_call("get_project_status")
    ensure_worker.assert_any_call("project_status")
    queue.check_and_trigger_stitch.assert_awaited_once_with("run-123")
