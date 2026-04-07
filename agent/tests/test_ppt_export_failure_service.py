from src.ppt_export_failure_service import PPTExportFailureService


def _make_service(retry_rows, obs_rows):
    return PPTExportFailureService(
        persist_retry_diagnostic=lambda payload: retry_rows.append(payload),
        persist_observability_report=lambda payload: obs_rows.append(payload),
        utc_now=lambda: "2026-01-01T00:00:00Z",
    )


def test_build_retry_target_ids_uses_block_targets_for_block_scope():
    retry_rows = []
    obs_rows = []
    service = _make_service(retry_rows, obs_rows)

    assert service.build_retry_target_ids(
        retry_scope="block",
        target_slide_ids=["s1"],
        target_block_ids=["b1", "b2"],
    ) == ["b1", "b2"]
    assert service.build_retry_target_ids(
        retry_scope="deck",
        target_slide_ids=["s1", "s2"],
        target_block_ids=["b1"],
    ) == ["s1", "s2"]


def test_persist_retry_event_records_common_fields():
    retry_rows = []
    obs_rows = []
    service = _make_service(retry_rows, obs_rows)

    service.persist_retry_event(
        deck_id="deck-1",
        failure_code="schema_invalid",
        failure_detail="missing field",
        retry_scope="deck",
        target_slide_ids=["s1"],
        target_block_ids=["b1"],
        attempt=2,
        idempotency_key="idem-1",
        export_channel="inline",
        quality_profile="balanced",
        route_mode="standard",
        render_spec_version="v1",
        status="failed",
        quality_score=72.5,
        quality_score_threshold=80.0,
    )

    assert len(retry_rows) == 1
    row = retry_rows[0]
    assert row["deck_id"] == "deck-1"
    assert row["failure_code"] == "schema_invalid"
    assert row["retry_scope"] == "deck"
    assert row["retry_target_ids"] == ["s1"]
    assert row["status"] == "failed"
    assert row["quality_score"] == 72.5
    assert row["quality_score_threshold"] == 80.0
    assert row["created_at"] == "2026-01-01T00:00:00Z"


def test_persist_failed_observability_limits_diagnostics_to_last_20():
    retry_rows = []
    obs_rows = []
    service = _make_service(retry_rows, obs_rows)
    diagnostics = [{"i": i} for i in range(30)]

    service.persist_failed_observability(
        deck_id="deck-2",
        failure_code="timeout",
        failure_detail="upstream timeout",
        route_mode="standard",
        quality_profile="balanced",
        attempts=3,
        export_channel="inline",
        generator_mode="official",
        diagnostics=diagnostics,
        quality_score=68.0,
        quality_score_threshold=75.0,
    )

    assert len(obs_rows) == 1
    row = obs_rows[0]
    assert row["status"] == "failed"
    assert row["failure_code"] == "timeout"
    assert len(row["diagnostics"]) == 20
    assert row["diagnostics"][0] == {"i": 10}
    assert row["quality_score"] == 68.0
    assert row["quality_score_threshold"] == 75.0


def test_persist_observability_event_supports_success_and_extra_fields():
    retry_rows = []
    obs_rows = []
    service = _make_service(retry_rows, obs_rows)

    service.persist_observability_event(
        deck_id="deck-3",
        status="success",
        failure_code=None,
        failure_detail=None,
        route_mode="fast",
        quality_profile="balanced",
        attempts=1,
        export_channel="inline",
        generator_mode="official",
        diagnostics=[],
        extra_fields={"alert_count": 2, "issue_codes": ["placeholder_text"]},
    )

    assert len(obs_rows) == 1
    row = obs_rows[0]
    assert row["status"] == "success"
    assert row["failure_code"] is None
    assert row["alert_count"] == 2
    assert row["issue_codes"] == ["placeholder_text"]
