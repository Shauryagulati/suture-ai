"""GET /api/documents/{id}, PATCH /{id}, GET /{id}/file, and view-audit."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.document import DocumentStatus
from app.utils.context import current_clinic_id
from tests._doc_helpers import (
    auth_headers,
    make_user_and_login,
    patch_llm_provider,
    patch_ocr,
    patch_storage_path,
)

pytestmark = pytest.mark.asyncio

_FAKE_PDF = b"%PDF-1.4\n%hello world\n"


async def _upload(
    client: AsyncClient,
    token: str,
) -> str:
    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token),
        files={"file": ("scan.pdf", _FAKE_PDF, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def test_detail_returns_full_payload(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="extracted body text")
    patch_llm_provider(
        monkeypatch,
        response_text=('{"classification": "lab", "confidence": 0.8, "reasoning": "r"}'),
    )
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="u@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )
    doc_id = await _upload(client, token)

    resp = await client.get(f"/api/documents/{doc_id}", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == doc_id
    assert body["extracted_text"] == "extracted body text"
    assert body["ocr_engine"] == "pypdf"
    assert body["notes"] is None


async def test_patch_updates_status_and_notes(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="x")
    patch_llm_provider(
        monkeypatch,
        response_text=('{"classification": "other", "confidence": 0.5, "reasoning": "r"}'),
    )
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="u@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )
    doc_id = await _upload(client, token)

    patch_resp = await client.patch(
        f"/api/documents/{doc_id}",
        json={"status": DocumentStatus.reviewed.value, "notes": "looks ok"},
        headers=auth_headers(token),
    )
    assert patch_resp.status_code == 200, patch_resp.text
    body = patch_resp.json()
    assert body["status"] == DocumentStatus.reviewed.value
    assert body["notes"] == "looks ok"


async def test_get_file_streams_pdf_bytes(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="x")
    patch_llm_provider(
        monkeypatch,
        response_text=('{"classification": "other", "confidence": 0.5, "reasoning": "r"}'),
    )
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="u@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )
    doc_id = await _upload(client, token)

    resp = await client.get(
        f"/api/documents/{doc_id}/file",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == _FAKE_PDF


async def test_detail_view_writes_audit_row(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """GET /{id} must emit a `view` audit_logs row (PHI access traceability)."""
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="x")
    patch_llm_provider(
        monkeypatch,
        response_text=('{"classification": "other", "confidence": 0.5, "reasoning": "r"}'),
    )
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="u@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )
    doc_id = await _upload(client, token)

    # Snapshot view-count before.
    tok = current_clinic_id.set(clinic_a)
    try:
        before = (
            await db_session.execute(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "view")
            )
        ).scalar_one()
    finally:
        current_clinic_id.reset(tok)

    resp = await client.get(f"/api/documents/{doc_id}", headers=auth_headers(token))
    assert resp.status_code == 200

    tok = current_clinic_id.set(clinic_a)
    try:
        after = (
            await db_session.execute(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "view")
            )
        ).scalar_one()
    finally:
        current_clinic_id.reset(tok)
    assert after == before + 1
