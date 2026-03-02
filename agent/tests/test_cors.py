"""
测试用例: P0 — CORS 锁定

覆盖范围:
- 允许的 origin 可以正常访问
- 未配置的 origin 被拒绝
- preflight OPTIONS 请求正确响应
"""

import os
import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware


def _create_cors_app(cors_origin: str = "http://localhost:3000") -> FastAPI:
    """创建带 CORS 中间件的测试 app."""
    _cors_raw = cors_origin
    _cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    if not _cors_origins:
        _cors_origins = ["http://localhost:3000"]

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
        expose_headers=["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    return app


class TestCORS:
    """测试 CORS 配置."""

    def test_allowed_origin(self):
        """TC-CORS-01: 允许的 origin 应包含 CORS 头."""
        app = _create_cors_app("http://localhost:3000")
        client = TestClient(app)
        resp = client.get("/test", headers={"Origin": "http://localhost:3000"})
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_disallowed_origin(self):
        """TC-CORS-02: 不允许的 origin 不应包含 CORS 头."""
        app = _create_cors_app("http://localhost:3000")
        client = TestClient(app)
        resp = client.get("/test", headers={"Origin": "http://evil.com"})
        assert resp.status_code == 200  # 请求本身仍通过
        # 但不应有 access-control-allow-origin 头
        assert resp.headers.get("access-control-allow-origin") != "http://evil.com"

    def test_multiple_origins_supported(self):
        """TC-CORS-03: 逗号分隔的多个 origin 应都被允许."""
        app = _create_cors_app("http://localhost:3000,https://autoviralvid.com")
        client = TestClient(app)

        resp1 = client.get("/test", headers={"Origin": "http://localhost:3000"})
        assert resp1.headers.get("access-control-allow-origin") == "http://localhost:3000"

        resp2 = client.get("/test", headers={"Origin": "https://autoviralvid.com"})
        assert resp2.headers.get("access-control-allow-origin") == "https://autoviralvid.com"

    def test_preflight_options(self):
        """TC-CORS-04: OPTIONS preflight 应返回正确的 CORS 头."""
        app = _create_cors_app("http://localhost:3000")
        client = TestClient(app)
        resp = client.options("/test", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        })
        assert resp.status_code == 200
        assert "access-control-allow-methods" in resp.headers

    def test_no_wildcard_by_default(self):
        """TC-CORS-05: 默认不使用 * 通配符."""
        app = _create_cors_app("http://localhost:3000")
        client = TestClient(app)
        resp = client.get("/test", headers={"Origin": "http://random.com"})
        assert resp.headers.get("access-control-allow-origin") != "*"

    def test_credentials_allowed(self):
        """TC-CORS-06: 应支持 credentials (cookie)."""
        app = _create_cors_app("http://localhost:3000")
        client = TestClient(app)
        resp = client.get("/test", headers={"Origin": "http://localhost:3000"})
        assert resp.headers.get("access-control-allow-credentials") == "true"
