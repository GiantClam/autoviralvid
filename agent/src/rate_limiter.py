"""
Simple in-memory rate limiter for the FastAPI backend.

Uses a sliding-window counter per IP (or per user_id when auth is available).
This is a best-effort limiter suitable for a single-process deployment.
For multi-instance production, switch to Redis-based limiting.

Usage:
    from src.rate_limiter import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware, rpm=60)
"""

import time
import logging
from collections import defaultdict
from typing import Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("rate_limiter")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter (requests per minute)."""

    def __init__(self, app, rpm: int = 60):
        super().__init__(app)
        self.rpm = rpm
        self.window = 60.0  # seconds
        # {key: [(timestamp, ...)] }
        self._hits: Dict[str, list] = defaultdict(list)
        self._last_cleanup = time.monotonic()

    def _client_key(self, request: Request) -> str:
        """Derive a rate-limit key from the request."""
        # Prefer user ID from auth header (if decoded), fall back to IP
        forwarded = request.headers.get("x-forwarded-for")
        ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        return f"ip:{ip}"

    def _cleanup(self, now: float):
        """Remove stale entries every 60 seconds to keep memory bounded."""
        if now - self._last_cleanup < 60:
            return
        cutoff = now - self.window
        stale_keys = []
        for key, timestamps in self._hits.items():
            self._hits[key] = [t for t in timestamps if t > cutoff]
            if not self._hits[key]:
                stale_keys.append(key)
        for k in stale_keys:
            del self._hits[k]
        self._last_cleanup = now

    async def dispatch(self, request: Request, call_next):
        # Skip rate-limiting for health checks and webhooks
        path = request.url.path
        if path in ("/healthz", "/webhook/runninghub", "/render/health"):
            return await call_next(request)

        now = time.monotonic()
        self._cleanup(now)

        key = self._client_key(request)
        cutoff = now - self.window
        # Prune old timestamps
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]

        if len(self._hits[key]) >= self.rpm:
            remaining = 0
            reset_at = self._hits[key][0] + self.window
            retry_after = max(1, int(reset_at - now))
            logger.warning(f"[rate_limit] Key {key} exceeded {self.rpm} rpm")
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests. Please try again later."},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.rpm),
                    "X-RateLimit-Remaining": "0",
                },
            )

        self._hits[key].append(now)
        remaining = max(0, self.rpm - len(self._hits[key]))

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rpm)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
