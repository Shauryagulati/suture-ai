"""HTTP middleware: security headers + lightweight auth rate limiting.

Implemented as **pure ASGI** middleware, not Starlette ``BaseHTTPMiddleware``.
BaseHTTPMiddleware runs the downstream app in a separate anyio task, which drops
ContextVars (e.g. ``current_clinic_id``) for streaming responses — that would
make the tenant guard fail closed on streaming endpoints like the voice
transcript. Pure ASGI middleware wraps send/receive in-place and preserves them.

Both are dependency-free. The rate limiter keeps per-IP counters in process
memory — correct for the single-worker local v1; a multi-worker production
deployment swaps in a Redis-backed limiter (see SECURITY.md).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings

# Applied to every response.
_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    # Modern guidance: disable the legacy auditor and rely on CSP.
    "x-xss-protection": "0",
    "permissions-policy": "geolocation=(), microphone=(), camera=()",
}
# Restrictive CSP for the JSON API. Skipped for the interactive docs, which load
# Swagger UI assets and would break under default-src 'none'.
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
_CSP_EXEMPT_PREFIXES = ("/docs", "/redoc", "/openapi.json")

# Endpoints that get brute-force protection.
_RATE_LIMITED_PREFIXES = ("/api/auth/login", "/api/auth/register")
_WINDOW_SECONDS = 60.0


class SecurityHeadersMiddleware:
    """Add standard security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        add_csp = not any(scope.get("path", "").startswith(p) for p in _CSP_EXEMPT_PREFIXES)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in _SECURITY_HEADERS.items():
                    headers.setdefault(key, value)
                if add_csp:
                    headers.setdefault("content-security-policy", _API_CSP)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class AuthRateLimitMiddleware:
    """Fixed-window per-IP limit on auth endpoints (brute-force protection)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        path = scope.get("path", "")
        if settings.rate_limit_enabled and any(path.startswith(p) for p in _RATE_LIMITED_PREFIXES):
            client = scope.get("client")
            ip = client[0] if client else "unknown"
            now = time.monotonic()
            hits = self._hits[ip]
            while hits and now - hits[0] > _WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= settings.auth_rate_limit_per_minute:
                retry_after = int(_WINDOW_SECONDS - (now - hits[0])) + 1
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again shortly."},
                    headers={"Retry-After": str(retry_after)},
                )
                await response(scope, receive, send)
                return
            hits.append(now)

        await self.app(scope, receive, send)
