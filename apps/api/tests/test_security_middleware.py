"""Security headers (on the shared app) + auth rate limiting (in isolation).

Rate limiting is disabled globally in tests (conftest) to avoid tripping the
per-IP limiter across the suite's many logins, so it's verified here on a
purpose-built app instance.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware import AuthRateLimitMiddleware

pytestmark = pytest.mark.asyncio


async def test_security_headers_present(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in resp.headers["Content-Security-Policy"]


async def test_docs_exempt_from_strict_csp(client: AsyncClient) -> None:
    # Swagger UI would break under default-src 'none'.
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert "Content-Security-Policy" not in resp.headers


def _rate_limited_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthRateLimitMiddleware)

    @app.post("/api/auth/login")
    async def _login() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health")
    async def _health() -> dict[str, bool]:
        return {"ok": True}

    return app


async def test_auth_rate_limit_blocks_after_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import app.middleware as mw

    monkeypatch.setattr(
        mw,
        "get_settings",
        lambda: SimpleNamespace(rate_limit_enabled=True, auth_rate_limit_per_minute=3),
    )

    app = _rate_limited_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # First 3 allowed, 4th blocked.
        for _ in range(3):
            assert (await ac.post("/api/auth/login")).status_code == 200
        blocked = await ac.post("/api/auth/login")
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        # Non-auth paths are never limited.
        assert (await ac.get("/health")).status_code == 200


async def test_rate_limit_disabled_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    import app.middleware as mw

    monkeypatch.setattr(
        mw,
        "get_settings",
        lambda: SimpleNamespace(rate_limit_enabled=False, auth_rate_limit_per_minute=1),
    )
    app = _rate_limited_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for _ in range(5):
            assert (await ac.post("/api/auth/login")).status_code == 200
