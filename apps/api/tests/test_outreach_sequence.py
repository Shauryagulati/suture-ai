"""schedule_outreach_sequence — sequence materialization tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discharge_summary import (
    DischargeStatus,
    DischargeSummary,
    UrgencyTier,
)
from app.models.document import UrgencyLevel
from app.models.outreach_attempt import OutreachAttempt, OutreachChannel
from app.models.patient import Patient
from app.models.referral import Referral, ReferralStatus
from app.services.outreach.orchestrator import (
    next_attempt_number_for_referral,
    schedule_outreach_sequence,
)

pytestmark = pytest.mark.asyncio


async def _seed_referral(
    db: AsyncSession,
    clinic_id: UUID,
    *,
    urgency: UrgencyLevel = UrgencyLevel.routine,
) -> Referral:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Pat",
        last_name="Sequence",
        dob="1972-03-10",
        phone="412-555-0150",
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    db.add(patient)
    await db.flush()
    referral = Referral(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient.id,
        status=ReferralStatus.ready_to_schedule,
        urgency=urgency,
    )
    db.add(referral)
    await db.commit()
    return referral


async def _seed_discharge(
    db: AsyncSession,
    clinic_id: UUID,
    *,
    urgency_tier: UrgencyTier = UrgencyTier.critical,
) -> DischargeSummary:
    from datetime import date

    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Pat",
        last_name="Disch",
        dob="1955-07-04",
        phone="412-555-0160",
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    db.add(patient)
    await db.flush()
    discharge = DischargeSummary(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient.id,
        status=DischargeStatus.new,
        urgency_tier=urgency_tier,
        discharge_date=date(2026, 5, 20),
    )
    db.add(discharge)
    await db.commit()
    return discharge


async def test_schedule_sequence_creates_three_attempts_for_routine(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    now = datetime(2026, 6, 1, 9, 0, 0, tzinfo=UTC)
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        referral = await _seed_referral(db_session, clinic_a_id, urgency=UrgencyLevel.routine)
        attempts = await schedule_outreach_sequence(
            db_session, referral=referral, now=now
        )
        await db_session.commit()

    assert len(attempts) == 3
    by_channel = {a.channel: a for a in attempts}
    assert by_channel[OutreachChannel.sms].scheduled_at == now
    # Routine: SMS@0, email@+24h, voice@+48h
    delta_email = (
        by_channel[OutreachChannel.email].scheduled_at - now
    ).total_seconds() / 3600
    delta_voice = (
        by_channel[OutreachChannel.voice].scheduled_at - now
    ).total_seconds() / 3600
    assert delta_email == 24
    assert delta_voice == 48


async def test_schedule_sequence_compresses_for_critical_discharge(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    now = datetime(2026, 6, 1, 9, 0, 0, tzinfo=UTC)
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        discharge = await _seed_discharge(
            db_session, clinic_a_id, urgency_tier=UrgencyTier.critical
        )
        attempts = await schedule_outreach_sequence(
            db_session, discharge=discharge, now=now
        )
        await db_session.commit()

    by_channel = {a.channel: a for a in attempts}
    # Critical: SMS@0, email@+4h, voice@+8h
    delta_email = (
        by_channel[OutreachChannel.email].scheduled_at - now
    ).total_seconds() / 3600
    delta_voice = (
        by_channel[OutreachChannel.voice].scheduled_at - now
    ).total_seconds() / 3600
    assert delta_email == 4
    assert delta_voice == 8


async def test_schedule_sequence_sms_has_scheduling_link_url(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        referral = await _seed_referral(db_session, clinic_a_id)
        attempts = await schedule_outreach_sequence(db_session, referral=referral)
        await db_session.commit()

    by_channel = {a.channel: a for a in attempts}
    assert by_channel[OutreachChannel.sms].scheduling_link_url is not None
    assert "schedule/" in by_channel[OutreachChannel.sms].scheduling_link_url
    # Non-SMS rows defer link generation until send time.
    assert by_channel[OutreachChannel.email].scheduling_link_url is None
    assert by_channel[OutreachChannel.voice].scheduling_link_url is None


async def test_schedule_sequence_idempotent_at_attempt_one(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        referral = await _seed_referral(db_session, clinic_a_id)
        first = await schedule_outreach_sequence(db_session, referral=referral)
        await db_session.commit()
        second = await schedule_outreach_sequence(db_session, referral=referral)
        await db_session.commit()

        rows = (
            (
                await db_session.execute(
                    select(OutreachAttempt).where(
                        OutreachAttempt.referral_id == referral.id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(first) == 3
    assert len(second) == 3
    assert len(rows) == 3
    assert {a.id for a in first} == {a.id for a in second}


async def test_schedule_sequence_re_trigger_with_higher_attempt_number(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        referral = await _seed_referral(db_session, clinic_a_id)
        await schedule_outreach_sequence(db_session, referral=referral)
        await db_session.commit()

        next_n = await next_attempt_number_for_referral(
            db_session, referral_id=referral.id
        )
        assert next_n == 2

        await schedule_outreach_sequence(
            db_session, referral=referral, attempt_number=next_n
        )
        await db_session.commit()

        rows = (
            (
                await db_session.execute(
                    select(OutreachAttempt).where(
                        OutreachAttempt.referral_id == referral.id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 6
    attempt_numbers = sorted({a.attempt_number for a in rows})
    assert attempt_numbers == [1, 2]


async def test_schedule_sequence_requires_exactly_one_parent(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        await schedule_outreach_sequence(db_session)
