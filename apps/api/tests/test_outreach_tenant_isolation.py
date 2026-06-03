"""HIPAA-class tenant isolation + audit-PHI-safety for the outreach surface."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.utils.security import encode_scheduling_token

pytestmark = pytest.mark.asyncio


async def _seed_attempt(
    db: AsyncSession, clinic_id: UUID, *, status: OutreachStatus = OutreachStatus.pending
) -> tuple[Patient, OutreachAttempt]:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Pat",
        last_name="Isol",
        dob="1970-01-01",
        phone="412-555-0150",
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    db.add(patient)
    await db.flush()
    attempt = OutreachAttempt(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient.id,
        channel=OutreachChannel.sms,
        status=status,
        scheduled_at=datetime.now(UTC),
        outcome={},
        attempt_number=1,
    )
    db.add(attempt)
    await db.commit()
    return patient, attempt


async def test_outreach_attempt_invisible_under_other_clinic_context(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    """Direct SELECT under clinic B's context must return zero rows for
    clinic A's attempt — the SQLAlchemy session-level guard scopes
    every clinic-scoped query."""
    clinic_a_id, clinic_b_id = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        _, attempt = await _seed_attempt(db_session, clinic_a_id)

    with set_clinic_context(clinic_id=clinic_b_id, user_id=test_user):
        rows = (
            (
                await db_session.execute(
                    select(OutreachAttempt).where(OutreachAttempt.id == attempt.id)
                )
            )
            .scalars()
            .all()
        )
    assert rows == []


async def test_outreach_attempt_get_returns_404_cross_clinic(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        _, attempt = await _seed_attempt(db_session, clinic_a_id)

    client_b, headers_b, _ = await authed_client_factory("b")
    r = await client_b.get(f"/api/outreach/{attempt.id}", headers=headers_b)
    assert r.status_code == 404


async def test_outreach_trigger_404_cross_clinic(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    """Clinic B cannot trigger outreach for a clinic-A referral."""
    from app.models.document import UrgencyLevel
    from app.models.referral import Referral, ReferralStatus

    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, _ = await _seed_attempt(db_session, clinic_a_id)
        ref = Referral(
            id=uuid4(),
            clinic_id=clinic_a_id,
            patient_id=patient.id,
            status=ReferralStatus.ready_to_schedule,
            urgency=UrgencyLevel.routine,
        )
        db_session.add(ref)
        await db_session.commit()

    client_b, headers_b, _ = await authed_client_factory("b")
    r = await client_b.post(f"/api/outreach/trigger/referral/{ref.id}", headers=headers_b)
    assert r.status_code == 404


async def test_outreach_patient_history_empty_cross_clinic(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, _ = await _seed_attempt(db_session, clinic_a_id)

    client_b, headers_b, _ = await authed_client_factory("b")
    r = await client_b.get(f"/api/outreach/patient/{patient.id}", headers=headers_b)
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_audit_log_outreach_create_has_no_phi_in_details(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    """The audit row for OutreachAttempt insert must only carry IDs and
    column names — never the patient phone, email, or outcome values."""
    clinic_a_id, _ = two_clinics
    raw_phone = "412-555-9999"

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient = Patient(
            id=uuid4(),
            clinic_id=clinic_a_id,
            first_name="Pat",
            last_name="PhiSafe",
            dob="1970-01-01",
            phone=raw_phone,
            mrn=f"MRN-{uuid4().hex[:6]}",
        )
        db_session.add(patient)
        await db_session.flush()
        attempt = OutreachAttempt(
            id=uuid4(),
            clinic_id=clinic_a_id,
            patient_id=patient.id,
            channel=OutreachChannel.sms,
            status=OutreachStatus.pending,
            scheduled_at=datetime.now(UTC),
            outcome={"some_key": "value"},
            attempt_number=1,
        )
        db_session.add(attempt)
        await db_session.commit()

        audit_rows = (
            (
                await db_session.execute(
                    select(AuditLog).where(
                        AuditLog.resource_type == "outreach_attempts",
                        AuditLog.resource_id == attempt.id,
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(audit_rows) >= 1
    for row in audit_rows:
        details_str = str(row.details or {})
        assert raw_phone not in details_str
        assert "Pat" not in details_str
        assert "PhiSafe" not in details_str


async def test_scheduling_token_clinic_scoping_blocks_cross_clinic_lookup(
    client,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    """A token issued for clinic A, but pointing at a clinic-B patient_id,
    must not reveal clinic-B data. The tenant guard sees clinic A in the
    ContextVar (from the token) and so the clinic-B patient is invisible."""
    clinic_a_id, clinic_b_id = two_clinics
    with set_clinic_context(clinic_id=clinic_b_id, user_id=test_user):
        patient_b, attempt_b = await _seed_attempt(db_session, clinic_b_id)

    # Issue a clinic-A token but with clinic-B patient/attempt ids.
    token, _ = encode_scheduling_token(
        patient_id=patient_b.id,
        clinic_id=clinic_a_id,
        outreach_attempt_id=attempt_b.id,
    )
    r = await client.get(f"/api/schedule/{token}")
    # Patient lookup under clinic-A ContextVar can't see clinic-B patient.
    assert r.status_code == 404
