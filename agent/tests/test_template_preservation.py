from src.minimax_exporter import build_payload


def test_no_local_style_override_when_original_mode_enabled():
    p = build_payload(
        slides=[],
        title="t",
        author="a",
        original_style=True,
        disable_local_style_rewrite=True,
    )
    assert p["disable_local_style_rewrite"] is True
    assert p["original_style"] is True

