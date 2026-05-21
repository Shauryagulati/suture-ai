"""Classification verdict pipeline — happy path + malformed LLM response."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentClassification, DocumentStatus
from tests._doc_helpers import (
    auth_headers,
    make_user_and_login,
    patch_llm_provider,
    patch_ocr,
    patch_storage_path,
)

pytestmark = pytest.mark.asyncio

_FAKE_PDF = b"%PDF-1.4\n"


async def test_classification_referral_with_high_confidence(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(
        monkeypatch,
        text=(
            "REFERRAL REQUEST\nReferring Provider: Dr. Smith\n"
            "Please evaluate this patient for chest pain workup."
        ),
    )
    patch_llm_provider(
        monkeypatch,
        response_text=(
            '{"classification": "referral", "confidence": 0.85, '
            '"reasoning": "Header reads REFERRAL REQUEST."}'
        ),
    )
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="u@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )

    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token),
        files={"file": ("ref.pdf", _FAKE_PDF, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["classification"] == DocumentClassification.referral.value
    assert body["classification_confidence"] > 0.5


async def test_classification_falls_back_to_unclassified_on_bad_json(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Garbage LLM output must NOT crash the upload — fall back to unclassified."""
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="some text")
    patch_llm_provider(
        monkeypatch,
        response_text="this is not JSON at all, just rambling prose",
    )
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="u@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )

    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token),
        files={"file": ("ambiguous.pdf", _FAKE_PDF, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["classification"] == DocumentClassification.unclassified.value
    assert body["classification_confidence"] == 0.0
    # Status should still be `classified` — the document was processed, the
    # LLM just couldn't pick a category.
    assert body["status"] == DocumentStatus.classified.value
