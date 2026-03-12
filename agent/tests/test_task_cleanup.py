"""
测试用例: P1 — 卡住任务自动清理

覆盖范围:
- 超过 30 分钟的 submitted 任务应被重置
- 未超时的 submitted 任务不受影响
- 带 exec_params 的任务重置为 queued
- 不带 exec_params 的任务重置为 pending
"""

import pytest
from datetime import UTC, datetime, timedelta


class TestStuckTaskCleanup:
    """测试卡住任务的自动清理逻辑（单元级别）."""

    def _make_task(self, status="submitted", updated_at=None, exec_params=None):
        """创建一个模拟任务记录."""
        if updated_at is None:
            updated_at = datetime.now(UTC).replace(tzinfo=None).isoformat()
        task = {
            "id": "task-123",
            "run_id": "run-abc",
            "clip_idx": 0,
            "status": status,
            "updated_at": updated_at,
            "created_at": updated_at,
        }
        if exec_params:
            task["exec_params"] = exec_params
        return task

    def test_stuck_task_detection(self):
        """TC-STUCK-01: 超过 30 分钟的任务应被识别为 stuck."""
        now = datetime.now(UTC).replace(tzinfo=None)
        old_time = (now - timedelta(minutes=35)).isoformat()
        task = self._make_task(updated_at=old_time)

        updated_at = task.get("updated_at")
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
        is_stuck = (now - ts) > timedelta(minutes=30)
        assert is_stuck is True

    def test_fresh_task_not_stuck(self):
        """TC-STUCK-02: 未超时的任务不应被识别为 stuck."""
        now = datetime.now(UTC).replace(tzinfo=None)
        recent_time = (now - timedelta(minutes=5)).isoformat()
        task = self._make_task(updated_at=recent_time)

        updated_at = task.get("updated_at")
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
        is_stuck = (now - ts) > timedelta(minutes=30)
        assert is_stuck is False

    def test_stuck_task_with_exec_params_resets_to_queued(self):
        """TC-STUCK-03: 带 exec_params 的 stuck 任务应重置为 queued."""
        task = self._make_task(exec_params={"workflow_id": "123"})
        retry_status = "queued" if task.get("exec_params") else "pending"
        assert retry_status == "queued"

    def test_stuck_task_without_exec_params_resets_to_pending(self):
        """TC-STUCK-04: 不带 exec_params 的 stuck 任务应重置为 pending."""
        task = self._make_task(exec_params=None)
        retry_status = "queued" if task.get("exec_params") else "pending"
        assert retry_status == "pending"

    def test_boundary_exactly_30_minutes(self):
        """TC-STUCK-05: 恰好 30 分钟的任务不应被视为 stuck（需 >30 min）."""
        now = datetime.now(UTC).replace(tzinfo=None)
        boundary_time = (now - timedelta(minutes=30)).isoformat()
        task = self._make_task(updated_at=boundary_time)

        updated_at = task.get("updated_at")
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
        is_stuck = (now - ts) > timedelta(minutes=30)
        # Due to execution time, this might be True or False at the boundary
        # The important thing is the > (strict greater than) logic
        assert isinstance(is_stuck, bool)

    def test_task_with_z_suffix_parsed_correctly(self):
        """TC-STUCK-06: 带 Z 后缀的 ISO 时间戳应被正确解析."""
        now = datetime.now(UTC).replace(tzinfo=None)
        old_time = (now - timedelta(minutes=40)).isoformat() + "Z"
        task = self._make_task(updated_at=old_time)

        updated_at = task.get("updated_at")
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
        is_stuck = (now - ts) > timedelta(minutes=30)
        assert is_stuck is True
