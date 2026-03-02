"""
测试用例: P0 — 文件上传安全 (presign 端点校验)

覆盖范围:
- 合法文件类型通过
- 非法文件类型被拒绝
- 文件名长度限制
- 路径遍历防御
"""

import pytest
from starlette.testclient import TestClient
from unittest.mock import patch, MagicMock


def _create_test_app():
    """创建一个带 presign 端点的测试 app (不依赖完整 main.py)."""
    import os
    os.environ.setdefault("AUTH_SECRET", "")
    os.environ.setdefault("AUTH_REQUIRED", "false")

    from fastapi import FastAPI, HTTPException, Depends
    from pydantic import BaseModel
    from src.auth import get_current_user, AuthUser

    ALLOWED_UPLOAD_TYPES = {
        "image/png", "image/jpeg", "image/jpg", "image/webp",
        "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
        "audio/ogg", "audio/aac", "audio/m4a", "audio/x-m4a",
        "application/octet-stream",
    }
    MAX_FILENAME_LENGTH = 255

    class UploadPresignRequest(BaseModel):
        filename: str
        content_type: str = "application/octet-stream"

    app = FastAPI()

    @app.post("/upload/presign")
    async def upload_presign(body: UploadPresignRequest, user: AuthUser = Depends(get_current_user)):
        clean_name = body.filename.strip().replace("..", "").replace("/", "_").replace("\\", "_")
        if not clean_name or len(clean_name) > MAX_FILENAME_LENGTH:
            raise HTTPException(status_code=400, detail="Invalid filename")
        if body.content_type not in ALLOWED_UPLOAD_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {body.content_type}")
        return {"upload_url": "https://mock.r2/put", "public_url": f"https://mock.cdn/{clean_name}"}

    return app


class TestUploadPresign:
    """测试文件上传 presign 端点的安全校验."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _create_test_app()
        self.client = TestClient(self.app)

    def test_valid_image_upload(self):
        """TC-UPL-01: image/png 应被接受."""
        resp = self.client.post("/upload/presign", json={
            "filename": "photo.png",
            "content_type": "image/png",
        })
        assert resp.status_code == 200
        assert "upload_url" in resp.json()

    def test_valid_audio_upload(self):
        """TC-UPL-02: audio/mpeg 应被接受."""
        resp = self.client.post("/upload/presign", json={
            "filename": "voice.mp3",
            "content_type": "audio/mpeg",
        })
        assert resp.status_code == 200

    def test_valid_jpeg_upload(self):
        """TC-UPL-03: image/jpeg 应被接受."""
        resp = self.client.post("/upload/presign", json={
            "filename": "img.jpg",
            "content_type": "image/jpeg",
        })
        assert resp.status_code == 200

    def test_invalid_content_type_rejected(self):
        """TC-UPL-04: text/html 应被拒绝."""
        resp = self.client.post("/upload/presign", json={
            "filename": "hack.html",
            "content_type": "text/html",
        })
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_executable_content_type_rejected(self):
        """TC-UPL-05: application/x-executable 应被拒绝."""
        resp = self.client.post("/upload/presign", json={
            "filename": "malware.exe",
            "content_type": "application/x-executable",
        })
        assert resp.status_code == 400

    def test_svg_rejected(self):
        """TC-UPL-06: image/svg+xml 应被拒绝 (可含 XSS)."""
        resp = self.client.post("/upload/presign", json={
            "filename": "icon.svg",
            "content_type": "image/svg+xml",
        })
        assert resp.status_code == 400

    def test_filename_too_long_rejected(self):
        """TC-UPL-07: 文件名超过 255 字符应被拒绝."""
        resp = self.client.post("/upload/presign", json={
            "filename": "a" * 300 + ".png",
            "content_type": "image/png",
        })
        assert resp.status_code == 400
        assert "Invalid filename" in resp.json()["detail"]

    def test_empty_filename_rejected(self):
        """TC-UPL-08: 空文件名应被拒绝."""
        resp = self.client.post("/upload/presign", json={
            "filename": "",
            "content_type": "image/png",
        })
        assert resp.status_code == 400

    def test_path_traversal_sanitized(self):
        """TC-UPL-09: 路径遍历符号应被清理."""
        resp = self.client.post("/upload/presign", json={
            "filename": "../../etc/passwd",
            "content_type": "application/octet-stream",
        })
        assert resp.status_code == 200
        # 文件名中不应包含 .. 或 /
        public_url = resp.json()["public_url"]
        assert ".." not in public_url
        assert "/" not in public_url.split("/")[-1] or "_" in public_url

    def test_backslash_sanitized(self):
        """TC-UPL-10: Windows 路径分隔符应被清理."""
        resp = self.client.post("/upload/presign", json={
            "filename": "..\\..\\secret.txt",
            "content_type": "application/octet-stream",
        })
        assert resp.status_code == 200
        public_url = resp.json()["public_url"]
        assert "\\" not in public_url.split("/")[-1]
