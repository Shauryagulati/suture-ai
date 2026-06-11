"""Regression locks for tenant-guard bypass vectors.

The guard uses ``do_orm_execute`` + ``with_loader_criteria`` (not a
compiled-SELECT string interceptor), so it must scope the vectors a naive
interceptor would miss: column-only selects, ``session.get()``, and
aggregate ``count()``. It must also fail closed when no clinic context is
set. These tests promote the security review's throwaway probes into
permanent regression tests so a future refactor can't silently reopen the
bypass.

Reads use a *fresh* session so ``session.get()`` actually issues a query
(a same-session ``get`` would return the identity-map cache and skip the
guard).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.patient import Patient
from app.utils.context import TenantContextMissingError

pytestmark = pytest.mark.asyncio


async def _make_patient(
    db: AsyncSession, clinic_id: UUID, set_clinic_context, *, first_name: str = "Probe"
) -> UUID:
    pid = uuid4()
    with set_clinic_context(clinic_id=clinic_id):
        db.add(
            Patient(
                id=pid,
                clinic_id=clinic_id,
                first_name=first_name,
                last_name="Patient",
                dob="1980-01-01",
                phone="412-555-0000",
            )
        )
        await db.commit()
    return pid


async def test_column_only_select_is_clinic_scoped(
    db_session: AsyncSession, two_clinics: tuple[UUID, UUID], set_clinic_context
) -> None:
    clinic_a, clinic_b = two_clinics
    await _make_patient(db_session, clinic_a, set_clinic_context, first_name="OnlyInA")
    async with async_session_maker() as read:
        with set_clinic_context(clinic_id=clinic_b):
            rows = (await read.execute(select(Patient.first_name))).scalars().all()
    assert "OnlyInA" not in rows
    assert rows == []


async def test_session_get_is_clinic_scoped(
    db_session: AsyncSession, two_clinics: tuple[UUID, UUID], set_clinic_context
) -> None:
    clinic_a, clinic_b = two_clinics
    pid = await _make_patient(db_session, clinic_a, set_clinic_context)
    async with async_session_maker() as read:
        with set_clinic_context(clinic_id=clinic_b):
            got = await read.get(Patient, pid)
    assert got is None


async def test_count_by_column_is_clinic_scoped(
    db_session: AsyncSession, two_clinics: tuple[UUID, UUID], set_clinic_context
) -> None:
    # `count(Patient.id)` references an entity column, so with_loader_criteria
    # injects the clinic filter. This is the form ALL app code uses (verified
    # by grep: extractions/tasks/documents/patients/evals/roi routers).
    clinic_a, clinic_b = two_clinics
    await _make_patient(db_session, clinic_a, set_clinic_context)
    async with async_session_maker() as read:
        with set_clinic_context(clinic_id=clinic_b):
            count = (await read.execute(select(func.count(Patient.id)))).scalar_one()
    assert count == 0


@pytest.mark.xfail(
    reason=(
        "KNOWN LIMITATION: a bare count(*) over select_from(Entity) loads no "
        "entity columns, so with_loader_criteria does not inject the clinic "
        "filter and the count spans clinics (fail-open). App code never uses "
        "this form — it always uses count(Model.id), which IS scoped (see the "
        "test above). Pinned here so the gap is visible and self-corrects to "
        "XPASS if a future guard/SQLAlchemy change closes it. See the "
        "app-layer-tenant-isolation ADR."
    ),
    strict=False,
)
async def test_bare_count_star_should_be_clinic_scoped(
    db_session: AsyncSession, two_clinics: tuple[UUID, UUID], set_clinic_context
) -> None:
    clinic_a, clinic_b = two_clinics
    await _make_patient(db_session, clinic_a, set_clinic_context)
    async with async_session_maker() as read:
        with set_clinic_context(clinic_id=clinic_b):
            count = (await read.execute(select(func.count()).select_from(Patient))).scalar_one()
    assert count == 0  # desired; currently returns 1 (xfail)


async def test_clinic_scoped_select_without_context_raises(
    db_session: AsyncSession,
) -> None:
    # No clinic context set → fail closed, not silent full-table read.
    with pytest.raises(TenantContextMissingError):
        await db_session.execute(select(Patient))
