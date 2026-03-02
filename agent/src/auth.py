"""
JWT authentication for the FastAPI backend.

Verifies tokens issued by the Next.js frontend (via /api/auth/api-token).
The same AUTH_SECRET is used on both sides for HMAC-SHA256 signing.

Usage in route handlers:
    from src.auth import get_current_user, CurrentUser

    @router.get("/projects")
    async def list_projects(user: CurrentUser = Depends(get_current_user)):
        ...
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

import jwt  # PyJWT
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("auth")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AUTH_SECRET = os.getenv("AUTH_SECRET") or os.getenv("NEXTAUTH_SECRET") or ""
# When AUTH_REQUIRED is false (or AUTH_SECRET is empty), unauthenticated
# requests are allowed through with a placeholder user.  This keeps the
# dev experience smooth while ensuring production always enforces auth.
# AUTH_REQUIRED = bool(AUTH_SECRET) and os.getenv("AUTH_REQUIRED", "true").lower() not in (
#     "0",
#     "false",
#     "no",
# )
# Dev mode: disable auth when AUTH_REQUIRED=false
_AUTH_REQUIRED_RAW = os.getenv("AUTH_REQUIRED", "false").lower().strip()
AUTH_REQUIRED = _AUTH_REQUIRED_RAW in ("1", "true", "yes")
_DEV_BYPASS = not AUTH_REQUIRED

# ---------------------------------------------------------------------------
# Bearer token extractor (optional – won't raise if header is absent)
# ---------------------------------------------------------------------------
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------
@dataclass
class AuthUser:
    """Minimal user identity extracted from a verified JWT."""

    id: str
    email: str = ""


# Type alias for dependency injection
CurrentUser = AuthUser

# Placeholder for unauthenticated dev mode
_DEV_USER = AuthUser(id="dev-user", email="dev@localhost")


# ---------------------------------------------------------------------------
# Core verification
# ---------------------------------------------------------------------------
def _verify_token(token: str) -> AuthUser:
    """Decode and verify a JWT string.  Raises HTTPException on failure."""
    if not AUTH_SECRET:
        raise HTTPException(
            status_code=500, detail="AUTH_SECRET not configured on server"
        )

    try:
        payload = jwt.decode(
            token,
            AUTH_SECRET,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as exc:
        logger.warning(f"[auth] Invalid token: {exc}")
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    return AuthUser(
        id=str(user_id),
        email=payload.get("email", ""),
    )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------
async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthUser:
    """Require a valid JWT Bearer token and return the authenticated user.

    In dev mode (AUTH_SECRET not set or AUTH_REQUIRED=false), returns a
    placeholder user so local development doesn't need tokens.
    """
    # --- Try to extract token ---
    token: Optional[str] = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        # Fallback: check query param (useful for SSE / EventSource)
        token = request.query_params.get("token")

    # --- Dev-mode bypass ---
    if _DEV_BYPASS:
        # In dev mode (AUTH_REQUIRED=false), always allow access
        # Token validation is optional - if provided and valid, use it; otherwise use dev user
        if token:
            try:
                return _verify_token(token)
            except HTTPException:
                pass
        return _DEV_USER

    # --- Production: token is mandatory ---
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _verify_token(token)


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[AuthUser]:
    """Like get_current_user but returns None instead of raising 401."""
    token: Optional[str] = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        token = request.query_params.get("token")

    if not token:
        return _DEV_USER if _DEV_BYPASS else None

    try:
        return _verify_token(token)
    except HTTPException:
        return _DEV_USER if _DEV_BYPASS else None
