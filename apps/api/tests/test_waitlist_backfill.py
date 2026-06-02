"""Waitlist backfill — cancel appointment triggers SMS offer to at-risk patients."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, AppointmentStatus
from app.models.document import UrgencyLevel
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.models.provider import Provider, ProviderType
from app.models.referral import Referral, ReferralStatus
from app.services.outreach.backfill import offer_cancelled_slot

pytestmark = pytest.mark.asyncio


async def _seed_patient_and_provider(
    db: AsyncSession, clinic_id: UUID, *, suffix: str
) -> tuple[Patient, Provider]:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name=f"Pat{suffix}",
        last_name="Waitlist",
        dob="1970-01-01",
        phone=f"412-555-01{suffix}",
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    provider = Provider(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Doc",
        last_name="Cardiac",
        npi=f"123456789{suffix[-1]}",
        provider_type=ProviderType.internal,
    )
    db.add_all([patient, provider])
    await db.flush()
    return patient, provider


async def _seed_appointment(
    db: AsyncSession,
    clinic_id: UUID,
    patient: Patient,
    provider: Provider,
    *,
    appointment_type: str = "cardiology_followup",
) -> Appointment:
    appt = Appointment(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient.id,
        provider_id=provider.id,
        appointment_at=datetime.now(UTC) + timedelta(days=2),
        appointment_type=appointment_type,
        status=AppointmentStatus.scheduled,
    )
    db.add(appt)
    await db.flush()
    return appt


async def _seed_ready_to_schedule_referral(
    db: AsyncSession,
    clinic_id: UUID,
    *,
    suffix: str,
    created_at_offset_minutes: int = 0,
) -> Referral:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name=f"Pat{suffix}",
        last_name="AtRisk",
        dob="1970-01-01",
        phone=f"412-555-02{suffix}",
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    db.add(patient)
    await db.flush()
    referral = Referral(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient.id,
        status=ReferralStatus.ready_to_schedule,
        urgency=UrgencyLevel.urgent,
    )
    db.add(referral)
    await db.flush()
    if created_at_offset_minutes:
        # created_at is server_default=now() — override via direct SQL update.
        referral.created_at = datetime.now(UTC) - timedelta(minutes=abs(created_at_offset_minutes))
        await db.flush()
    return referral


async def test_offer_cancelled_slot_creates_backfill_sms_for_oldest_referral(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, provider = await _seed_patient_and_provider(db_session, clinic_a_id, suffix="10")
        appt = await _seed_appointment(db_session, clinic_a_id, patient, provider)
        # Three at-risk patients with different created_at ages.
        for i, age_minutes in enumerate([300, 200, 100]):
            await _seed_ready_to_schedule_referral(
                db_session,
                clinic_a_id,
                suffix=f"{i:02d}",
                created_at_offset_minutes=age_minutes,
            )
        await db_session.commit()

        offers = await offer_cancelled_slot(db_session, appointment_id=appt.id)
        await db_session.commit()

    assert len(offers) == 3
    for o in offers:
        assert o.channel == OutreachChannel.sms
        assert o.status == OutreachStatus.pending
        assert o.outcome["backfill_offered"] is True
        assert o.outcome["cancelled_appointment_id"] == str(appt.id)
        assert o.scheduling_link_url is not None


async def test_offer_cancelled_slot_excludes_appointment_patient(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, provider = await _seed_patient_and_provider(db_session, clinic_a_id, suffix="11")
        appt = await _seed_appointment(db_session, clinic_a_id, patient, provider)
        # The cancelled appointment's patient is ALSO ready_to_schedule
        # (perhaps they have a separate active referral).
        self_referral = Referral(
            id=uuid4(),
            clinic_id=clinic_a_id,
            patient_id=patient.id,
            status=ReferralStatus.ready_to_schedule,
            urgency=UrgencyLevel.urgent,
        )
        db_session.add(self_referral)
        # Plus one other at-risk patient.
        other_ref = await _seed_ready_to_schedule_referral(db_session, clinic_a_id, suffix="12")
        await db_session.commit()

        offers = await offer_cancelled_slot(db_session, appointment_id=appt.id)
        await db_session.commit()

    assert len(offers) == 1
    assert offers[0].referral_id == other_ref.id


async def test_offer_cancelled_slot_respects_top_n(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, provider = await _seed_patient_and_provider(db_session, clinic_a_id, suffix="13")
        appt = await _seed_appointment(db_session, clinic_a_id, patient, provider)
        for i in range(6):
            await _seed_ready_to_schedule_referral(db_session, clinic_a_id, suffix=f"2{i:02d}")
        await db_session.commit()

        offers = await offer_cancelled_slot(db_session, appointment_id=appt.id, top_n=2)
        await db_session.commit()

    assert len(offers) == 2


async def test_cancel_appointment_endpoint_triggers_backfill(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, provider = await _seed_patient_and_provider(db_session, clinic_a_id, suffix="14")
        appt = await _seed_appointment(db_session, clinic_a_id, patient, provider)
        await _seed_ready_to_schedule_referral(db_session, clinic_a_id, suffix="33")
        await db_session.commit()

    client_a, headers_a, _ = await authed_client_factory("a")
    r = await client_a.post(f"/api/appointments/{appt.id}/cancel", headers=headers_a)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == AppointmentStatus.cancelled.value
    assert len(body["backfill_attempt_ids"]) == 1

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await db_session.refresh(appt)
        attempts = (
            (
                await db_session.execute(
                    select(OutreachAttempt).where(
                        OutreachAttempt.id.in_([UUID(s) for s in body["backfill_attempt_ids"]])
                    )
                )
            )
            .scalars()
            .all()
        )
    assert appt.status == AppointmentStatus.cancelled
    assert all(a.outcome["backfill_offered"] is True for a in attempts)


async def test_cancel_appointment_cross_clinic_returns_404(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, provider = await _seed_patient_and_provider(db_session, clinic_a_id, suffix="15")
        appt = await _seed_appointment(db_session, clinic_a_id, patient, provider)
        await db_session.commit()

    client_b, headers_b, _ = await authed_client_factory("b")
    r = await client_b.post(f"/api/appointments/{appt.id}/cancel", headers=headers_b)
    assert r.status_code == 404
