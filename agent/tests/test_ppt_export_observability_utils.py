from src.ppt_export_observability_utils import (
    build_persisted_diagnostics,
    build_strict_failure_detail,
    merge_strict_blockers_into_alerts,
)


def test_merge_strict_blockers_into_alerts_dedupes_by_code():
    alerts = [{"code": "a", "message": "A"}]
    blockers = [{"code": "a", "message": "A2"}, {"code": "b", "message": "B"}]
    merged = merge_strict_blockers_into_alerts(alerts, blockers)
    assert [item.get("code") for item in merged] == ["a", "b"]


def test_build_persisted_diagnostics_keeps_last_20_and_appends_summaries():
    diagnostics = [{"i": i} for i in range(25)]
    persisted = build_persisted_diagnostics(
        diagnostics=diagnostics,
        template_renderer_summary={"skipped_ratio": 0.5},
        text_qa={"ok": True},
        strict_blockers=[{"code": "strict_x", "message": "bad"}],
    )
    assert len(persisted) == 20
    statuses = [item.get("status") for item in persisted if isinstance(item, dict)]
    assert "template_renderer_summary" in statuses
    assert "text_qa_summary" in statuses
    assert "strict_quality_gate_failed" in statuses


def test_build_strict_failure_detail_limits_items_and_length():
    blockers = [{"code": f"c{i}", "message": "m" * 100} for i in range(20)]
    detail = build_strict_failure_detail(blockers, max_items=3, max_len=80)
    assert "c0:" in detail
    assert "c3:" not in detail
    assert len(detail) <= 80

