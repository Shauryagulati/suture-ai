"""Every classification call must persist an ai_invocations row, scoped to the clinic."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_invocation import AiInvocation, InvocationType
from app.utils.context import current_clinic_id
from tests._doc_helpers import (
    auth_headers,
    make_user_and_login,
    patch_llm_provider,
    patch_ocr,
    patch_storage_path,
)

pytestmark = pytest.mark.asyncio

_FAKE_PDF = b"%PDF-1.4\n"


async def _upload(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token),
        files={"file": ("d.pdf", _FAKE_PDF, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def test_classification_writes_ai_invocation_row(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="some text")
    patch_llm_provider(
        monkeypatch,
        response_text=(
            '{"classification": "referral", "confidence": 0.8, "reasoning": "r"}'
        ),
        model="medgemma1.5",
    )
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="u@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )
    doc_id = await _upload(client, token)

    tok = current_clinic_id.set(clinic_a)
    try:
        rows = (await db_session.execute(select(AiInvocation))).scalars().all()
    finally:
        current_clinic_id.reset(tok)

    # Filter by invocation_type so the test isolates the classification row
    # from the auto-extract row added in Module 2.
    matching = [
        r
        for r in rows
        if str(r.document_id) == doc_id and r.invocation_type == InvocationType.classification
    ]
    assert len(matching) == 1
    row = matching[0]
    assert row.model == "medgemma1.5"
    assert row.clinic_id == clinic_a
    assert row.latency_ms >= 0
    # Confidence captured in the JSONB column.
    assert row.confidence_scores.get("classification") == pytest.approx(0.8)


async def test_ai_invocation_is_tenant_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Clinic B must not see clinic A's ai_invocations rows via the tenant guard."""
    clinic_a, clinic_b = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="x")
    patch_llm_provider(
        monkeypatch,
        response_text=(
            '{"classification": "other", "confidence": 0.5, "reasoning": "r"}'
        ),
    )

    token_a = await make_user_and_login(
        client=client,
        db=db_session,
        email="a@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )
    token_b = await make_user_and_login(
        client=client,
        db=db_session,
        email="b@b.example.com",
        password="pw1234567",
        clinic_id=clinic_b,
    )

    await _upload(client, token_a)
    await _upload(client, token_b)

    # In clinic A's context, only one invocation row is visible.
    tok = current_clinic_id.set(clinic_a)
    try:
        a_rows = (await db_session.execute(select(AiInvocation))).scalars().all()
    finally:
        current_clinic_id.reset(tok)
    assert len(a_rows) == 1
    assert a_rows[0].clinic_id == clinic_a

    tok = current_clinic_id.set(clinic_b)
    try:
        b_rows = (await db_session.execute(select(AiInvocation))).scalars().all()
    finally:
        current_clinic_id.reset(tok)
    assert len(b_rows) == 1
    assert b_rows[0].clinic_id == clinic_b
