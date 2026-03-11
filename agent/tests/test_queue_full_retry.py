import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_queue(max_queue_retries: int):
    from src.video_task_queue_supabase import SupabaseVideoTaskQueue

    q = SupabaseVideoTaskQueue.__new__(SupabaseVideoTaskQueue)
    q.supabase = MagicMock()
    q.logger = MagicMock()
    q._max_queue_retries = max_queue_retries
    q._max_general_retries = 3
    q._submit_queued_task = AsyncMock(side_effect=RuntimeError("API code=421: TASK_QUEUE_MAXED"))
    q._submit_pending_task = AsyncMock()
    return q


def _update_payloads(queue):
    chain = queue.supabase.table.return_value
    return [call.args[0] for call in chain.update.call_args_list]


@pytest.mark.asyncio
async def test_queue_full_is_requeued_while_under_retry_budget():
    queue = _make_queue(max_queue_retries=60)
    chain = MagicMock()
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.execute.return_value = MagicMock()
    queue.supabase.table.return_value = chain

    await queue._submit_task(
        {
            "id": "task-1",
            "run_id": "run-1",
            "clip_idx": 3,
            "status": "queued",
            "retry_count": 10,
        }
    )

    assert queue._submit_queued_task.await_count == 1
    payload = _update_payloads(queue)[0]
    assert payload["status"] == "queued"
    assert payload["retry_count"] == 11
    assert payload["error"] == "RunningHub queue full (retry 11)"


@pytest.mark.asyncio
async def test_queue_full_fails_after_retry_budget_is_exhausted():
    queue = _make_queue(max_queue_retries=10)
    chain = MagicMock()
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.execute.return_value = MagicMock()
    queue.supabase.table.return_value = chain

    await queue._submit_task(
        {
            "id": "task-2",
            "run_id": "run-2",
            "clip_idx": 4,
            "status": "queued",
            "retry_count": 10,
        }
    )

    assert queue._submit_queued_task.await_count == 1
    assert _update_payloads(queue)[0]["status"] == "failed"
    assert "Max queue-full retries exceeded" in _update_payloads(queue)[0]["error"]
