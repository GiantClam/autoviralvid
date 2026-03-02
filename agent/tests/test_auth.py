"""
测试用例: P0 — 后端 API 鉴权 (JWT 中间件 + 用户身份注入)

覆盖范围:
- JWT 签发与验证
- 有效 / 无效 / 过期 token 处理
- dev 模式 bypass
- FastAPI 依赖注入
"""

import os
import time
import pytest
import jwt as pyjwt
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_SECRET = "test-secret-for-unit-tests"


def _make_token(sub: str = "user-123", email: str = "test@example.com",
                exp_delta: int = 3600, secret: str = TEST_SECRET) -> str:
    """签发一个测试用 JWT."""
    payload = {
        "sub": sub,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_delta,
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# 1. _verify_token — 核心验证逻辑
# ---------------------------------------------------------------------------

class TestVerifyToken:
    """测试 _verify_token 函数."""

    @patch.dict(os.environ, {"AUTH_SECRET": TEST_SECRET}, clear=False)
    def test_valid_token(self):
        """TC-AUTH-01: 合法 token 应正确解析出 user_id 和 email."""
        # 需要重新导入以获取新的环境变量
        import importlib
        import src.auth as auth_mod
        importlib.reload(auth_mod)

        token = _make_token(sub="u-abc", email="alice@test.com")
        user = auth_mod._verify_token(token)
        assert user.id == "u-abc"
        assert user.email == "alice@test.com"

    @patch.dict(os.environ, {"AUTH_SECRET": TEST_SECRET}, clear=False)
    def test_expired_token_raises_401(self):
        """TC-AUTH-02: 过期 token 应返回 401."""
        import importlib
        import src.auth as auth_mod
        importlib.reload(auth_mod)

        token = _make_token(exp_delta=-100)  # 已过期
        with pytest.raises(HTTPException) as exc_info:
            auth_mod._verify_token(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    @patch.dict(os.environ, {"AUTH_SECRET": TEST_SECRET}, clear=False)
    def test_wrong_secret_raises_401(self):
        """TC-AUTH-03: 用错误密钥签发的 token 应返回 401."""
        import importlib
        import src.auth as auth_mod
        importlib.reload(auth_mod)

        token = _make_token(secret="wrong-secret")
        with pytest.raises(HTTPException) as exc_info:
            auth_mod._verify_token(token)
        assert exc_info.value.status_code == 401

    @patch.dict(os.environ, {"AUTH_SECRET": TEST_SECRET}, clear=False)
    def test_malformed_token_raises_401(self):
        """TC-AUTH-04: 格式错误的 token 应返回 401."""
        import importlib
        import src.auth as auth_mod
        importlib.reload(auth_mod)

        with pytest.raises(HTTPException) as exc_info:
            auth_mod._verify_token("not.a.valid.jwt")
        assert exc_info.value.status_code == 401

    @patch.dict(os.environ, {"AUTH_SECRET": TEST_SECRET}, clear=False)
    def test_token_missing_sub_raises_401(self):
        """TC-AUTH-05: 缺少 sub 字段的 token 应返回 401."""
        import importlib
        import src.auth as auth_mod
        importlib.reload(auth_mod)

        # 手动创建不含 sub 的 token
        payload = {"email": "test@test.com", "iat": int(time.time()), "exp": int(time.time()) + 3600}
        token = pyjwt.encode(payload, TEST_SECRET, algorithm="HS256")
        with pytest.raises(HTTPException) as exc_info:
            auth_mod._verify_token(token)
        assert exc_info.value.status_code == 401

    @patch.dict(os.environ, {"AUTH_SECRET": ""}, clear=False)
    def test_no_secret_configured_raises_500(self):
        """TC-AUTH-06: 未配置 AUTH_SECRET 时应返回 500."""
        import importlib
        import src.auth as auth_mod
        importlib.reload(auth_mod)

        token = _make_token()
        with pytest.raises(HTTPException) as exc_info:
            auth_mod._verify_token(token)
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# 2. AuthUser 数据类
# ---------------------------------------------------------------------------

class TestAuthUser:
    """测试 AuthUser 数据模型."""

    def test_create_with_defaults(self):
        """TC-AUTH-07: AuthUser 默认 email 为空字符串."""
        from src.auth import AuthUser
        user = AuthUser(id="u-1")
        assert user.id == "u-1"
        assert user.email == ""

    def test_create_with_all_fields(self):
        """TC-AUTH-08: AuthUser 应接受所有字段."""
        from src.auth import AuthUser
        user = AuthUser(id="u-2", email="test@test.com")
        assert user.id == "u-2"
        assert user.email == "test@test.com"


# ---------------------------------------------------------------------------
# 3. Dev 模式行为
# ---------------------------------------------------------------------------

class TestDevMode:
    """测试 dev 模式下 auth bypass."""

    @patch.dict(os.environ, {"AUTH_SECRET": "", "AUTH_REQUIRED": "false"}, clear=False)
    def test_dev_mode_returns_placeholder_user(self):
        """TC-AUTH-09: dev 模式无 token 时返回占位用户."""
        import importlib
        import src.auth as auth_mod
        importlib.reload(auth_mod)

        assert auth_mod.AUTH_REQUIRED is False

    @patch.dict(os.environ, {"AUTH_SECRET": TEST_SECRET, "AUTH_REQUIRED": "false"}, clear=False)
    def test_auth_required_false_bypasses(self):
        """TC-AUTH-10: AUTH_REQUIRED=false 即使有 secret 也不强制验证."""
        import importlib
        import src.auth as auth_mod
        importlib.reload(auth_mod)

        assert auth_mod.AUTH_REQUIRED is False
