import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main


@pytest.mark.asyncio
async def test_webhook_success_triggers_stitch_check():
    sb = MagicMock()

    query_chain = MagicMock()
    query_chain.select.return_value = query_chain
    query_chain.eq.return_value = query_chain
    query_chain.execute.return_value = MagicMock(
        data=[{"run_id": "run-123", "clip_idx": 0}]
    )

    update_chain = MagicMock()
    update_chain.eq.return_value = update_chain
    update_chain.execute.return_value = MagicMock(data=None)

    def table_side_effect(name):
        if name == "autoviralvid_video_tasks":
            table = MagicMock()
            table.select.return_value = query_chain
            table.update.return_value = update_chain
            return table
        raise AssertionError(f"Unexpected table access: {name}")

    sb.table.side_effect = table_side_effect

    request = MagicMock()
    request.json = AsyncMock(
        return_value={
            "taskId": "provider-123",
            "status": "success",
            "outputs": [{"fileUrl": "https://provider/video.mp4"}],
        }
    )

    queue = MagicMock()
    queue.check_and_trigger_stitch = AsyncMock()

    created_tasks = []
    original_create_task = asyncio.create_task

    def track_task(coro):
        task = original_create_task(coro)
        created_tasks.append(task)
        return task

    with patch.object(main, "supabase", sb), patch.object(
        main, "upload_url_to_r2", new=AsyncMock(return_value="https://cdn/video.mp4")
    ) as mock_upload, patch(
        "src.video_task_queue_supabase.ensure_supabase_queue_worker",
        return_value={"running": True},
    ) as ensure_worker, patch(
        "src.video_task_queue_supabase.get_supabase_queue",
        return_value=queue,
    ), patch.object(main.asyncio, "create_task", side_effect=track_task):
        response = await main.webhook_runninghub(request)
        assert response == {"ok": True}

        if created_tasks:
            await asyncio.gather(*created_tasks)

    ensure_worker.assert_called_once_with("runninghub_webhook")
    mock_upload.assert_awaited_once_with(
        "https://provider/video.mp4",
        "run-123_clip0.mp4",
    )
    queue.check_and_trigger_stitch.assert_awaited_once_with("run-123")
