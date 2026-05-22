"""Payer friction — per-payer turnaround + approval rate + denial reasons."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriorAuthEvent, PriorAuthEventType, PriorAuthStatus
from app.services.analytics.payer_friction import compute_payer_friction
from tests.analytics_helpers import make_patient, make_prior_auth

pytestmark = pytest.mark.asyncio


async def test_avg_turnaround_and_approval_rate(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    now = datetime.now(UTC)
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        patient = make_patient(clinic_id=clinic_a)
        db_session.add(patient)
        await db_session.flush()
        db_session.add(
            make_prior_auth(
                clinic_id=clinic_a,
                patient_id=patient.id,
                payer_name="UPMC Health Plan",
                status=PriorAuthStatus.approved,
                submitted_at=now - timedelta(days=5),
                approved_at=now - timedelta(days=2),
            )
        )
        db_session.add(
            make_prior_auth(
                clinic_id=clinic_a,
                patient_id=patient.id,
                payer_name="UPMC Health Plan",
                status=PriorAuthStatus.approved,
                submitted_at=now - timedelta(days=10),
                approved_at=now - timedelta(days=5),
            )
        )
        db_session.add(
            make_prior_auth(
                clinic_id=clinic_a,
                patient_id=patient.id,
                payer_name="UPMC Health Plan",
                status=PriorAuthStatus.denied,
                submitted_at=now - timedelta(days=10),
                denied_at=now - timedelta(days=3),
            )
        )
        db_session.add(
            make_prior_auth(
                clinic_id=clinic_a,
                patient_id=patient.id,
                payer_name="UPMC Health Plan",
                status=PriorAuthStatus.submitted,
                submitted_at=now - timedelta(days=1),
            )
        )
        await db_session.commit()
        summary = await compute_payer_friction(db_session)

    upmc = next(r for r in summary.rows if r.payer_name == "UPMC Health Plan")
    assert upmc.total_auths == 4
    assert upmc.approved == 2
    assert upmc.denied == 1
    assert upmc.pending == 1
    assert upmc.approval_rate == pytest.approx(2 / 3)
    assert upmc.avg_turnaround_days == pytest.approx((3 + 5 + 7) / 3)


async def test_top_denial_reasons_from_events(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        patient = make_patient(clinic_id=clinic_a)
        db_session.add(patient)
        await db_session.flush()
        pa1 = make_prior_auth(
            clinic_id=clinic_a,
            patient_id=patient.id,
            payer_name="Highmark BCBS",
            status=PriorAuthStatus.denied,
        )
        pa2 = make_prior_auth(
            clinic_id=clinic_a,
            patient_id=patient.id,
            payer_name="Highmark BCBS",
            status=PriorAuthStatus.denied,
        )
        db_session.add_all([pa1, pa2])
        await db_session.flush()
        db_session.add(
            PriorAuthEvent(
                clinic_id=clinic_a,
                prior_auth_id=pa1.id,
                event_type=PriorAuthEventType.denied,
                details={"reason": "Missing medical necessity"},
            )
        )
        db_session.add(
            PriorAuthEvent(
                clinic_id=clinic_a,
                prior_auth_id=pa2.id,
                event_type=PriorAuthEventType.denied,
                details={"reason": "Missing medical necessity"},
            )
        )
        await db_session.commit()
        summary = await compute_payer_friction(db_session)

    hm = next(r for r in summary.rows if r.payer_name == "Highmark BCBS")
    assert hm.top_denial_reasons[0] == "Missing medical necessity"


async def test_no_decided_auths_yields_none_for_turnaround(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        patient = make_patient(clinic_id=clinic_a)
        db_session.add(patient)
        await db_session.flush()
        db_session.add(
            make_prior_auth(
                clinic_id=clinic_a,
                patient_id=patient.id,
                payer_name="Aetna",
                status=PriorAuthStatus.submitted,
            )
        )
        await db_session.commit()
        summary = await compute_payer_friction(db_session)
    aetna = next(r for r in summary.rows if r.payer_name == "Aetna")
    assert aetna.avg_turnaround_days is None
    assert aetna.approval_rate == 0.0
