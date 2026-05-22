"""Public scheduling endpoints — GET /api/schedule/{token}, POST /book.

These endpoints are unauthed; auth happens via the signed token. The
token carries clinic_id, which the handler writes to the tenant
ContextVar so existing guard semantics apply.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, AppointmentStatus
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.models.provider import Provider, ProviderType
from app.models.referral import Referral, ReferralStatus
from app.utils.security import encode_access_token, encode_scheduling_token

pytestmark = pytest.mark.asyncio


async def _seed_patient_provider_attempt(
    db: AsyncSession,
    clinic_id: UUID,
    *,
    with_referral: bool = False,
) -> tuple[Patient, Provider, OutreachAttempt, Referral | None]:
    """Insert a patient, an internal provider, and a pending OutreachAttempt
    (optionally tied to a referral) inside the caller's clinic context."""
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        mrn=f"MRN-{uuid4().hex[:6]}",
        first_name="Pat",
        last_name="Sched",
        dob="1972-03-10",
        phone="412-555-0150",
    )
    provider = Provider(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Doc",
        last_name="Cardiac",
        npi="1234567890",
        provider_type=ProviderType.internal,
    )
    db.add_all([patient, provider])
    await db.flush()

    referral: Referral | None = None
    if with_referral:
        referral = Referral(
            id=uuid4(),
            clinic_id=clinic_id,
            patient_id=patient.id,
            assigned_provider_id=provider.id,
            status=ReferralStatus.ready_to_schedule,
        )
        db.add(referral)
        await db.flush()

    attempt = OutreachAttempt(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient.id,
        referral_id=referral.id if referral else None,
        channel=OutreachChannel.sms,
        status=OutreachStatus.sent,
        scheduled_at=datetime.now(UTC),
        outcome={},
        attempt_number=1,
    )
    db.add(attempt)
    await db.commit()
    return patient, provider, attempt, referral


async def test_get_slots_returns_six_weekday_slots(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, _, attempt, _ = await _seed_patient_provider_attempt(db_session, clinic_a_id)

    token, _ = encode_scheduling_token(
        patient_id=patient.id,
        clinic_id=clinic_a_id,
        outreach_attempt_id=attempt.id,
    )
    r = await client.get(f"/api/schedule/{token}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["patient_first_name"] == "Pat"
    assert len(body["slots"]) == 6
    assert body["outreach_attempt_id"] == str(attempt.id)
    # All slots are weekday and in the future.
    for slot_str in body["slots"]:
        ts = datetime.fromisoformat(slot_str.replace("Z", "+00:00"))
        assert ts.weekday() < 5
        assert ts > datetime.now(UTC)


async def test_get_slots_garbage_token_returns_401(client: AsyncClient) -> None:
    r = await client.get("/api/schedule/not-a-real-jwt-token")
    assert r.status_code == 401


async def test_get_slots_access_token_rejected_as_wrong_type(client: AsyncClient) -> None:
    access, _ = encode_access_token(
        user_id=uuid4(), clinic_id=uuid4(), role="admin"
    )
    r = await client.get(f"/api/schedule/{access}")
    assert r.status_code == 401
    assert "scheduling" in r.json()["detail"]


async def test_get_slots_for_missing_patient_returns_404(
    client: AsyncClient,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a_id, _ = two_clinics
    token, _ = encode_scheduling_token(
        patient_id=uuid4(),  # patient that doesn't exist in this clinic
        clinic_id=clinic_a_id,
        outreach_attempt_id=uuid4(),
    )
    r = await client.get(f"/api/schedule/{token}")
    assert r.status_code == 404


async def test_book_slot_creates_appointment_and_marks_attempt_responded(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, provider, attempt, referral = await _seed_patient_provider_attempt(
            db_session, clinic_a_id, with_referral=True
        )

    token, _ = encode_scheduling_token(
        patient_id=patient.id,
        clinic_id=clinic_a_id,
        outreach_attempt_id=attempt.id,
        referral_id=referral.id if referral else None,
    )
    slot = datetime(2026, 6, 1, 14, 0, 0, tzinfo=UTC).isoformat()
    r = await client.post(
        f"/api/schedule/{token}/book",
        json={"slot": slot, "appointment_type": "cardiology_followup"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == AppointmentStatus.scheduled.value
    appt_id = UUID(body["appointment_id"])

    # Verify in DB under clinic-A scope.
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        appt = (
            await db_session.execute(select(Appointment).where(Appointment.id == appt_id))
        ).scalar_one()
        assert appt.provider_id == provider.id
        assert appt.referral_id == referral.id
        assert appt.appointment_type == "cardiology_followup"

        await db_session.refresh(attempt)
        assert attempt.status == OutreachStatus.responded
        assert attempt.outcome["scheduling_link_clicked"] is True
        assert attempt.outcome["appointment_id"] == str(appt_id)
        assert "response_at" in attempt.outcome


async def test_book_slot_falls_back_to_first_internal_provider_when_no_referral(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, provider, attempt, _ = await _seed_patient_provider_attempt(
            db_session, clinic_a_id, with_referral=False
        )

    token, _ = encode_scheduling_token(
        patient_id=patient.id,
        clinic_id=clinic_a_id,
        outreach_attempt_id=attempt.id,
    )
    r = await client.post(
        f"/api/schedule/{token}/book",
        json={"slot": datetime(2026, 6, 2, 9, 0, 0, tzinfo=UTC).isoformat()},
    )
    assert r.status_code == 200, r.text

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        appt = (
            await db_session.execute(
                select(Appointment).where(Appointment.id == UUID(r.json()["appointment_id"]))
            )
        ).scalar_one()
        assert appt.provider_id == provider.id


async def test_book_slot_garbage_token_returns_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/schedule/garbage/book",
        json={"slot": datetime(2026, 6, 1, 14, tzinfo=UTC).isoformat()},
    )
    assert r.status_code == 401


async def test_book_slot_clinic_scoping_appointment_belongs_to_token_clinic(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    """Token issued for clinic A; appointment row must have clinic_id=A
    and must NOT be visible from clinic B's context."""
    clinic_a_id, clinic_b_id = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, _, attempt, _ = await _seed_patient_provider_attempt(db_session, clinic_a_id)

    token, _ = encode_scheduling_token(
        patient_id=patient.id, clinic_id=clinic_a_id, outreach_attempt_id=attempt.id
    )
    r = await client.post(
        f"/api/schedule/{token}/book",
        json={"slot": datetime(2026, 6, 3, 11, tzinfo=UTC).isoformat()},
    )
    assert r.status_code == 200
    appt_id = UUID(r.json()["appointment_id"])

    # Under clinic-B context the tenant guard hides the row.
    with set_clinic_context(clinic_id=clinic_b_id, user_id=test_user):
        rows = (
            await db_session.execute(select(Appointment).where(Appointment.id == appt_id))
        ).scalars().all()
        assert rows == []
