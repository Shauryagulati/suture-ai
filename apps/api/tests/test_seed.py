"""Seed script test — runs seed_dev.py against the test DB, asserts counts.

Also confirms Fernet round-trips the encrypted phone column (stored
ciphertext, ORM read returns plaintext).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Clinic,
    ClinicMembership,
    Patient,
    User,
)

pytestmark = pytest.mark.asyncio


async def test_seed_produces_expected_counts(db_session: AsyncSession) -> None:
    """seed_dev.seed() populates the expected counts and encrypts PHI columns."""
    # Import lazily so the conftest env (PHI key, DB URL) is set before seed
    # touches settings.
    from seeds.scripts.seed_dev import seed

    await seed()

    # Counts.
    clinics = (await db_session.execute(select(func.count()).select_from(Clinic))).scalar_one()
    users = (await db_session.execute(select(func.count()).select_from(User))).scalar_one()
    memberships = (
        await db_session.execute(select(func.count()).select_from(ClinicMembership))
    ).scalar_one()
    # Patient count needs tenant context — wrap in admin sweep via raw count.
    raw_patients = (await db_session.execute(text("SELECT COUNT(*) FROM patients"))).scalar_one()
    raw_providers = (await db_session.execute(text("SELECT COUNT(*) FROM providers"))).scalar_one()

    assert clinics == 2, f"expected 2 clinics, got {clinics}"
    assert users == 6, f"expected 6 users, got {users}"
    assert memberships == 6, f"expected 6 memberships, got {memberships}"
    assert raw_patients == 20, f"expected 20 patients, got {raw_patients}"
    assert raw_providers == 10, f"expected 10 providers, got {raw_providers}"

    # Fernet round-trip: raw ciphertext on disk; ORM read plaintext.
    raw_phones = (
        (await db_session.execute(text("SELECT phone FROM patients LIMIT 5"))).scalars().all()
    )
    for cipher in raw_phones:
        assert cipher.startswith("gAAAAA"), (
            f"seeded patient.phone is not Fernet ciphertext: {cipher[:30]!r}"
        )

    # ORM read via the first clinic context — decrypts.
    first_clinic = (await db_session.execute(select(Clinic))).scalars().first()
    assert first_clinic is not None
    from app.utils.context import current_clinic_id

    token = current_clinic_id.set(first_clinic.id)
    try:
        p = (await db_session.execute(select(Patient))).scalars().first()
        assert p is not None
        assert not p.phone.startswith("gAAAAA"), (
            f"ORM-decrypted phone still looks like ciphertext: {p.phone!r}"
        )
    finally:
        current_clinic_id.reset(token)
