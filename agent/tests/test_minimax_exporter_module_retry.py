from src.minimax_exporter import export_minimax_pptx


def _sample_slide() -> dict:
    return {
        "slide_id": "s1",
        "title": "Intro",
        "slide_type": "content",
        "layout_grid": "split_2",
        "elements": [{"type": "text", "content": "hello"}],
        "blocks": [
            {"block_type": "title", "card_id": "title", "content": "Intro"},
            {"block_type": "body", "card_id": "left", "content": "hello"},
        ],
    }


def test_exporter_always_uses_drawingml_engine():
    result = export_minimax_pptx(
        slides=[_sample_slide()],
        title="Deck",
        author="AutoViralVid",
        retry_scope="deck",
        target_slide_ids=[],
        generator_mode="official",
        timeout=30,
    )

    assert result["pptx_bytes"].startswith(b"PK")
    assert result["generator_mode"] == "drawingml"
    assert result["render_channel"] == "local"
    assert result["is_full_deck"] is True
    assert result["generator_meta"].get("engine") == "drawingml_native"
    assert result["generator_meta"].get("render_slides") == 1


def test_exporter_marks_remote_channel_as_local_fallback():
    result = export_minimax_pptx(
        slides=[_sample_slide()],
        title="Deck",
        author="AutoViralVid",
        render_channel="remote",
        generator_mode="official",
        timeout=30,
    )

    meta = result.get("generator_meta") or {}
    assert meta.get("channel_fallback_used") is True
    assert "drawingml export currently runs in local mode" in str(
        meta.get("channel_fallback_reason") or ""
    )
    payload = result.get("input_payload") or {}
    assert payload.get("render_channel") == "local"
    assert payload.get("requested_render_channel") == "remote"


def test_exporter_reports_svg_source_stats():
    slide = _sample_slide()
    slide["svg_markup"] = (
        '<svg width="960" height="540" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="40" y="40" width="320" height="120" fill="#3366FF" />'
        "</svg>"
    )
    result = export_minimax_pptx(
        slides=[slide, _sample_slide()],
        title="Deck",
        author="AutoViralVid",
        generator_mode="official",
        timeout=30,
    )
    meta = result.get("generator_meta") or {}
    assert meta.get("provided_svg_count") == 1
    assert meta.get("templated_svg_count") == 1


def test_exporter_repairs_invalid_provided_svg_and_still_exports():
    broken = _sample_slide()
    broken["svg_markup"] = "<svg><g><text>broken"
    result = export_minimax_pptx(
        slides=[broken],
        title="Deck",
        author="AutoViralVid",
        generator_mode="official",
        timeout=30,
    )
    meta = result.get("generator_meta") or {}
    assert result["pptx_bytes"].startswith(b"PK")
    assert meta.get("provided_svg_count") == 1
    assert meta.get("repaired_svg_count") == 1
    assert int(meta.get("invalid_svg_count") or 0) >= 1
    assert meta.get("templated_svg_count") == 1


def test_exporter_enables_notes_when_slide_contains_narration():
    slide = _sample_slide()
    slide["narration"] = "Narration text for note page."
    result = export_minimax_pptx(
        slides=[slide],
        title="Deck",
        author="AutoViralVid",
        generator_mode="official",
        timeout=30,
    )
    meta = result.get("generator_meta") or {}
    assert result["pptx_bytes"].startswith(b"PK")
    assert meta.get("notes_slide_count") == 1
