import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import api_routes


@pytest.mark.asyncio
async def test_list_projects_includes_task_summary_and_result_video_url():
    sb = MagicMock()

    jobs_chain = MagicMock()
    jobs_chain.select.return_value = jobs_chain
    jobs_chain.order.return_value = jobs_chain
    jobs_chain.limit.return_value = jobs_chain
    jobs_chain.execute.return_value = MagicMock(
        data=[
            {
                "run_id": "run-123",
                "theme": "History test",
                "status": "processing",
                "video_url": None,
                "created_at": "2026-03-12T00:00:00+00:00",
                "updated_at": "2026-03-12T00:01:00+00:00",
            }
        ]
    )

    tasks_chain = MagicMock()
    tasks_chain.select.return_value = tasks_chain
    tasks_chain.in_.return_value = tasks_chain
    tasks_chain.execute.return_value = MagicMock(
        data=[
            {"run_id": "run-123", "status": "queued"},
            {"run_id": "run-123", "status": "submitted"},
            {"run_id": "run-123", "status": "succeeded"},
        ]
    )

    sessions_chain = MagicMock()
    sessions_chain.select.return_value = sessions_chain
    sessions_chain.in_.return_value = sessions_chain
    sessions_chain.execute.return_value = MagicMock(
        data=[
            {
                "run_id": "run-123",
                "status": "completed",
                "result": {"video_url": "https://cdn/final.mp4"},
            }
        ]
    )

    def table_side_effect(name):
        if name == "autoviralvid_jobs":
            return jobs_chain
        if name == "autoviralvid_video_tasks":
            return tasks_chain
        if name == "autoviralvid_crew_sessions":
            return sessions_chain
        raise AssertionError(f"Unexpected table access: {name}")

    sb.table.side_effect = table_side_effect

    with patch.object(api_routes, "supabase", sb):
        result = await api_routes.list_projects(40, SimpleNamespace(id="u1"))

    project = result["projects"][0]
    assert project["video_url"] == "https://cdn/final.mp4"
    assert project["session_status"] == "completed"
    assert project["result_video_url"] == "https://cdn/final.mp4"
    assert project["task_summary"]["total"] == 3
    assert project["task_summary"]["queued"] == 1
    assert project["task_summary"]["submitted"] == 1
    assert project["task_summary"]["succeeded"] == 1


@pytest.mark.asyncio
async def test_get_project_status_returns_frontend_compatible_summary_shape():
    sb = MagicMock()

    job_chain = MagicMock()
    job_chain.select.return_value = job_chain
    job_chain.eq.return_value = job_chain
    job_chain.single.return_value = job_chain
    job_chain.execute.return_value = MagicMock(
        data={
            "run_id": "run-123",
            "status": "processing",
            "updated_at": "2026-03-12T00:00:00+00:00",
            "video_url": None,
        }
    )

    tasks_chain = MagicMock()
    tasks_chain.select.return_value = tasks_chain
    tasks_chain.eq.return_value = tasks_chain
    tasks_chain.order.return_value = tasks_chain
    tasks_chain.execute.return_value = MagicMock(
        data=[
            {
                "id": "task-1",
                "clip_idx": 0,
                "status": "queued",
                "video_url": None,
                "error": None,
                "retry_count": 0,
                "updated_at": "2026-03-12T00:00:00+00:00",
            },
            {
                "id": "task-2",
                "clip_idx": 1,
                "status": "succeeded",
                "video_url": "https://cdn/clip.mp4",
                "error": None,
                "retry_count": 0,
                "updated_at": "2026-03-12T00:01:00+00:00",
            },
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
    svc.get_status = AsyncMock(return_value={"run_id": "run-123"})

    with patch.object(api_routes, "supabase", sb), patch.object(
        api_routes, "_get_project_service", return_value=svc
    ), patch.object(api_routes, "_ensure_queue_worker"):
        result = await api_routes.get_project_status("run-123", SimpleNamespace(id="u1"))

    assert result["status"] == "processing"
    assert result["project_status"] == "processing"
    assert result["summary"]["total"] == 2
    assert result["summary"]["queued"] == 1
    assert result["summary"]["succeeded"] == 1
    assert result["summary"]["all_done"] is False
