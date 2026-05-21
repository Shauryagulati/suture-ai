"""Shared helpers for document inbox tests.

Functions here build users, tokens, and mock the OCR/LLM providers used by
the upload pipeline.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ClinicMembership, MembershipRole, User
from app.services.llm import factory as llm_factory
from app.services.llm.ollama import OllamaProvider
from app.utils.security import hash_password


async def make_user_and_login(
    *,
    client: AsyncClient,
    db: AsyncSession,
    email: str,
    password: str,
    clinic_id: UUID,
    role: MembershipRole = MembershipRole.admin,
) -> str:
    """Create a user in the given clinic, log in, return the access token."""
    user = User(
        id=uuid4(),
        email=email,
        hashed_password=hash_password(password),
        full_name="Test User",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    db.add(
        ClinicMembership(
            user_id=user.id,
            clinic_id=clinic_id,
            role=role,
            is_default=True,
        )
    )
    await db.commit()

    resp = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def patch_ocr(monkeypatch: pytest.MonkeyPatch, *, text: str, engine: str = "pypdf") -> None:
    """Replace the OCR layer used by the documents router with a stub."""

    async def _fake(_path: Any) -> tuple[str, str]:
        return text, engine

    monkeypatch.setattr("app.routers.documents.extract_text", _fake)


def patch_llm_provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response_text: str,
    extraction_response_text: str = "{}",
    model: str = "medgemma1.5",
) -> None:
    """Wire classification AND extraction LLM calls to a single MockTransport.

    The mock routes by the system-prompt prefix:
    - extraction prompts (``"You are a structured-data extractor"`` from the
      Module 2 prompt files) → ``extraction_response_text`` (default: empty
      JSON, which yields a parse-success row with ``human_review_required``).
    - everything else (classification) → ``response_text``.

    Tests that only run classification can ignore ``extraction_response_text``.
    Tests that exercise the auto-extract path should pass a realistic
    extraction JSON.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        system = body.get("system", "")
        if system.startswith("You are a structured-data extractor"):
            return httpx.Response(200, json={"response": extraction_response_text})
        return httpx.Response(200, json={"response": response_text})

    transport = httpx.MockTransport(handler)
    provider = OllamaProvider(model=model, base_url="http://mock-llm")
    provider._client = httpx.AsyncClient(base_url="http://mock-llm", transport=transport)

    llm_factory.get_llm_provider.cache_clear()
    monkeypatch.setattr(
        "app.services.classification.get_llm_provider",
        lambda: provider,
    )
    monkeypatch.setattr(
        "app.services.extraction.service.get_llm_provider",
        lambda: provider,
    )


def patch_storage_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Redirect uploaded PDFs into pytest's tmp_path."""
    settings = get_settings()
    monkeypatch.setattr(settings, "document_storage_path", tmp_path / "documents")
