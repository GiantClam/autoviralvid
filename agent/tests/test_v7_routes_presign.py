from src.schemas.ppt_v7 import DialogueLine, SlideData
from src.v7_routes import (
    _build_image_video_slides,
    _presign_r2_get_url_if_needed,
    _presign_video_slides,
)


def test_v7_presign_r2_get_url_if_needed(monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE", "https://s.autoviralvid.com")
    monkeypatch.setenv("R2_BUCKET", "autoviralvid")

    class _FakeR2:
        def generate_presigned_url(self, method, Params, ExpiresIn):
            assert method == "get_object"
            assert Params["Bucket"] == "autoviralvid"
            assert ExpiresIn >= 3600
            return f"https://signed.example.com/{Params['Key']}"

    monkeypatch.setattr("src.r2.get_r2_client", lambda: _FakeR2())

    signed = _presign_r2_get_url_if_needed(
        "https://s.autoviralvid.com/projects/p1/slides/slide_001.png"
    )
    assert signed == "https://signed.example.com/projects/p1/slides/slide_001.png"


def test_v7_build_image_video_slides_presigns_image_and_audio(monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE", "https://s.autoviralvid.com")
    monkeypatch.setenv("R2_BUCKET", "autoviralvid")

    class _FakeR2:
        def generate_presigned_url(self, method, Params, ExpiresIn):
            return f"https://signed.example.com/{Params['Key']}"

    monkeypatch.setattr("src.r2.get_r2_client", lambda: _FakeR2())

    slide = SlideData(
        page_number=1,
        slide_type="cover",
        markdown="# Intro <mark>key</mark>",
        script=[DialogueLine(role="host", text="intro line")],
        narration_audio_url="https://s.autoviralvid.com/projects/p1/audio/a1.mp3",
        duration=6.0,
    )
    rows = _build_image_video_slides(
        ["https://s.autoviralvid.com/projects/p1/slides/slide_001.png"],
        [slide],
    )

    assert len(rows) == 1
    assert rows[0]["imageUrl"] == "https://signed.example.com/projects/p1/slides/slide_001.png"
    assert rows[0]["audioUrl"] == "https://signed.example.com/projects/p1/audio/a1.mp3"


def test_v7_presign_video_slides(monkeypatch):
    monkeypatch.setenv("R2_PUBLIC_BASE", "https://s.autoviralvid.com")

    class _FakeR2:
        def generate_presigned_url(self, method, Params, ExpiresIn):
            return f"https://signed.example.com/{Params['Key']}"

    monkeypatch.setattr("src.r2.get_r2_client", lambda: _FakeR2())

    rows = _presign_video_slides(
        [
            {
                "imageUrl": "https://s.autoviralvid.com/projects/p2/slides/slide_002.png",
                "audioUrl": "https://s.autoviralvid.com/projects/p2/audio/a2.mp3",
                "duration": 5.0,
            }
        ]
    )
    assert rows[0]["imageUrl"] == "https://signed.example.com/projects/p2/slides/slide_002.png"
    assert rows[0]["audioUrl"] == "https://signed.example.com/projects/p2/audio/a2.mp3"

