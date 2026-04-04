from src.ppt_export_pipeline import ExportPipelineTimeline


def test_export_pipeline_timeline_stage_context_records_duration():
    timeline = ExportPipelineTimeline()
    with timeline.stage("prepare_input", {"slide_count": 3}):
        _ = 1 + 1
    data = timeline.to_dict()
    assert data["version"] == "v1"
    assert len(data["stages"]) == 1
    row = data["stages"][0]
    assert row["stage"] == "prepare_input"
    assert row["ok"] is True
    assert row["meta"]["slide_count"] == 3
    assert row["duration_ms"] >= 0


def test_export_pipeline_timeline_record_supports_instant_events():
    timeline = ExportPipelineTimeline()
    timeline.record(stage="persist", ok=True, meta={"status": "success"})
    data = timeline.to_dict()
    assert len(data["stages"]) == 1
    row = data["stages"][0]
    assert row["stage"] == "persist"
    assert row["ok"] is True
    assert row["meta"]["status"] == "success"
