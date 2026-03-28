import pytest

from src.ppt_quality_gate import QualityIssue, QualityResult
import src.ppt_service as ppt_service
from src.schemas.ppt import ExportRequest, SlideContent, SlideElement
from src.ppt_service import PPTService


@pytest.mark.asyncio
async def test_quality_gate_triggers_slide_retry_and_persists_diagnostics(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.ppt_quality_gate as quality_gate
    import src.ppt_service as ppt_service
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_PARTIAL_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "3")

    # avoid test delays from retry backoff
    async def _fake_sleep(_seconds):
        return None

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)

    export_calls = []

    def _fake_export(**kwargs):
        export_calls.append(kwargs)
        return {
            "pptx_bytes": b"fake-pptx",
            "generator_meta": {"render_slides": 1},
            "render_spec": {
                "mode": "minimax_presentation",
                "slides": [{"slide_id": "s1", "page_number": 1, "slide_type": "grid_3"}],
            },
            "input_payload": {
                "slides": [
                    {
                        "slide_id": "s1",
                        "title": "Intro",
                        "elements": [{"type": "text", "content": "hello"}],
                    }
                ]
            },
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(
        pptx_rasterizer,
        "rasterize_pptx_bytes_to_png_bytes",
        lambda _pptx: [],
    )

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    validate_calls = {"count": 0}

    def _fake_validate_deck(_slides):
        validate_calls["count"] += 1
        if validate_calls["count"] == 1:
            return QualityResult(
                ok=False,
                issues=[
                    QualityIssue(
                        slide_id="s1",
                        code="placeholder_pollution",
                        message="placeholder",
                        retry_scope="slide",
                        retry_target_ids=["s1"],
                    )
                ],
            )
        return QualityResult(ok=True, issues=[])

    monkeypatch.setattr(quality_gate, "validate_deck", _fake_validate_deck)

    persisted = []
    monkeypatch.setattr(ppt_service, "_persist_ppt_retry_diagnostic", lambda payload: persisted.append(payload))

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Intro",
                elements=[SlideElement(type="text", content="hello", block_id="b1")],
                narration="hello",
                duration=120,
            )
        ],
        title="Deck",
        author="AutoViralVid",
        retry_scope="deck",
        target_slide_ids=[],
    )

    svc = PPTService()
    result = await svc.export_pptx(req)

    assert result["attempts"] == 2
    assert result["retry_scope"] == "slide"
    assert len(export_calls) == 2
    assert export_calls[1]["retry_scope"] == "slide"
    assert "failure_code" in str(export_calls[1]["retry_hint"])
    statuses = [row["status"] for row in persisted]
    assert "quality_gate_failed" in statuses
    assert "success" in statuses


def test_build_image_video_slides_presigns_r2_public_urls(monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE", "https://s.autoviralvid.com")
    monkeypatch.setenv("R2_BUCKET", "autoviralvid")

    class _FakeR2:
        def generate_presigned_url(self, method, Params, ExpiresIn):
            assert method == "get_object"
            assert Params["Bucket"] == "autoviralvid"
            assert Params["Key"] == "projects/p1/slides/slide_001.png"
            assert ExpiresIn >= 3600
            return "https://signed.example.com/slide_001.png"

    monkeypatch.setattr("src.r2.get_r2_client", lambda: _FakeR2())

    slides = ppt_service._build_image_video_slides(
        ["https://s.autoviralvid.com/projects/p1/slides/slide_001.png"],
        [{"duration": 6}],
    )

    assert len(slides) == 1
    assert slides[0]["imageUrl"] == "https://signed.example.com/slide_001.png"


def test_presign_allows_known_domain_without_r2_public_base(monkeypatch):
    monkeypatch.delenv("R2_PUBLIC_BASE", raising=False)
    monkeypatch.delenv("R2_PUBLIC_HOSTS", raising=False)
    monkeypatch.setenv("R2_BUCKET", "autoviralvid")

    class _FakeR2:
        def generate_presigned_url(self, method, Params, ExpiresIn):
            assert method == "get_object"
            assert Params["Bucket"] == "autoviralvid"
            assert Params["Key"] == "projects/p2/slides/slide_002.png"
            assert ExpiresIn >= 3600
            return "https://signed.example.com/slide_002.png"

    monkeypatch.setattr("src.r2.get_r2_client", lambda: _FakeR2())

    signed = ppt_service._presign_r2_get_url_if_needed(
        "https://s.autoviralvid.com/projects/p2/slides/slide_002.png"
    )
    assert signed == "https://signed.example.com/slide_002.png"


def test_presign_skips_existing_signed_url(monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE", "https://s.autoviralvid.com")

    class _FakeR2:
        def generate_presigned_url(self, method, Params, ExpiresIn):  # pragma: no cover
            raise AssertionError("should not be called for already signed URL")

    monkeypatch.setattr("src.r2.get_r2_client", lambda: _FakeR2())

    existing = (
        "https://s.autoviralvid.com/projects/p3/slides/slide_003.png?"
        "X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc123"
    )
    assert ppt_service._presign_r2_get_url_if_needed(existing) == existing


@pytest.mark.asyncio
async def test_schema_invalid_retries_failed_slide_only(monkeypatch):
    import src.minimax_exporter as minimax_exporter
    import src.pptx_rasterizer as pptx_rasterizer
    import src.r2 as r2
    from src.minimax_exporter import MiniMaxExportError
    from src.ppt_failure_classifier import classify_failure

    monkeypatch.setenv("PPT_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_PARTIAL_RETRY_ENABLED", "true")
    monkeypatch.setenv("PPT_RETRY_MAX_ATTEMPTS", "2")

    async def _fake_sleep(_seconds):
        return None

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)

    calls = []

    def _fake_export(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise MiniMaxExportError(
                message="schema invalid",
                classification=classify_failure("schema invalid"),
                detail="Render contract invalid: slides[0].blocks[1].content is required",
            )
        return {
            "pptx_bytes": b"ok",
            "generator_meta": {"render_slides": 1},
            "render_spec": {"mode": "minimax_presentation", "slides": [{"slide_id": "s1", "slide_type": "split_2"}]},
            "input_payload": {
                "slides": [
                    {"slide_id": "s1", "title": "Intro", "elements": [{"type": "text", "content": "hello"}]}
                ]
            },
        }

    monkeypatch.setattr(minimax_exporter, "export_minimax_pptx", _fake_export)
    monkeypatch.setattr(pptx_rasterizer, "rasterize_pptx_bytes_to_png_bytes", lambda _pptx: [])

    async def _fake_upload(_bytes, key, content_type):
        return f"https://example.com/{key}"

    monkeypatch.setattr(r2, "upload_bytes_to_r2", _fake_upload)

    req = ExportRequest(
        slides=[
            SlideContent(
                slide_id="s1",
                title="Intro",
                elements=[SlideElement(type="text", content="hello", block_id="b1")],
                narration="hello",
                duration=120,
            )
        ],
        title="Deck",
        author="AutoViralVid",
        retry_scope="deck",
    )

    result = await PPTService().export_pptx(req)

    assert result["attempts"] == 2
    assert len(calls) == 2
    assert calls[1]["retry_scope"] == "slide"
    assert calls[1]["target_slide_ids"] == ["s1"]
