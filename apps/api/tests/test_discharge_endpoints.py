"""Discharge GET / confirm / fax-download + appointment-complete endpoints.

Covers:
- POST /api/discharges/{id}/confirm fires the fax when status=seen
- POST .../confirm returns 409 when status != seen
- GET  /api/discharges/{id}/fax streams the PDF
- GET  .../fax returns 404 before fax exists
- Tenant isolation on confirm + fax (clinic B sees 404 for clinic A's discharge)
- POST /api/appointments/{id}/complete advances scheduled -> seen + idempotent
- GET  /api/discharges/{id} writes an audit view row
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, AppointmentStatus
from app.models.audit_log import AuditLog
from app.models.discharge_summary import (
    DischargeStatus,
    DischargeSummary,
    UrgencyTier,
)
from app.models.fax import Fax, FaxStatus
from app.models.patient import Patient
from app.models.provider import Provider, ProviderType
from app.services.discharge import confirmation as confirmation_mod
from app.services.fax import factory as fax_factory
from app.services.fax import stub as fax_stub_mod
from app.utils.context import current_clinic_id, current_user_id
from tests._doc_helpers import auth_headers, make_user_and_login

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_fax_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(confirmation_mod, "_PERSIST_ROOT", tmp_path / "confirmations")
    monkeypatch.setattr(fax_stub_mod, "_OUTBOX_ROOT", tmp_path / "fax_outbox")
    fax_factory.reset_fax_provider_cache()
    yield
    fax_factory.reset_fax_provider_cache()


async def _login(
    client: AsyncClient, db: AsyncSession, clinic_id: UUID, letter: str
) -> tuple[dict[str, str], UUID]:
    from app.models.user import User

    email = f"discharge-{letter}-{uuid4().hex[:6]}@suture-test.example.com"
    token = await make_user_and_login(
        client=client,
        db=db,
        email=email,
        password="discharge-pw-1234",
        clinic_id=clinic_id,
    )
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one()
    return auth_headers(token), user.id


async def _seed_discharge(
    db: AsyncSession,
    *,
    clinic_id: UUID,
    user_id: UUID,
    status: DischargeStatus,
) -> tuple[DischargeSummary, Patient, Provider]:
    """Seed a Patient + internal Provider + DischargeSummary in clinic context."""
    cid_token = current_clinic_id.set(clinic_id)
    uid_token = current_user_id.set(user_id)
    try:
        patient = Patient(
            id=uuid4(),
            clinic_id=clinic_id,
            mrn=f"MRN-{uuid4().hex[:6]}",
            first_name="Pat",
            last_name="Disch",
            dob="1955-07-04",
            phone="412-555-0160",
        )
        provider = Provider(
            id=uuid4(),
            clinic_id=clinic_id,
            first_name="Renee",
            last_name="Wexler",
            npi="1234567890",
            provider_type=ProviderType.internal,
            practice_name="Steel City Cardiology",
            practice_phone="412-555-0190",
            practice_address="500 Forbes Ave, Pittsburgh, PA",
            specialty="Cardiology",
        )
        db.add_all([patient, provider])
        await db.flush()
        discharge = DischargeSummary(
            id=uuid4(),
            clinic_id=clinic_id,
            patient_id=patient.id,
            status=status,
            urgency_tier=UrgencyTier.high,
            discharge_date=date(2026, 5, 20),
        )
        db.add(discharge)
        await db.commit()
        return discharge, patient, provider
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)


async def _seed_appointment(
    db: AsyncSession,
    *,
    clinic_id: UUID,
    user_id: UUID,
    patient_id: UUID,
    provider_id: UUID,
    discharge_id: UUID | None,
) -> Appointment:
    cid_token = current_clinic_id.set(clinic_id)
    uid_token = current_user_id.set(user_id)
    try:
        appt = Appointment(
            id=uuid4(),
            clinic_id=clinic_id,
            patient_id=patient_id,
            provider_id=provider_id,
            discharge_summary_id=discharge_id,
            appointment_at=datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
            appointment_type="cardiology_followup",
            status=AppointmentStatus.scheduled,
        )
        db.add(appt)
        await db.commit()
        return appt
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)


# ─────────────────────────────────────────────────────────────────────
# GET /api/discharges/{id}
# ─────────────────────────────────────────────────────────────────────


async def test_get_discharge_returns_detail_and_audits_view(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login(client, db_session, clinic_a, "a")
    discharge, _patient, _ = await _seed_discharge(
        db_session, clinic_id=clinic_a, user_id=user_id, status=DischargeStatus.new
    )

    r = await client.get(f"/api/discharges/{discharge.id}", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(discharge.id)
    assert body["status"] == "new"
    assert body["patient_first_name"] == "Pat"
    assert body["patient_last_name"] == "Disch"
    assert body["urgency_tier"] == "high"

    # Audit view row exists.
    cid = current_clinic_id.set(clinic_a)
    try:
        views = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.resource_type == "discharge_summaries",
                    AuditLog.resource_id == discharge.id,
                    AuditLog.action == "view",
                )
            )
        ).scalars().all()
    finally:
        current_clinic_id.reset(cid)
    assert len(views) == 1


async def test_get_discharge_returns_404_for_unknown(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, _ = await _login(client, db_session, clinic_a, "a")
    r = await client.get(f"/api/discharges/{uuid4()}", headers=headers)
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────
# POST /api/discharges/{id}/confirm
# ─────────────────────────────────────────────────────────────────────


async def test_confirm_on_seen_advances_to_confirmation_sent_and_fires_fax(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login(client, db_session, clinic_a, "a")
    discharge, _, _ = await _seed_discharge(
        db_session, clinic_id=clinic_a, user_id=user_id, status=DischargeStatus.seen
    )

    r = await client.post(f"/api/discharges/{discharge.id}/confirm", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "confirmation_sent"
    assert body["confirmation_fax_sent_at"] is not None
    assert body["fax_available"] is True

    # Fax row recorded.
    cid = current_clinic_id.set(clinic_a)
    try:
        faxes = (
            await db_session.execute(
                select(Fax).where(Fax.patient_id == discharge.patient_id)
            )
        ).scalars().all()
    finally:
        current_clinic_id.reset(cid)
    assert len(faxes) == 1
    assert faxes[0].status == FaxStatus.sent


async def test_confirm_on_scheduled_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login(client, db_session, clinic_a, "a")
    discharge, _, _ = await _seed_discharge(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        status=DischargeStatus.scheduled,
    )
    r = await client.post(f"/api/discharges/{discharge.id}/confirm", headers=headers)
    assert r.status_code == 409
    assert "status=seen" in r.json()["detail"]


async def test_confirm_returns_404_for_unknown(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, _ = await _login(client, db_session, clinic_a, "a")
    r = await client.post(f"/api/discharges/{uuid4()}/confirm", headers=headers)
    assert r.status_code == 404


async def test_confirm_cross_tenant_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    """Clinic B's JWT must not be able to confirm clinic A's discharge."""
    clinic_a, clinic_b = two_clinics
    _, user_a_id = await _login(client, db_session, clinic_a, "a")
    headers_b, _ = await _login(client, db_session, clinic_b, "b")

    discharge, _, _ = await _seed_discharge(
        db_session, clinic_id=clinic_a, user_id=user_a_id, status=DischargeStatus.seen
    )

    r = await client.post(f"/api/discharges/{discharge.id}/confirm", headers=headers_b)
    assert r.status_code == 404, r.text  # tenant guard hides the row


# ─────────────────────────────────────────────────────────────────────
# GET /api/discharges/{id}/fax
# ─────────────────────────────────────────────────────────────────────


async def test_get_fax_returns_pdf_after_confirmation(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login(client, db_session, clinic_a, "a")
    discharge, _, _ = await _seed_discharge(
        db_session, clinic_id=clinic_a, user_id=user_id, status=DischargeStatus.seen
    )
    await client.post(f"/api/discharges/{discharge.id}/confirm", headers=headers)

    r = await client.get(f"/api/discharges/{discharge.id}/fax", headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")


async def test_get_fax_before_confirmation_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login(client, db_session, clinic_a, "a")
    discharge, _, _ = await _seed_discharge(
        db_session, clinic_id=clinic_a, user_id=user_id, status=DischargeStatus.new
    )
    r = await client.get(f"/api/discharges/{discharge.id}/fax", headers=headers)
    assert r.status_code == 404
    assert "no confirmation fax" in r.json()["detail"]


async def test_get_fax_cross_tenant_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, clinic_b = two_clinics
    headers_a, user_a_id = await _login(client, db_session, clinic_a, "a")
    headers_b, _ = await _login(client, db_session, clinic_b, "b")

    discharge, _, _ = await _seed_discharge(
        db_session, clinic_id=clinic_a, user_id=user_a_id, status=DischargeStatus.seen
    )
    await client.post(f"/api/discharges/{discharge.id}/confirm", headers=headers_a)

    r = await client.get(f"/api/discharges/{discharge.id}/fax", headers=headers_b)
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────
# POST /api/appointments/{id}/complete
# ─────────────────────────────────────────────────────────────────────


async def test_complete_appointment_advances_linked_discharge_to_seen(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login(client, db_session, clinic_a, "a")
    discharge, patient, provider = await _seed_discharge(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        status=DischargeStatus.scheduled,
    )
    appt = await _seed_appointment(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        patient_id=patient.id,
        provider_id=provider.id,
        discharge_id=discharge.id,
    )

    r = await client.post(
        f"/api/appointments/{appt.id}/complete", headers=headers
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["appointment_status"] == "completed"
    assert body["discharge_status"] == "seen"


async def test_complete_appointment_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login(client, db_session, clinic_a, "a")
    discharge, patient, provider = await _seed_discharge(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        status=DischargeStatus.scheduled,
    )
    appt = await _seed_appointment(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        patient_id=patient.id,
        provider_id=provider.id,
        discharge_id=discharge.id,
    )

    r1 = await client.post(f"/api/appointments/{appt.id}/complete", headers=headers)
    assert r1.status_code == 200
    r2 = await client.post(f"/api/appointments/{appt.id}/complete", headers=headers)
    assert r2.status_code == 200
    # Second call still reports completed + seen, did not error or double-fire.
    assert r2.json()["appointment_status"] == "completed"
    assert r2.json()["discharge_status"] == "seen"


async def test_complete_appointment_without_discharge_does_not_set_discharge_status(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login(client, db_session, clinic_a, "a")
    _, patient, provider = await _seed_discharge(
        db_session, clinic_id=clinic_a, user_id=user_id, status=DischargeStatus.new
    )
    appt = await _seed_appointment(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        patient_id=patient.id,
        provider_id=provider.id,
        discharge_id=None,
    )

    r = await client.post(f"/api/appointments/{appt.id}/complete", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["appointment_status"] == "completed"
    assert r.json()["discharge_status"] is None
