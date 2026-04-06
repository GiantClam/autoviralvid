from src.minimax_exporter import export_minimax_pptx
from src.ppt_svg_renderer import render_slide_svg_markup, resolve_slide_svg_markup


def _simple_svg() -> str:
    return (
        '<svg width="960" height="540" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="40" y="40" width="320" height="120" fill="#3366FF" stroke="#112244"/>'
        "</svg>"
    )


def test_resolve_slide_svg_markup_prefers_direct_key():
    slide = {"render_path": "svg", "svg_markup": _simple_svg()}
    assert resolve_slide_svg_markup(slide).startswith("<svg")


def test_resolve_slide_svg_markup_accepts_xml_declaration():
    slide = {
        "svg_markup": '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg width="960" height="540" xmlns="http://www.w3.org/2000/svg"></svg>'
    }
    resolved = resolve_slide_svg_markup(slide)
    assert "<svg" in resolved


def test_render_slide_svg_markup_generates_layout_when_missing_svg():
    svg = render_slide_svg_markup(
        slide={
            "slide_type": "content",
            "title": "Route Strategy",
            "blocks": [
                {"block_type": "title", "content": "Route Strategy"},
                {"block_type": "body", "content": "Single DrawingML pipeline"},
            ],
        },
        slide_index=1,
        slide_count=5,
        deck_title="Deck",
        design_spec={
            "colors": {
                "primary": "1E3A5F",
                "secondary": "2F7BFF",
                "accent": "18E0D1",
                "bg": "0B1220",
                "text_primary": "F4F8FF",
                "text_secondary": "BFD0E8",
            }
        },
    )
    assert svg.startswith("<svg")
    assert "Route Strategy" in svg
    assert "Single DrawingML pipeline" in svg


def test_exporter_generates_drawingml_pptx_without_node_runtime():
    result = export_minimax_pptx(
        slides=[
            {
                "slide_id": "s1",
                "title": "SVG Slide",
                "slide_type": "content",
                "layout_grid": "split_2",
                "render_path": "svg",
                "svg_markup": _simple_svg(),
                "blocks": [],
            }
        ],
        title="Deck",
        author="AutoViralVid",
        generator_mode="official",
        timeout=30,
    )
    assert result["pptx_bytes"].startswith(b"PK")
    assert result["generator_meta"].get("engine") == "drawingml_native"
    assert result["generator_meta"].get("render_slides") == 1
    assert result["generator_mode"] == "drawingml"
