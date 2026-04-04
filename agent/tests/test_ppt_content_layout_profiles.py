from __future__ import annotations

from src.ppt_content_layout_profiles import build_content_layout_plan


def test_content_layout_plan_prefers_comparison_archetype_for_vs_signal():
    plan = build_content_layout_plan(
        title="传统方案 vs 智能代理方案",
        evidence=["人工交接多", "响应链路长", "自动编排提效 80%", "上线周期缩短 60%"],
        visual_anchor="text",
        data_elements=["comparison"],
        layout_hint="split_2",
    )

    assert plan["archetype"] == "comparison_2col"
    assert plan["block_flags"]["comparison"] is True
    assert "comparison_cards_light" in (plan["template_whitelist"] or [])


def test_content_layout_plan_prefers_dashboard_for_metric_signal():
    plan = build_content_layout_plan(
        title="季度 KPI 与转化趋势",
        evidence=["ROI 132%", "转化率提升 28%", "获客成本下降 17%", "渠道贡献持续上升"],
        visual_anchor="chart",
        data_elements=["chart", "kpi", "table"],
        layout_hint="grid_3",
    )

    assert plan["archetype"] in {"dashboard_kpi_4", "chart_single_focus", "chart_dual_compare"}
    assert plan["block_flags"]["chart"] is True
    assert plan["block_flags"]["kpi"] is True
    assert "kpi_dashboard_dark" in (plan["template_whitelist"] or [])
