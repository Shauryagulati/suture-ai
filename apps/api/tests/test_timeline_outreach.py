"""Timeline service tests for outreach event integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import UrgencyLevel
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.models.referral import Referral, ReferralStatus
from app.services.workflow.timeline import build_referral_timeline

pytestmark = pytest.mark.asyncio


async def test_build_referral_timeline_includes_outreach_events(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient = Patient(
            id=uuid4(),
            clinic_id=clinic_a_id,
            first_name="Pat",
            last_name="Tl",
            dob="1970-01-01",
            phone="412-555-0150",
            mrn=f"MRN-{uuid4().hex[:6]}",
        )
        db_session.add(patient)
        await db_session.flush()
        referral = Referral(
            id=uuid4(),
            clinic_id=clinic_a_id,
            patient_id=patient.id,
            status=ReferralStatus.ready_to_schedule,
            urgency=UrgencyLevel.routine,
        )
        db_session.add(referral)
        await db_session.flush()
        now = datetime.now(UTC)
        for hours_offset, channel, status, sent_at in [
            (0, OutreachChannel.sms, OutreachStatus.sent, now - timedelta(hours=2)),
            (24, OutreachChannel.email, OutreachStatus.pending, None),
            (48, OutreachChannel.voice, OutreachStatus.pending, None),
        ]:
            db_session.add(
                OutreachAttempt(
                    id=uuid4(),
                    clinic_id=clinic_a_id,
                    patient_id=patient.id,
                    referral_id=referral.id,
                    channel=channel,
                    status=status,
                    scheduled_at=now + timedelta(hours=hours_offset),
                    sent_at=sent_at,
                    outcome={},
                    attempt_number=1,
                )
            )
        await db_session.commit()

        events = await build_referral_timeline(db_session, referral_id=referral.id)

    outreach_events = [e for e in events if e.resource_type == "outreach_attempts"]
    assert len(outreach_events) == 3
    actions = {e.action for e in outreach_events}
    assert actions == {"outreach_sent", "outreach_pending"}
    channels = {e.metadata["channel"] for e in outreach_events}
    assert channels == {"sms", "email", "voice"}


async def test_build_referral_timeline_orders_events_chronologically(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient = Patient(
            id=uuid4(),
            clinic_id=clinic_a_id,
            first_name="Pat",
            last_name="Order",
            dob="1970-01-01",
            phone="412-555-0150",
            mrn=f"MRN-{uuid4().hex[:6]}",
        )
        db_session.add(patient)
        await db_session.flush()
        referral = Referral(
            id=uuid4(),
            clinic_id=clinic_a_id,
            patient_id=patient.id,
            status=ReferralStatus.ready_to_schedule,
            urgency=UrgencyLevel.routine,
        )
        db_session.add(referral)
        await db_session.flush()
        now = datetime.now(UTC)
        for offset in (0, 24, 48):
            db_session.add(
                OutreachAttempt(
                    id=uuid4(),
                    clinic_id=clinic_a_id,
                    patient_id=patient.id,
                    referral_id=referral.id,
                    channel=OutreachChannel.sms,
                    status=OutreachStatus.pending,
                    scheduled_at=now + timedelta(hours=offset),
                    outcome={},
                    attempt_number=1,
                )
            )
        await db_session.commit()

        events = await build_referral_timeline(db_session, referral_id=referral.id)

    timestamps = [e.at for e in events]
    assert timestamps == sorted(timestamps)


async def test_outreach_event_metadata_carries_attempt_number_and_flags(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient = Patient(
            id=uuid4(),
            clinic_id=clinic_a_id,
            first_name="Pat",
            last_name="Meta",
            dob="1970-01-01",
            phone="412-555-0150",
            mrn=f"MRN-{uuid4().hex[:6]}",
        )
        db_session.add(patient)
        await db_session.flush()
        referral = Referral(
            id=uuid4(),
            clinic_id=clinic_a_id,
            patient_id=patient.id,
            status=ReferralStatus.ready_to_schedule,
            urgency=UrgencyLevel.routine,
        )
        db_session.add(referral)
        await db_session.flush()
        db_session.add(
            OutreachAttempt(
                id=uuid4(),
                clinic_id=clinic_a_id,
                patient_id=patient.id,
                referral_id=referral.id,
                channel=OutreachChannel.sms,
                status=OutreachStatus.responded,
                scheduled_at=datetime.now(UTC),
                sent_at=datetime.now(UTC),
                outcome={
                    "scheduling_link_clicked": True,
                    "backfill_offered": False,
                },
                attempt_number=2,
            )
        )
        await db_session.commit()

        events = await build_referral_timeline(db_session, referral_id=referral.id)

    outreach_events = [e for e in events if e.resource_type == "outreach_attempts"]
    assert len(outreach_events) == 1
    md = outreach_events[0].metadata
    assert md["channel"] == "sms"
    assert md["attempt_number"] == 2
    assert md["scheduling_link_clicked"] is True
    assert md["backfill_offered"] is False
