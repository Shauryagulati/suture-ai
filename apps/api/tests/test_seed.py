"""Seed script test — runs seed_dev.py against the test DB, asserts counts.

Also confirms Fernet round-trips the encrypted phone column (stored
ciphertext, ORM read returns plaintext).
"""

from __future__ import annotations

from uuid import uuid4

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
    # 6 clinic users (3 roles x 2 clinics) + 1 sentinel Ember voice-agent user.
    assert users == 7, f"expected 7 users, got {users}"
    # Memberships stay 6 — the Ember agent user has no clinic membership.
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


async def test_seed_idempotent_when_foreign_clinic_present(db_session: AsyncSession) -> None:
    """seed() must operate only on the clinics it owns.

    Regression: seed fetched ALL clinics (`select(Clinic)`) and created an
    admin@<slug> user for every one — including the `eval-harness` clinic left
    behind by `make eval-extraction`. clear_seed only knows the two seed slugs,
    so it couldn't remove that stray user, and the next `make seed` crashed on
    a duplicate admin@eval-harness.example.com.
    """
    from seeds.scripts.seed_dev import seed

    # Simulate the state left by `make eval-extraction`: a foreign clinic with
    # its own admin user that the seed script does not manage.
    db_session.add(Clinic(id=uuid4(), name="Eval Harness (synthetic)", slug="eval-harness"))
    await db_session.flush()
    db_session.add(
        User(
            id=uuid4(),
            email="admin@eval-harness.example.com",
            hashed_password="!disabled-no-login",
            full_name="Admin Eval Harness (synthetic)",
        )
    )
    await db_session.commit()

    # Must not raise. The buggy version raised IntegrityError trying to insert a
    # second admin@eval-harness user.
    await seed()

    slugs = set((await db_session.execute(select(Clinic.slug))).scalars().all())
    # seed created the clinics it owns...
    assert {"steel-city-cardiology", "allegheny-valley-heart"} <= slugs
    # ...and left the foreign clinic + its single admin user untouched.
    assert "eval-harness" in slugs
    dupes = (
        await db_session.execute(
            select(func.count())
            .select_from(User)
            .where(User.email == "admin@eval-harness.example.com")
        )
    ).scalar_one()
    assert dupes == 1, f"seed created a duplicate eval-harness admin: {dupes} rows"
