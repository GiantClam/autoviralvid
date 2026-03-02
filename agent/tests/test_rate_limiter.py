"""
测试用例: P1 — API 限流 (RateLimitMiddleware)

覆盖范围:
- 正常请求通过并返回限流头
- 超出限制返回 429
- 健康检查端点跳过限流
- 清理机制正常工作
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.testclient import TestClient
from fastapi import FastAPI

from src.rate_limiter import RateLimitMiddleware


# ---------------------------------------------------------------------------
# Fixture: 创建一个带限流的测试 app
# ---------------------------------------------------------------------------

def _create_app(rpm: int = 5) -> FastAPI:
    """创建一个简单的 FastAPI app 用于测试限流."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rpm=rpm)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.post("/webhook/runninghub")
    async def webhook():
        return {"ok": True}

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRateLimiter:
    """测试限流中间件."""

    def test_normal_request_passes(self):
        """TC-RL-01: 正常请求应通过并包含限流头."""
        app = _create_app(rpm=10)
        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert resp.headers["X-RateLimit-Limit"] == "10"
        assert "X-RateLimit-Remaining" in resp.headers

    def test_rate_limit_exceeded_returns_429(self):
        """TC-RL-02: 超过 RPM 限制应返回 429."""
        app = _create_app(rpm=3)
        client = TestClient(app)

        # 前 3 个请求应该通过
        for i in range(3):
            resp = client.get("/test")
            assert resp.status_code == 200, f"Request {i+1} should pass"

        # 第 4 个请求应被限流
        resp = client.get("/test")
        assert resp.status_code == 429
        body = resp.json()
        assert "error" in body
        assert "Retry-After" in resp.headers

    def test_healthz_skips_rate_limit(self):
        """TC-RL-03: /healthz 应跳过限流."""
        app = _create_app(rpm=1)
        client = TestClient(app)

        # 用完配额
        client.get("/test")

        # healthz 不受限
        resp = client.get("/healthz")
        assert resp.status_code == 200
        # 不应包含限流头
        assert "X-RateLimit-Limit" not in resp.headers

    def test_webhook_skips_rate_limit(self):
        """TC-RL-04: /webhook/runninghub 应跳过限流."""
        app = _create_app(rpm=1)
        client = TestClient(app)

        # 用完配额
        client.get("/test")

        # webhook 不受限
        resp = client.post("/webhook/runninghub")
        assert resp.status_code == 200

    def test_remaining_decreases(self):
        """TC-RL-05: 每个请求后 remaining 应递减."""
        app = _create_app(rpm=5)
        client = TestClient(app)

        resp1 = client.get("/test")
        remaining1 = int(resp1.headers["X-RateLimit-Remaining"])

        resp2 = client.get("/test")
        remaining2 = int(resp2.headers["X-RateLimit-Remaining"])

        assert remaining2 < remaining1

    def test_429_includes_retry_after(self):
        """TC-RL-06: 429 响应应包含 Retry-After 头."""
        app = _create_app(rpm=1)
        client = TestClient(app)

        client.get("/test")  # 用完配额
        resp = client.get("/test")  # 被限流

        assert resp.status_code == 429
        retry_after = int(resp.headers.get("Retry-After", "0"))
        assert retry_after > 0
