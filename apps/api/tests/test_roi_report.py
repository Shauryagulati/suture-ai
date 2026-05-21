"""ROI report — date-range aggregation."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DocumentStatus,
    PriorAuthStatus,
    ReferralStatus,
    UrgencyLevel,
)
from app.services.analytics.roi import (
    AVG_VISIT_VALUE_CENTS,
    MANUAL_MINUTES_PER_DOC,
    compute_roi_report,
)
from tests.analytics_helpers import (
    make_appointment,
    make_document,
    make_patient,
    make_prior_auth,
    make_provider,
    make_referral,
)

pytestmark = pytest.mark.asyncio


async def test_documents_processed_and_hours_saved(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        for _ in range(5):
            doc = make_document(clinic_id=clinic_a, status=DocumentStatus.processed)
            db_session.add(doc)
        await db_session.commit()
        report = await compute_roi_report(
            db_session,
            from_date=date.today() - timedelta(days=30),
            to_date=date.today(),
        )
    assert report.documents_processed == 5
    assert report.hours_saved == pytest.approx(5 * MANUAL_MINUTES_PER_DOC / 60)


async def test_revenue_recovered_proportional_to_at_risk(
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
        report = await compute_roi_report(
            db_session,
            from_date=date.today() - timedelta(days=30),
            to_date=date.today(),
        )
    assert report.referrals_at_risk == 3
    assert report.projected_revenue_recovered_cents == 3 * AVG_VISIT_VALUE_CENTS


async def test_approval_rate_only_counts_decided_within_window(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    now = datetime.now(UTC)
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        p = make_patient(clinic_id=clinic_a)
        db_session.add(p)
        await db_session.flush()
        db_session.add(
            make_prior_auth(
                clinic_id=clinic_a,
                patient_id=p.id,
                status=PriorAuthStatus.approved,
                submitted_at=now - timedelta(days=5),
                approved_at=now - timedelta(days=2),
            )
        )
        db_session.add(
            make_prior_auth(
                clinic_id=clinic_a,
                patient_id=p.id,
                status=PriorAuthStatus.denied,
                submitted_at=now - timedelta(days=5),
                denied_at=now - timedelta(days=2),
            )
        )
        db_session.add(
            make_prior_auth(
                clinic_id=clinic_a,
                patient_id=p.id,
                status=PriorAuthStatus.approved,
                submitted_at=now - timedelta(days=120),
                approved_at=now - timedelta(days=90),
            )
        )
        await db_session.commit()
        report = await compute_roi_report(
            db_session,
            from_date=date.today() - timedelta(days=30),
            to_date=date.today(),
        )
    assert report.prior_auth_approval_rate == pytest.approx(0.5)


async def test_avg_days_referral_to_appointment(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        p = make_patient(clinic_id=clinic_a)
        prov = make_provider(clinic_id=clinic_a)
        db_session.add_all([p, prov])
        await db_session.flush()
        ref = make_referral(clinic_id=clinic_a, patient_id=p.id, status=ReferralStatus.scheduled)
        db_session.add(ref)
        await db_session.flush()
        db_session.add(
            make_appointment(
                clinic_id=clinic_a,
                patient_id=p.id,
                provider_id=prov.id,
                referral_id=ref.id,
                days_from_now=10,
            )
        )
        await db_session.commit()
        report = await compute_roi_report(
            db_session,
            from_date=date.today() - timedelta(days=30),
            to_date=date.today(),
        )
    assert report.avg_days_referral_to_appointment is not None
    assert 9 <= report.avg_days_referral_to_appointment <= 11
