"""POST /api/documents/upload — multipart PDF upload."""

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


_FAKE_PDF = b"%PDF-1.4\n%mocked test fixture\n"


async def test_upload_happy_path_creates_row_and_file(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="Patient referred for cardiology consult.")
    patch_llm_provider(
        monkeypatch,
        response_text=(
            '{"classification": "referral", "confidence": 0.92, '
            '"reasoning": "Header reads consult request."}'
        ),
    )
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="uploader@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )

    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token),
        files={"file": ("scan.pdf", _FAKE_PDF, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["file_name"] == "scan.pdf"
    assert body["mime_type"] == "application/pdf"
    # Upload returns instantly; OCR/classify/extract run in a background task,
    # so the response reflects the just-saved (unprocessed) document.
    assert body["status"] == DocumentStatus.uploaded.value
    # Not yet processed → still the default classification.
    assert body["classification"] == DocumentClassification.unclassified.value

    # Row in DB, scoped to clinic A — the background pipeline has run by now.
    token_a = current_clinic_id.set(clinic_a)
    try:
        rows = (await db_session.execute(select(Document))).scalars().all()
    finally:
        current_clinic_id.reset(token_a)
    assert len(rows) == 1
    doc = rows[0]
    assert doc.clinic_id == clinic_a
    # Referral auto-extracts, so the final status is `extracted`.
    assert doc.status == DocumentStatus.extracted
    assert doc.classification == DocumentClassification.referral
    assert doc.classification_confidence == pytest.approx(0.92)
    assert doc.ocr_engine == "pypdf"
    assert Path(doc.file_path).exists()
    assert Path(doc.file_path).read_bytes() == _FAKE_PDF


async def test_upload_rejects_non_pdf_mime(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="uploader@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )

    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token),
        files={"file": ("notes.txt", b"plain text not a pdf", "text/plain")},
    )
    assert resp.status_code == 415


async def test_upload_rejects_oversize(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)  # 1 KB cap for this test

    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="uploader@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )

    oversize = b"%PDF-1.4\n" + b"x" * 2048
    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token),
        files={"file": ("big.pdf", oversize, "application/pdf")},
    )
    assert resp.status_code == 413
