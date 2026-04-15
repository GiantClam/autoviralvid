import pytest

from src.ppt_service_v2 import PPTService
from src.schemas.ppt import VideoRenderConfig


@pytest.mark.asyncio
async def test_ppt_service_start_video_render_from_pptx(monkeypatch):
    import src.lambda_renderer as lambda_renderer
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    async def _fake_upload(_data, key, content_type="image/png", bucket=None):
        _ = content_type, bucket
        return f"https://example.com/{key}"

    async def _fake_start_render(slides, config, webhook_url=None, prefer_local=False):
        _ = config, webhook_url, prefer_local
        assert isinstance(slides, list) and len(slides) == 1
        assert str(slides[0].get("imageUrl", "")).startswith("https://example.com/")
        return {
            "render_id": "render_pptx_case_1",
            "video_url": "https://example.com/video.mp4",
            "mode": "local",
            "cost": 0,
        }

    monkeypatch.setattr(
        pptx_rasterizer,
        "rasterize_pptx_bytes_to_png_bytes",
        lambda _pptx: [b"png-bytes"],
    )
    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)
    monkeypatch.setattr(lambda_renderer, "start_render", _fake_start_render)

    service = PPTService()

    async def _fake_read_binary(_source: str) -> bytes:
        return b"pptx-bytes"

    monkeypatch.setattr(service, "_read_binary_source", _fake_read_binary)

    job = await service.start_video_render(
        slides=[],
        config=VideoRenderConfig(),
        pptx_url="https://example.com/presentation.pptx",
        audio_urls=[],
    )

    assert job.id == "render_pptx_case_1"
    assert job.status == "done"
    status = await service.get_render_status(job.id)
    assert status.get("status") == "done"
    download = await service.get_download_url(job.id)
    assert download.get("output_url") == "https://example.com/video.mp4"
