import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import api_routes


def _mock_supabase():
    sb = MagicMock()

    select_chain = MagicMock()
    select_chain.select.return_value = select_chain
    select_chain.eq.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute.return_value = MagicMock(data=[{"run_id": "run-123"}])

    update_chain = MagicMock()
    update_chain.eq.return_value = update_chain
    update_chain.execute.return_value = MagicMock(data=None)

    jobs_table = MagicMock()
    jobs_table.select.return_value = select_chain
    jobs_table.update.return_value = update_chain

    def table_side_effect(name):
        if name == "autoviralvid_jobs":
            return jobs_table
        raise AssertionError(f"Unexpected table access: {name}")

    sb.table.side_effect = table_side_effect
    return sb, jobs_table


@pytest.mark.asyncio
async def test_submit_digital_human_persists_tasks_before_response():
    sb, jobs_table = _mock_supabase()
    background_tasks = BackgroundTasks()
    service = SimpleNamespace(submit_digital_human=AsyncMock(return_value=[{"ok": True}]))

    with patch.object(api_routes, "_require_supabase", return_value=sb), patch.object(
        api_routes, "_ensure_queue_worker"
    ) as ensure_worker, patch.object(
        api_routes, "_get_project_service", return_value=service
    ):
        response = await api_routes.submit_digital_human(
            "run-123",
            background_tasks,
            SimpleNamespace(id="user-1"),
        )

        assert response == {"run_id": "run-123", "status": "generating_digital_human"}
        ensure_worker.assert_called_once_with("submit_digital_human")
        assert len(background_tasks.tasks) == 0
        service.submit_digital_human.assert_awaited_once_with("run-123")

    first_update = jobs_table.update.call_args_list[0].args[0]
    assert first_update["status"] == "generating_videos"
