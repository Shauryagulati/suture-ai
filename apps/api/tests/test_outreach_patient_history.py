"""GET /api/outreach/patient/{patient_id} — aggregation across referrals."""

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

pytestmark = pytest.mark.asyncio


async def test_patient_history_aggregates_across_referrals(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    """Two referrals for the same patient → patient history should show
    all attempts across both, ordered newest-first."""
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient = Patient(
            id=uuid4(),
            clinic_id=clinic_a_id,
            first_name="Pat",
            last_name="History",
            dob="1970-01-01",
            phone="412-555-0150",
            mrn=f"MRN-{uuid4().hex[:6]}",
        )
        db_session.add(patient)
        await db_session.flush()

        now = datetime.now(UTC)
        for ref_offset_days in (0, 30):
            referral = Referral(
                id=uuid4(),
                clinic_id=clinic_a_id,
                patient_id=patient.id,
                status=ReferralStatus.ready_to_schedule,
                urgency=UrgencyLevel.routine,
            )
            db_session.add(referral)
            await db_session.flush()
            for ch_offset, channel in enumerate(
                (OutreachChannel.sms, OutreachChannel.email, OutreachChannel.voice)
            ):
                db_session.add(
                    OutreachAttempt(
                        id=uuid4(),
                        clinic_id=clinic_a_id,
                        patient_id=patient.id,
                        referral_id=referral.id,
                        channel=channel,
                        status=OutreachStatus.pending,
                        scheduled_at=now - timedelta(days=ref_offset_days, hours=ch_offset),
                        outcome={},
                        attempt_number=1,
                    )
                )
        await db_session.commit()

    client_a, headers_a, _ = await authed_client_factory("a")
    r = await client_a.get(f"/api/outreach/patient/{patient.id}", headers=headers_a)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 6
    # Newest-first ordering.
    timestamps = [item["scheduled_at"] for item in body["items"]]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_patient_history_empty_for_unknown_patient(
    authed_client_factory,
) -> None:
    client_a, headers_a, _ = await authed_client_factory("a")
    r = await client_a.get(f"/api/outreach/patient/{uuid4()}", headers=headers_a)
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_patient_history_isolated_to_clinic(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    """Clinic A's patient outreach history must not surface to clinic B."""
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient = Patient(
            id=uuid4(),
            clinic_id=clinic_a_id,
            first_name="Pat",
            last_name="Isolated",
            dob="1970-01-01",
            phone="412-555-0150",
            mrn=f"MRN-{uuid4().hex[:6]}",
        )
        db_session.add(patient)
        await db_session.flush()
        db_session.add(
            OutreachAttempt(
                id=uuid4(),
                clinic_id=clinic_a_id,
                patient_id=patient.id,
                channel=OutreachChannel.sms,
                status=OutreachStatus.pending,
                scheduled_at=datetime.now(UTC),
                outcome={},
                attempt_number=1,
            )
        )
        await db_session.commit()

    client_b, headers_b, _ = await authed_client_factory("b")
    r = await client_b.get(f"/api/outreach/patient/{patient.id}", headers=headers_b)
    assert r.status_code == 200
    assert r.json()["items"] == []
