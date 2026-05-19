"""Shared pytest fixtures.

Gate A scope: minimal — just an httpx client against the FastAPI app for /health.
Gate B1 will add: ephemeral Postgres, transactional rollback, clinic-context helper.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
