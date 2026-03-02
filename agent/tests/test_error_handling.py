"""
测试用例: P0 — 后端标准化错误处理

覆盖范围:
- 422 Validation Error 返回标准 JSON 信封
- HTTPException 返回标准 JSON 信封
- 未处理异常返回 500 且不泄露堆栈信息
"""

import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


def _create_app_with_handlers() -> FastAPI:
    """创建带全局异常处理器的测试 app."""
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err.get("loc", []))
            errors.append({"field": loc, "message": err.get("msg", "")})
        return JSONResponse(
            status_code=422,
            content={"error": "Validation failed", "details": errors},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    class TestBody(BaseModel):
        name: str = Field(..., min_length=1, max_length=10)
        age: int = Field(..., ge=0)

    @app.post("/test-validation")
    async def test_validation(body: TestBody):
        return {"ok": True}

    @app.get("/test-http-error")
    async def test_http_error():
        raise HTTPException(status_code=404, detail="Resource not found")

    @app.get("/test-server-error")
    async def test_server_error():
        raise RuntimeError("Something broke internally")

    return app


class TestErrorHandling:
    """测试全局异常处理器."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _create_app_with_handlers()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_validation_error_returns_422_json(self):
        """TC-ERR-01: 校验错误应返回 422 + JSON 信封."""
        resp = self.client.post("/test-validation", json={"name": "", "age": 5})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "Validation failed"
        assert "details" in body
        assert isinstance(body["details"], list)
        assert len(body["details"]) > 0

    def test_validation_error_details_contain_field(self):
        """TC-ERR-02: 校验错误 details 应包含字段路径."""
        resp = self.client.post("/test-validation", json={"name": "ok", "age": -1})
        assert resp.status_code == 422
        details = resp.json()["details"]
        fields = [d["field"] for d in details]
        assert any("age" in f for f in fields)

    def test_missing_required_field(self):
        """TC-ERR-03: 缺少必填字段应返回 422."""
        resp = self.client.post("/test-validation", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "Validation failed"

    def test_http_exception_returns_consistent_envelope(self):
        """TC-ERR-04: HTTPException 应返回一致的 JSON 信封."""
        resp = self.client.get("/test-http-error")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "Resource not found"
        # 不应有 "detail" 键 (FastAPI 默认)
        assert "detail" not in body

    def test_unhandled_exception_returns_500_no_leak(self):
        """TC-ERR-05: 未处理异常应返回 500 且不泄露内部信息."""
        resp = self.client.get("/test-server-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] == "Internal server error"
        # 不应泄露堆栈信息
        assert "traceback" not in str(body).lower()
        assert "RuntimeError" not in str(body)
        assert "Something broke" not in str(body)

    def test_invalid_json_body(self):
        """TC-ERR-06: 无效 JSON body 应返回 422."""
        resp = self.client.post(
            "/test-validation",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422
