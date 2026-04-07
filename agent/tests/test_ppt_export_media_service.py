import pytest

from src.ppt_export_media_service import PPTExportMediaService


@pytest.mark.asyncio
async def test_media_service_uses_png_upload_and_builds_image_slideshow():
    svc = PPTExportMediaService()

    async def _upload(_bytes, key, content_type):
        assert content_type == "image/png"
        return f"https://example.com/{key}"

    out = await svc.build_media_outputs(
        project_id="p1",
        export_pptx_bytes=b"pptx",
        initial_png_bytes_list=[b"a", b"b"],
        route_policy_force_rasterization=False,
        render_spec={},
        slides_data=[{"slide_id": "s1"}],
        rasterize_pptx_bytes_to_png_bytes=lambda _pptx: [],
        upload_bytes_to_r2=_upload,
        build_image_video_slides=lambda urls, _slides: [{"imageUrl": u} for u in urls],
        logger_warning=lambda _msg, _exc: None,
    )
    assert len(out.slide_image_urls) == 2
    assert out.video_mode == "ppt_image_slideshow"
    assert isinstance(out.video_slides, list)
    assert out.video_slide_count == 2


@pytest.mark.asyncio
async def test_media_service_falls_back_to_render_spec_video_slides():
    svc = PPTExportMediaService()
    render_spec = {"mode": "minimax_presentation", "slides": [{"slide_id": "s1"}]}

    async def _upload(_bytes, key, content_type):  # pragma: no cover
        _ = (key, content_type)
        return f"https://example.com/{_bytes}"

    out = await svc.build_media_outputs(
        project_id="p2",
        export_pptx_bytes=b"pptx",
        initial_png_bytes_list=[],
        route_policy_force_rasterization=False,
        render_spec=render_spec,
        slides_data=[],
        rasterize_pptx_bytes_to_png_bytes=lambda _pptx: [],
        upload_bytes_to_r2=_upload,
        build_image_video_slides=lambda _urls, _slides: [],
        logger_warning=lambda _msg, _exc: None,
    )
    assert out.slide_image_urls == []
    assert out.video_mode == "minimax_presentation"
    assert out.video_slides == [{"slide_id": "s1"}]
    assert out.video_slide_count == 1


@pytest.mark.asyncio
async def test_media_service_handles_rasterize_failure_gracefully():
    svc = PPTExportMediaService()
    warned = {"v": False}

    def _rasterize(_pptx):
        raise RuntimeError("rasterize failed")

    out = await svc.build_media_outputs(
        project_id="p3",
        export_pptx_bytes=b"pptx",
        initial_png_bytes_list=[],
        route_policy_force_rasterization=True,
        render_spec={},
        slides_data=[],
        rasterize_pptx_bytes_to_png_bytes=_rasterize,
        upload_bytes_to_r2=lambda **_kwargs: None,  # pragma: no cover
        build_image_video_slides=lambda _urls, _slides: [],
        logger_warning=lambda _msg, _exc: warned.__setitem__("v", True),
    )
    assert warned["v"] is True
    assert out.slide_image_urls == []
    assert out.video_mode is None

