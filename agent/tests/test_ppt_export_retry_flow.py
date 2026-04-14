from pathlib import Path

import pytest

from src.ppt_service_v2 import PPTService, _resolve_export_channel
from src.schemas.ppt import ExportRequest, SlideContent, SlideElement


@pytest.mark.asyncio
async def test_export_pptx_materializes_bytes_to_output(monkeypatch, tmp_path):
    def _fake_export(**_kwargs):
        return {"pptx_bytes": b"pptx-bytes", "slide_image_urls": []}

    monkeypatch.setattr("src.ppt_service_v2.export_minimax_pptx", _fake_export)

    svc = PPTService()
    svc.output_base = tmp_path

    req = ExportRequest(
        slides=[
            SlideContent(
                title="Intro",
                elements=[SlideElement(type="text", content="hello")],
            )
        ],
        title="Deck",
    )

    out = await svc.export_pptx(req)

    output_pptx = Path(str(out.get("output_pptx") or ""))
    assert output_pptx.exists()
    assert output_pptx.read_bytes() == b"pptx-bytes"


def test_resolve_export_channel_disables_remote():
    assert _resolve_export_channel("local") == "local"
    with pytest.raises(ValueError, match="remote channel is disabled"):
        _resolve_export_channel("remote")
