"""GET /api/documents/ — list, filter, paginate, tenant-isolate."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentClassification
from tests._doc_helpers import (
    auth_headers,
    make_user_and_login,
    patch_llm_provider,
    patch_ocr,
    patch_storage_path,
)

pytestmark = pytest.mark.asyncio

_FAKE_PDF = b"%PDF-1.4\n"


async def _upload_one(
    client: AsyncClient,
    token: str,
    *,
    name: str = "doc.pdf",
) -> str:
    """Upload one document and return its id."""
    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token),
        files={"file": (name, _FAKE_PDF, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def test_list_is_tenant_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Clinic A's uploads must not be visible to clinic B and vice-versa."""
    clinic_a, clinic_b = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="content")
    patch_llm_provider(
        monkeypatch,
        response_text=('{"classification": "referral", "confidence": 0.7, "reasoning": "r"}'),
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

    # Clinic A uploads 2.
    a_ids = [await _upload_one(client, token_a, name=f"a{i}.pdf") for i in range(2)]
    # Clinic B uploads 3.
    b_ids = [await _upload_one(client, token_b, name=f"b{i}.pdf") for i in range(3)]
    assert set(a_ids).isdisjoint(b_ids)

    # Clinic A sees only its 2.
    resp_a = await client.get("/api/documents/", headers=auth_headers(token_a))
    assert resp_a.status_code == 200, resp_a.text
    body_a = resp_a.json()
    assert body_a["total"] == 2
    assert {item["id"] for item in body_a["items"]} == set(a_ids)

    # Clinic B sees only its 3.
    resp_b = await client.get("/api/documents/", headers=auth_headers(token_b))
    assert resp_b.status_code == 200
    body_b = resp_b.json()
    assert body_b["total"] == 3
    assert {item["id"] for item in body_b["items"]} == set(b_ids)

    # Attack path: clinic A tries to read clinic B's document by id → 404.
    sneaky = await client.get(
        f"/api/documents/{b_ids[0]}",
        headers=auth_headers(token_a),
    )
    assert sneaky.status_code == 404


async def test_list_filters_by_classification(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="content")
    # First upload — referral.
    patch_llm_provider(
        monkeypatch,
        response_text=('{"classification": "referral", "confidence": 0.8, "reasoning": "r"}'),
    )
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="u@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )
    await _upload_one(client, token, name="ref.pdf")

    # Second upload — discharge_summary. Re-patch the LLM.
    patch_llm_provider(
        monkeypatch,
        response_text=(
            '{"classification": "discharge_summary", "confidence": 0.9, "reasoning": "r"}'
        ),
    )
    await _upload_one(client, token, name="dc.pdf")

    resp = await client.get(
        "/api/documents/",
        params={"classification": DocumentClassification.referral.value},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["classification"] == DocumentClassification.referral.value


async def test_list_pagination(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="content")
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
    for i in range(5):
        await _upload_one(client, token, name=f"d{i}.pdf")

    resp = await client.get(
        "/api/documents/",
        params={"limit": 2, "offset": 2},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["items"]) == 2
