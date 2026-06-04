"""Classification verdict pipeline — happy path + malformed LLM response."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentClassification, DocumentStatus
from app.utils.context import current_clinic_id
from tests._doc_helpers import (
    auth_headers,
    make_user_and_login,
    patch_llm_provider,
    patch_ocr,
    patch_storage_path,
)

pytestmark = pytest.mark.asyncio


async def _latest_doc(db: AsyncSession, clinic_id: UUID) -> Document:
    """Re-fetch the most recent document. Classification/extraction run in a
    background task, so assertions read the persisted row, not the upload
    response."""
    tok = current_clinic_id.set(clinic_id)
    try:
        db.expire_all()
        rows = (await db.execute(select(Document))).scalars().all()
    finally:
        current_clinic_id.reset(tok)
    return rows[-1]

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
    doc = await _latest_doc(db_session, clinic_a)
    assert doc.classification == DocumentClassification.referral
    assert doc.classification_confidence is not None
    assert doc.classification_confidence > 0.5


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
    doc = await _latest_doc(db_session, clinic_a)
    assert doc.classification == DocumentClassification.unclassified
    assert doc.classification_confidence == 0.0
    # Status should still be `classified` — the document was processed, the
    # LLM just couldn't pick a category.
    assert doc.status == DocumentStatus.classified
