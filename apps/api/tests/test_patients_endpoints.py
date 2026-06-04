"""Patient registry API tests — list/search, detail (PHI + audit), isolation."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.patient import Patient
from app.utils.context import current_clinic_id, current_user_id
from tests._doc_helpers import auth_headers, make_user_and_login

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, db: AsyncSession, clinic_id: UUID) -> dict[str, str]:
    token = await make_user_and_login(
        client=client,
        db=db,
        email=f"reg-{uuid4().hex[:8]}@suture-test.example.com",
        password="reg-pw-12345",
        clinic_id=clinic_id,
    )
    return auth_headers(token)


async def _make_patient(db: AsyncSession, clinic_id: UUID, **kw: object) -> UUID:
    tok = current_clinic_id.set(clinic_id)
    # user_id None mirrors the seeder; the audit FK is nullable and a fake
    # uuid would violate it.
    utok = current_user_id.set(None)
    try:
        p = Patient(
            clinic_id=clinic_id,
            first_name=kw.get("first_name", "Amy"),
            last_name=kw.get("last_name", "Robinson"),
            dob=kw.get("dob", "1966-03-13"),
            phone=kw.get("phone", "412-555-1234"),
            city=kw.get("city", "Pittsburgh"),
            state="PA",
            mrn=kw.get("mrn", f"MRN-{uuid4().hex[:6].upper()}"),
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return p.id
    finally:
        current_clinic_id.reset(tok)
        current_user_id.reset(utok)


async def test_list_and_search(
    client: AsyncClient, db_session: AsyncSession, two_clinics: tuple[UUID, UUID]
) -> None:
    clinic_a, _ = two_clinics
    headers = await _login(client, db_session, clinic_a)
    await _make_patient(db_session, clinic_a, last_name="Robinson", mrn="MRN-AAA111")
    await _make_patient(db_session, clinic_a, last_name="Carter", mrn="MRN-BBB222")

    # List returns both, minimal PHI (no dob/phone in list rows).
    resp = await client.get("/api/patients/", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert "dob" not in body["items"][0]
    assert "phone" not in body["items"][0]

    # Search by last name narrows.
    resp = await client.get("/api/patients/?q=Carter", headers=headers)
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["last_name"] == "Carter"

    # Search by MRN works too.
    resp = await client.get("/api/patients/?q=AAA111", headers=headers)
    assert resp.json()["total"] == 1


async def test_detail_returns_demographics_and_audits(
    client: AsyncClient, db_session: AsyncSession, two_clinics: tuple[UUID, UUID]
) -> None:
    clinic_a, _ = two_clinics
    headers = await _login(client, db_session, clinic_a)
    pid = await _make_patient(db_session, clinic_a, dob="1966-03-13", phone="412-555-1234")

    def _patient_views() -> object:
        return select(AuditLog).where(
            AuditLog.resource_type == "patients", AuditLog.action == AuditAction.view
        )

    tok = current_clinic_id.set(clinic_a)
    try:
        before = len((await db_session.execute(_patient_views())).scalars().all())
    finally:
        current_clinic_id.reset(tok)

    resp = await client.get(f"/api/patients/{pid}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Encrypted columns decrypt on read.
    assert body["dob"] == "1966-03-13"
    assert body["phone"] == "412-555-1234"

    # A view audit row was written, carrying no PHI in its details.
    tok = current_clinic_id.set(clinic_a)
    try:
        rows = (await db_session.execute(_patient_views())).scalars().all()
    finally:
        current_clinic_id.reset(tok)
    assert len(rows) == before + 1
    assert "412-555-1234" not in str(rows[-1].details)


async def test_tenant_isolation(
    client: AsyncClient, db_session: AsyncSession, two_clinics: tuple[UUID, UUID]
) -> None:
    clinic_a, clinic_b = two_clinics
    pid_a = await _make_patient(db_session, clinic_a)
    headers_b = await _login(client, db_session, clinic_b)

    # Clinic B sees none of A's patients and gets 404 on A's patient.
    resp = await client.get("/api/patients/", headers=headers_b)
    assert resp.json()["total"] == 0
    resp = await client.get(f"/api/patients/{pid_a}", headers=headers_b)
    assert resp.status_code == 404
