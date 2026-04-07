from src.ppt_export_report_service import PPTExportReportService


def test_build_observability_report_includes_core_fields():
    svc = PPTExportReportService()
    report = svc.build_observability_report(
        route_mode="standard",
        quality_profile="balanced",
        strict_quality_mode=True,
        attempts=2,
        retry_count=1,
        layout_homogeneous_count=1,
        slide_count_for_incidence=4,
        generator_mode="official",
        export_channel="inline",
        has_visual_qa=True,
        has_text_qa=True,
        has_quality_score=True,
        visual_professional_score={"visual_avg_score": 78.0},
        issue_codes=["layout_homogeneous", "placeholder_text"],
        quality_score={"score": 82.0, "threshold": 75.0},
        template_renderer_summary={"skipped_ratio": 0.2},
        text_qa={"issue_codes": ["markitdown_placeholder_text"]},
    )
    assert report["route_mode"] == "standard"
    assert report["strict_quality_mode"] is True
    assert report["retry_count"] == 1
    assert report["layout_homogeneous_incidence"] == 0.25
    assert report["weighted_quality_score"] == 82.0
    assert report["weighted_quality_threshold"] == 75.0
    assert "markitdown_placeholder_text" in report["issue_codes"]
    assert report["template_renderer_summary"]["skipped_ratio"] == 0.2


def test_build_observability_report_merges_text_issue_codes_and_dedupes():
    svc = PPTExportReportService()
    report = svc.build_observability_report(
        route_mode="fast",
        quality_profile="balanced",
        strict_quality_mode=False,
        attempts=1,
        retry_count=0,
        layout_homogeneous_count=0,
        slide_count_for_incidence=1,
        generator_mode="template_edit",
        export_channel="inline",
        has_visual_qa=False,
        has_text_qa=True,
        has_quality_score=False,
        visual_professional_score=None,
        issue_codes=["placeholder_text"],
        quality_score=None,
        template_renderer_summary=None,
        text_qa={"issue_codes": ["placeholder_text", "markitdown_placeholder_text"]},
    )
    assert report["issue_codes"] == ["markitdown_placeholder_text", "placeholder_text"]


def test_build_observability_report_without_optional_sections():
    svc = PPTExportReportService()
    report = svc.build_observability_report(
        route_mode="fast",
        quality_profile="balanced",
        strict_quality_mode=False,
        attempts=1,
        retry_count=0,
        layout_homogeneous_count=0,
        slide_count_for_incidence=1,
        generator_mode="official",
        export_channel="inline",
        has_visual_qa=False,
        has_text_qa=False,
        has_quality_score=False,
        visual_professional_score=None,
        issue_codes=[],
        quality_score=None,
        template_renderer_summary=None,
        text_qa=None,
    )
    assert "weighted_quality_score" not in report
    assert "template_renderer_summary" not in report
    assert "visual_professional_score" not in report
    assert "text_qa" not in report
