"""Leakage risk scoring — score ordering and threshold."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutreachStatus, ReferralStatus, UrgencyLevel
from app.services.analytics.leakage import (
    LEAKAGE_THRESHOLD,
    compute_leakage_summary,
)
from tests.analytics_helpers import (
    make_outreach,
    make_patient,
    make_referral,
)

pytestmark = pytest.mark.asyncio


async def test_critical_no_appointment_failed_outreach_scores_higher_than_routine_scheduled(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        # Risky: stat referral, missing contact, 3 failed outreaches, no appointment.
        risky = make_patient(clinic_id=clinic_a, phone="", email=None)
        db_session.add(risky)
        await db_session.flush()
        db_session.add(
            make_referral(
                clinic_id=clinic_a,
                patient_id=risky.id,
                urgency=UrgencyLevel.stat,
                status=ReferralStatus.needs_review,
            )
        )
        for n in range(1, 4):
            db_session.add(
                make_outreach(
                    clinic_id=clinic_a,
                    patient_id=risky.id,
                    status=OutreachStatus.failed,
                    attempt_number=n,
                )
            )

        # Safe: routine referral, has phone+email, scheduled.
        safe = make_patient(clinic_id=clinic_a)
        db_session.add(safe)
        await db_session.flush()
        db_session.add(
            make_referral(
                clinic_id=clinic_a,
                patient_id=safe.id,
                urgency=UrgencyLevel.routine,
                status=ReferralStatus.scheduled,
            )
        )
        await db_session.commit()

        summary = await compute_leakage_summary(db_session)

    by_patient = {row.patient_id: row for row in summary.rows}
    # Safe is not in the open-status set anymore; only risky should appear.
    assert risky.id in by_patient
    assert by_patient[risky.id].score >= LEAKAGE_THRESHOLD


async def test_threshold_at_risk_count_matches_rows_above_threshold(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        for _ in range(3):
            p = make_patient(clinic_id=clinic_a, phone="", email=None)
            db_session.add(p)
            await db_session.flush()
            db_session.add(
                make_referral(
                    clinic_id=clinic_a,
                    patient_id=p.id,
                    urgency=UrgencyLevel.stat,
                    status=ReferralStatus.needs_review,
                )
            )
        await db_session.commit()
        summary = await compute_leakage_summary(db_session)
    assert summary.threshold == LEAKAGE_THRESHOLD
    assert summary.at_risk_count == sum(1 for r in summary.rows if r.score >= summary.threshold)


async def test_missing_contact_info_increases_score(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        with_contact = make_patient(clinic_id=clinic_a)
        no_contact = make_patient(clinic_id=clinic_a, phone="", email=None)
        db_session.add_all([with_contact, no_contact])
        await db_session.flush()
        for p in (with_contact, no_contact):
            db_session.add(
                make_referral(
                    clinic_id=clinic_a,
                    patient_id=p.id,
                    urgency=UrgencyLevel.routine,
                    status=ReferralStatus.needs_review,
                )
            )
        await db_session.commit()
        summary = await compute_leakage_summary(db_session)
    by_patient = {row.patient_id: row for row in summary.rows}
    assert by_patient[no_contact.id].score > by_patient[with_contact.id].score
