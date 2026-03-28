from src.minimax_exporter import build_payload


def test_exporter_default_mode_is_official():
    payload = build_payload(slides=[], title="t", author="a")
    assert payload.get("generator_mode") == "official"
    assert payload.get("render_channel") == "local"
    assert payload.get("visual_priority") is True
    assert payload.get("visual_density") == "balanced"
    assert payload.get("constraint_hardness") == "minimal"
    assert payload.get("template_id")
    assert payload.get("skill_profile")
    assert payload.get("schema_profile")
    assert payload.get("quality_profile")


def test_original_style_forces_disable_local_rewrite():
    payload = build_payload(
        slides=[{"title": "灵创智能"}],
        title="灵创智能",
        author="a",
        original_style=True,
        disable_local_style_rewrite=False,
    )
    assert payload["original_style"] is True
    assert payload["disable_local_style_rewrite"] is True


def test_exporter_channel_auto_defaults_to_local():
    payload = build_payload(
        slides=[{"title": "灵创智能"}],
        title="灵创智能",
        author="a",
        render_channel="auto",
    )
    assert payload["render_channel"] == "local"
