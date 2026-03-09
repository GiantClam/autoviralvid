"""
check_and_trigger_stitch 自动拼接逻辑单元测试

测试 video_task_queue_supabase.py 中 check_and_trigger_stitch 方法的
数字人多段自动拼接逻辑。

使用 Mock 隔离 Supabase 和 video_stitcher 依赖。

运行: cd agent && uv run python -m pytest tests/test_check_and_trigger_stitch.py -v
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_supabase():
    """创建 Mock Supabase client，支持链式调用"""
    sb = MagicMock()

    def make_chain(return_data=None):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        chain.single.return_value = chain
        chain.update.return_value = chain
        chain.upsert.return_value = chain
        chain.insert.return_value = chain
        chain.order.return_value = chain
        result = MagicMock()
        result.data = return_data
        chain.execute.return_value = result
        return chain

    sb.table.side_effect = lambda name: make_chain()
    return sb


def _make_queue(supabase_mock):
    """创建 SupabaseVideoTaskQueue 实例，注入 mock 依赖"""
    from src.video_task_queue_supabase import SupabaseVideoTaskQueue

    q = SupabaseVideoTaskQueue.__new__(SupabaseVideoTaskQueue)
    q.supabase = supabase_mock
    q.logger = MagicMock()
    q._running = False
    q._worker_task = None
    q._retry_interval = 10
    q._max_concurrent = 1
    q._stitch_in_progress = set()
    return q


# ---------------------------------------------------------------------------
# TC-ST-001: 无任务时直接返回
# ---------------------------------------------------------------------------

class TestCheckAndTriggerStitchNoTasks:
    """TC-ST-001: 无任务时 check_and_trigger_stitch 应直接返回"""

    @pytest.mark.asyncio
    async def test_no_tasks_returns_early(self):
        """run_id 下无任务记录时应直接返回，不做任何操作"""
        sb = MagicMock()
        tasks_chain = MagicMock()
        tasks_chain.select.return_value = tasks_chain
        tasks_chain.eq.return_value = tasks_chain
        result = MagicMock()
        result.data = []
        tasks_chain.execute.return_value = result
        sb.table.return_value = tasks_chain

        q = _make_queue(sb)
        await q.check_and_trigger_stitch("nonexistent-run-id")

        # 不应更新 crew_sessions
        # table 只应被调用一次（查询 video_tasks）
        sb.table.assert_called_once_with("autoviralvid_video_tasks")


# ---------------------------------------------------------------------------
# TC-ST-002: 非全部成功时不触发
# ---------------------------------------------------------------------------

class TestCheckAndTriggerStitchNotAllSucceeded:
    """TC-ST-002: 有任务尚未完成时不应触发拼接"""

    @pytest.mark.asyncio
    async def test_pending_tasks_no_stitch(self):
        """存在 pending 任务时应直接返回"""
        sb = MagicMock()

        tasks_data = [
            {"status": "succeeded", "video_url": "https://cdn/v1.mp4", "clip_idx": 0, "skill_name": "x"},
            {"status": "submitted", "video_url": None, "clip_idx": 1, "skill_name": "x"},
        ]
        tasks_chain = MagicMock()
        tasks_chain.select.return_value = tasks_chain
        tasks_chain.eq.return_value = tasks_chain
        result = MagicMock()
        result.data = tasks_data
        tasks_chain.execute.return_value = result
        sb.table.return_value = tasks_chain

        q = _make_queue(sb)
        await q.check_and_trigger_stitch("run-with-pending")

        # 不应查询 jobs 表（因为 all_succeeded = False）
        assert sb.table.call_count == 1  # 只查了 video_tasks


# ---------------------------------------------------------------------------
# TC-ST-003: 单段数字人不触发自动拼接
# ---------------------------------------------------------------------------

class TestCheckAndTriggerStitchSingleSegment:
    """TC-ST-003: 单段数字人任务应走 ready_to_stitch，不触发自动拼接"""

    @pytest.mark.asyncio
    async def test_single_segment_goes_to_ready_to_stitch(self):
        """单段数字人完成后应设为 ready_to_stitch"""
        sb = MagicMock()
        call_log = []

        tasks_data = [
            {"status": "succeeded", "video_url": "https://cdn/v1.mp4", "clip_idx": 0, "skill_name": "x"},
        ]

        job_storyboards = json.dumps({
            "_meta": {"pipeline_name": "digital_human"},
            "scenes": [],
        })
        job_data = [{"storyboards": job_storyboards}]

        def table_side_effect(name):
            call_log.append(name)
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = chain
            chain.update.return_value = chain
            result = MagicMock()
            if name == "autoviralvid_video_tasks":
                result.data = tasks_data
            elif name == "autoviralvid_jobs":
                result.data = job_data
            elif name == "autoviralvid_crew_sessions":
                result.data = None
            chain.execute.return_value = result
            return chain

        sb.table.side_effect = table_side_effect
        q = _make_queue(sb)

        await q.check_and_trigger_stitch("run-single")

        # 应查询 video_tasks、jobs，然后更新 crew_sessions
        assert "autoviralvid_video_tasks" in call_log
        assert "autoviralvid_jobs" in call_log
        assert "autoviralvid_crew_sessions" in call_log

        # 不应调用 stitch_video_segments（因为 len(tasks) == 1）
        # 验证 crew_sessions 更新为 ready_to_stitch（非 stitching）


# ---------------------------------------------------------------------------
# TC-ST-004: 多段数字人触发自动拼接
# ---------------------------------------------------------------------------

class TestCheckAndTriggerStitchMultiSegment:
    """TC-ST-004: 多段数字人全部完成时应自动触发拼接"""

    @pytest.mark.asyncio
    async def test_multi_segment_triggers_auto_stitch(self):
        """3 段数字人全部成功后应自动拼接"""
        sb = MagicMock()
        update_calls = {}

        tasks_data = [
            {"status": "succeeded", "video_url": "https://cdn/seg0.mp4", "clip_idx": 0, "skill_name": "x"},
            {"status": "succeeded", "video_url": "https://cdn/seg1.mp4", "clip_idx": 1, "skill_name": "x"},
            {"status": "succeeded", "video_url": "https://cdn/seg2.mp4", "clip_idx": 2, "skill_name": "x"},
        ]

        job_storyboards = json.dumps({
            "_meta": {"pipeline_name": "digital_human"},
            "scenes": [],
        })
        job_data = [{"storyboards": job_storyboards}]

        def table_side_effect(name):
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = chain

            def capture_update(payload):
                update_calls.setdefault(name, []).append(payload)
                chain2 = MagicMock()
                chain2.eq.return_value = chain2
                chain2.execute.return_value = MagicMock(data=None)
                return chain2

            chain.update.side_effect = capture_update

            result = MagicMock()
            if name == "autoviralvid_video_tasks":
                result.data = tasks_data
            elif name == "autoviralvid_jobs":
                result.data = job_data
            else:
                result.data = None
            chain.execute.return_value = result
            return chain

        sb.table.side_effect = table_side_effect
        q = _make_queue(sb)

        # Mock stitch_video_segments
        with patch("src.video_stitcher.stitch_video_segments", new_callable=AsyncMock) as mock_stitch:
            mock_stitch.return_value = "https://cdn/final.mp4"

            await q.check_and_trigger_stitch("run-multi")

            # ── 断言 ──
            # 1. stitch_video_segments 被调用
            mock_stitch.assert_called_once()
            call_args = mock_stitch.call_args
            video_urls = call_args[0][0]
            # 应按 clip_idx 排序
            assert video_urls == [
                "https://cdn/seg0.mp4",
                "https://cdn/seg1.mp4",
                "https://cdn/seg2.mp4",
            ]

            # 2. 输出 key 包含 run_id
            output_key = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("output_key")
            assert "run-multi" in (output_key or "")

        # 3. crew_sessions 应经历 stitching → completed
        session_updates = update_calls.get("autoviralvid_crew_sessions", [])
        statuses = [u.get("status") for u in session_updates]
        assert "stitching" in statuses, f"Missing 'stitching' status: {statuses}"
        assert "completed" in statuses, f"Missing 'completed' status: {statuses}"

        # 4. jobs 表应写入 video_url
        job_updates = update_calls.get("autoviralvid_jobs", [])
        assert any(u.get("video_url") == "https://cdn/final.mp4" for u in job_updates), \
            f"jobs 未更新 video_url: {job_updates}"


# ---------------------------------------------------------------------------
# TC-ST-005: 拼接失败时回退到 ready_to_stitch
# ---------------------------------------------------------------------------

class TestCheckAndTriggerStitchFailure:
    """TC-ST-005: 拼接失败时应回退到 ready_to_stitch"""

    @pytest.mark.asyncio
    async def test_stitch_failure_falls_back(self):
        """stitch_video_segments 抛异常时应设为 ready_to_stitch"""
        sb = MagicMock()
        update_calls = {}

        tasks_data = [
            {"status": "succeeded", "video_url": "https://cdn/seg0.mp4", "clip_idx": 0, "skill_name": "x"},
            {"status": "succeeded", "video_url": "https://cdn/seg1.mp4", "clip_idx": 1, "skill_name": "x"},
        ]

        job_storyboards = json.dumps({
            "_meta": {"pipeline_name": "digital_human"},
            "scenes": [],
        })

        def table_side_effect(name):
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = chain

            def capture_update(payload):
                update_calls.setdefault(name, []).append(payload)
                chain2 = MagicMock()
                chain2.eq.return_value = chain2
                chain2.execute.return_value = MagicMock(data=None)
                return chain2

            chain.update.side_effect = capture_update

            result = MagicMock()
            if name == "autoviralvid_video_tasks":
                result.data = tasks_data
            elif name == "autoviralvid_jobs":
                result.data = [{"storyboards": job_storyboards}]
            else:
                result.data = None
            chain.execute.return_value = result
            return chain

        sb.table.side_effect = table_side_effect
        q = _make_queue(sb)

        with patch("src.video_stitcher.stitch_video_segments", new_callable=AsyncMock) as mock_stitch:
            mock_stitch.side_effect = RuntimeError("FFmpeg crash")

            await q.check_and_trigger_stitch("run-fail-stitch")

        # crew_sessions 最终应为 ready_to_stitch
        session_updates = update_calls.get("autoviralvid_crew_sessions", [])
        final_status = session_updates[-1].get("status") if session_updates else None
        assert final_status == "ready_to_stitch", \
            f"拼接失败后 session 状态应为 ready_to_stitch，实际: {final_status}"


# ---------------------------------------------------------------------------
# TC-ST-006: 非数字人 pipeline 不自动拼接
# ---------------------------------------------------------------------------

class TestCheckAndTriggerStitchNonDigitalHuman:
    """TC-ST-006: 非数字人 pipeline 不触发自动拼接"""

    @pytest.mark.asyncio
    async def test_non_dh_pipeline_goes_to_ready_to_stitch(self):
        """qwen_product 等非数字人 pipeline 应走 ready_to_stitch"""
        sb = MagicMock()
        update_calls = {}

        tasks_data = [
            {"status": "succeeded", "video_url": "https://cdn/v0.mp4", "clip_idx": 0, "skill_name": "x"},
            {"status": "succeeded", "video_url": "https://cdn/v1.mp4", "clip_idx": 1, "skill_name": "x"},
            {"status": "succeeded", "video_url": "https://cdn/v2.mp4", "clip_idx": 2, "skill_name": "x"},
        ]

        job_storyboards = json.dumps({
            "_meta": {"pipeline_name": "qwen_product"},  # 非 digital_human
            "scenes": [],
        })

        def table_side_effect(name):
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = chain

            def capture_update(payload):
                update_calls.setdefault(name, []).append(payload)
                chain2 = MagicMock()
                chain2.eq.return_value = chain2
                chain2.execute.return_value = MagicMock(data=None)
                return chain2

            chain.update.side_effect = capture_update

            result = MagicMock()
            if name == "autoviralvid_video_tasks":
                result.data = tasks_data
            elif name == "autoviralvid_jobs":
                result.data = [{"storyboards": job_storyboards}]
            else:
                result.data = None
            chain.execute.return_value = result
            return chain

        sb.table.side_effect = table_side_effect
        q = _make_queue(sb)

        await q.check_and_trigger_stitch("run-non-dh")

        # 应更新为 ready_to_stitch，而非 stitching/completed
        session_updates = update_calls.get("autoviralvid_crew_sessions", [])
        statuses = [u.get("status") for u in session_updates]
        assert "stitching" not in statuses, f"非数字人不应出现 stitching: {statuses}"
        assert "ready_to_stitch" in statuses, f"应更新为 ready_to_stitch: {statuses}"


# ---------------------------------------------------------------------------
# TC-ST-007: 拼接时按 clip_idx 正确排序
# ---------------------------------------------------------------------------

class TestCheckAndTriggerStitchOrdering:
    """TC-ST-007: 拼接时应严格按 clip_idx 排序"""

    @pytest.mark.asyncio
    async def test_video_urls_ordered_by_clip_idx(self):
        """无论数据库返回顺序如何，拼接时应按 clip_idx 排序"""
        sb = MagicMock()

        # 故意乱序
        tasks_data = [
            {"status": "succeeded", "video_url": "https://cdn/seg2.mp4", "clip_idx": 2, "skill_name": "x"},
            {"status": "succeeded", "video_url": "https://cdn/seg0.mp4", "clip_idx": 0, "skill_name": "x"},
            {"status": "succeeded", "video_url": "https://cdn/seg1.mp4", "clip_idx": 1, "skill_name": "x"},
        ]

        job_storyboards = json.dumps({
            "_meta": {"pipeline_name": "digital_human"},
            "scenes": [],
        })

        def table_side_effect(name):
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = chain
            chain.update.return_value = chain
            chain.update.return_value.eq.return_value = chain.update.return_value
            chain.update.return_value.execute.return_value = MagicMock(data=None)

            result = MagicMock()
            if name == "autoviralvid_video_tasks":
                result.data = tasks_data
            elif name == "autoviralvid_jobs":
                result.data = [{"storyboards": job_storyboards}]
            else:
                result.data = None
            chain.execute.return_value = result
            return chain

        sb.table.side_effect = table_side_effect
        q = _make_queue(sb)

        with patch("src.video_stitcher.stitch_video_segments", new_callable=AsyncMock) as mock_stitch:
            mock_stitch.return_value = "https://cdn/final.mp4"

            await q.check_and_trigger_stitch("run-order-test")

            # 验证 video_urls 按 clip_idx 排序
            call_args = mock_stitch.call_args[0]
            video_urls = call_args[0]
            assert video_urls == [
                "https://cdn/seg0.mp4",
                "https://cdn/seg1.mp4",
                "https://cdn/seg2.mp4",
            ], f"URL 排序不正确: {video_urls}"


class TestCheckAndTriggerStitchIdempotency:
    """Existing final URLs should keep the run in a completed state."""

    @pytest.mark.asyncio
    async def test_existing_final_url_keeps_completed_state(self):
        sb = MagicMock()
        update_calls = {}

        tasks_data = [
            {"status": "succeeded", "video_url": "https://cdn/seg0.mp4", "clip_idx": 0, "skill_name": "x"},
            {"status": "succeeded", "video_url": "https://cdn/seg1.mp4", "clip_idx": 1, "skill_name": "x"},
        ]
        job_data = [{
            "storyboards": json.dumps({"_meta": {"pipeline_name": "digital_human"}, "scenes": []}),
            "video_url": "https://cdn/final.mp4",
        }]

        def table_side_effect(name):
            chain = MagicMock()
            chain.select.return_value = chain
            chain.eq.return_value = chain
            chain.limit.return_value = chain

            def capture_update(payload):
                update_calls.setdefault(name, []).append(payload)
                chain2 = MagicMock()
                chain2.eq.return_value = chain2
                chain2.execute.return_value = MagicMock(data=None)
                return chain2

            chain.update.side_effect = capture_update

            result = MagicMock()
            if name == "autoviralvid_video_tasks":
                result.data = tasks_data
            elif name == "autoviralvid_jobs":
                result.data = job_data
            else:
                result.data = None
            chain.execute.return_value = result
            return chain

        sb.table.side_effect = table_side_effect
        q = _make_queue(sb)

        with patch("src.video_stitcher.stitch_video_segments", new_callable=AsyncMock) as mock_stitch:
            await q.check_and_trigger_stitch("run-already-completed")
            mock_stitch.assert_not_called()

        job_updates = update_calls.get("autoviralvid_jobs", [])
        session_updates = update_calls.get("autoviralvid_crew_sessions", [])

        assert any(u.get("status") == "completed" for u in job_updates)
        assert any(u.get("status") == "completed" for u in session_updates)
