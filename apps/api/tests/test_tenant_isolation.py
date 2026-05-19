"""The HIPAA-class isolation tests.

Verifies the SQLAlchemy session-level tenant guard:
1. Happy path: clinic A context sees only clinic A rows.
2. **Attack path**: query for clinic B's specific row from clinic A → empty.
3. Missing context: query without ContextVar set → TenantContextMissingError.
4. Insert mismatch: clinic_id != ContextVar → TenantContextMismatchError.

Any failure here is a HIPAA-class bug. Per project operational discipline,
failures STOP the build and require human review before proceeding.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patient
from app.utils.context import (
    TenantContextMismatchError,
    TenantContextMissingError,
)

pytestmark = pytest.mark.asyncio


async def _seed_one_patient_per_clinic(
    db_session: AsyncSession,
    clinic_a: UUID,
    clinic_b: UUID,
    set_clinic_context: object,
) -> tuple[UUID, UUID]:
    """Insert one patient in each clinic. Returns (patient_a_id, patient_b_id)."""
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        pa = Patient(
            clinic_id=clinic_a,
            first_name="A",
            last_name="Patient",
            dob="1970-01-01",
            phone="555-1111",
        )
        db_session.add(pa)
        await db_session.commit()
        await db_session.refresh(pa)
        a_id = pa.id

    with set_clinic_context(clinic_id=clinic_b):  # type: ignore[operator]
        pb = Patient(
            clinic_id=clinic_b,
            first_name="B",
            last_name="Patient",
            dob="1970-01-01",
            phone="555-2222",
        )
        db_session.add(pb)
        await db_session.commit()
        await db_session.refresh(pb)
        b_id = pb.id

    return a_id, b_id


async def test_select_filters_to_current_clinic(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    """Happy path — clinic A context returns only clinic A patients."""
    clinic_a, clinic_b = two_clinics
    a_id, _b_id = await _seed_one_patient_per_clinic(
        db_session, clinic_a, clinic_b, set_clinic_context
    )

    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        result = await db_session.execute(select(Patient))
        rows = result.scalars().all()

    assert len(rows) == 1
    assert rows[0].id == a_id
    assert rows[0].clinic_id == clinic_a


async def test_select_by_id_in_other_clinic_returns_empty(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    """**ATTACK PATH** — clinic A tries to read clinic B's specific patient by ID.

    The guard must inject `WHERE clinic_id = clinic_a` so the result is empty,
    not a leak. This is the load-bearing HIPAA test for the gate.
    """
    clinic_a, clinic_b = two_clinics
    _a_id, b_id = await _seed_one_patient_per_clinic(
        db_session, clinic_a, clinic_b, set_clinic_context
    )

    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        result = await db_session.execute(select(Patient).where(Patient.id == b_id))
        rows = result.scalars().all()

    assert rows == [], f"TENANT LEAK: clinic A read clinic B's patient by ID. Got: {rows}"


async def test_query_without_clinic_context_raises(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    """Fail closed — a clinic-scoped query with no ContextVar set MUST raise."""
    # Insert with context set so we have data to query.
    # Then read without context set.
    from app.utils.context import current_clinic_id

    clinic_a, _ = two_clinics
    token = current_clinic_id.set(clinic_a)
    try:
        db_session.add(
            Patient(
                clinic_id=clinic_a,
                first_name="X",
                last_name="Y",
                dob="1970-01-01",
                phone="555-0000",
            )
        )
        await db_session.commit()
    finally:
        current_clinic_id.reset(token)

    # Now query with no context — must raise, not silently return all rows.
    with pytest.raises(TenantContextMissingError):
        await db_session.execute(select(Patient))


async def test_insert_with_mismatched_clinic_id_rejected(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    """Inserting clinic_id != current_clinic_id must raise."""
    clinic_a, clinic_b = two_clinics
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        bad = Patient(
            clinic_id=clinic_b,  # mismatch
            first_name="bad",
            last_name="row",
            dob="1970-01-01",
            phone="555-0000",
        )
        db_session.add(bad)
        with pytest.raises(TenantContextMismatchError):
            await db_session.flush()
