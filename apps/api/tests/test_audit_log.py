"""Verify the SQLAlchemy after_insert/update/delete listener writes audit rows
with no PHI in `details`."""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLog, Patient

pytestmark = pytest.mark.asyncio


async def test_patient_create_writes_audit_row(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: object,
) -> None:
    """Creating a Patient must emit an audit_logs row with correct shape."""
    clinic_a, _ = two_clinics
    actor_user_id = test_user

    with set_clinic_context(  # type: ignore[operator]
        clinic_id=clinic_a, user_id=actor_user_id
    ):
        patient = Patient(
            clinic_id=clinic_a,
            first_name="Jane",
            last_name="Doe",
            dob="1965-01-15",
            phone="555-867-5309",
        )
        db_session.add(patient)
        await db_session.commit()

    # Read audit_logs under the writer's clinic context — audit reads are
    # clinic-scoped like any other ClinicScopedBase model (the guard requires
    # a context and filters by clinic_id).
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        rows = (
            (await db_session.execute(select(AuditLog).where(AuditLog.resource_type == "patients")))
            .scalars()
            .all()
        )

    assert len(rows) == 1
    row = rows[0]
    assert row.action == AuditAction.create
    assert row.resource_type == "patients"
    assert row.resource_id == patient.id
    assert row.clinic_id == clinic_a
    assert row.user_id == actor_user_id


async def test_audit_details_contains_no_phi(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: object,
) -> None:
    """`audit_logs.details` must never serialize PHI values.

    Sweep the JSON for known PHI markers from the inserted patient.
    """
    clinic_a, _ = two_clinics
    sensitive_first = "Jane"
    sensitive_phone = "555-867-5309"
    sensitive_dob = "1965-01-15"

    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):  # type: ignore[operator]
        db_session.add(
            Patient(
                clinic_id=clinic_a,
                first_name=sensitive_first,
                last_name="Doe",
                dob=sensitive_dob,
                phone=sensitive_phone,
            )
        )
        await db_session.commit()

    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        rows = (
            (await db_session.execute(select(AuditLog).where(AuditLog.resource_type == "patients")))
            .scalars()
            .all()
        )

    for row in rows:
        as_json = json.dumps(row.details)
        for phi in (sensitive_first, sensitive_phone, sensitive_dob):
            assert phi not in as_json, f"PHI '{phi}' leaked into audit_logs.details: {as_json}"


async def test_null_clinic_audit_row_not_visible_under_clinic_context(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    """A NULL-clinic system audit row is written but NOT visible via the ORM
    under a clinic context — audit reads are clinic-scoped (the guard's
    `clinic_id == cid` excludes NULL). Locks in the corrected behavior; the
    docstring previously (wrongly) claimed the guard treats NULL as visible."""
    from app.database import async_session_maker

    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        db_session.add(
            AuditLog(
                clinic_id=None,
                action=AuditAction.view,
                resource_type="system_marker",
                details={},
            )
        )
        await db_session.commit()

    async with async_session_maker() as read:
        with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
            rows = (
                (
                    await read.execute(
                        select(AuditLog).where(AuditLog.resource_type == "system_marker")
                    )
                )
                .scalars()
                .all()
            )
    assert rows == []
