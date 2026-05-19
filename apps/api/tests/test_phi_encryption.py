"""Verify Fernet TypeDecorator: plaintext at ORM, ciphertext at rest."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patient

pytestmark = pytest.mark.asyncio


async def _make_patient(
    db_session: AsyncSession,
    clinic_id: UUID,
    *,
    first_name: str = "Test",
    last_name: str = "Patient",
    dob: str = "1970-01-01",
    phone: str = "555-555-0100",
) -> Patient:
    p = Patient(
        clinic_id=clinic_id,
        first_name=first_name,
        last_name=last_name,
        dob=dob,
        phone=phone,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def test_dob_stored_encrypted(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        patient = await _make_patient(db_session, clinic_a, dob="1965-01-15")

        # Raw SELECT bypasses ORM decryption — must see ciphertext.
        raw = await db_session.execute(
            text("SELECT dob FROM patients WHERE id = :pid").bindparams(pid=patient.id)
        )
        ciphertext = raw.scalar_one()

    assert ciphertext != "1965-01-15", "DOB must not be stored as plaintext"
    # Fernet ciphertext begins with `gAAAAA` (URL-safe-base64 of version + ts).
    assert ciphertext.startswith("gAAAAA"), (
        f"expected Fernet ciphertext prefix, got: {ciphertext[:20]!r}"
    )


async def test_dob_read_decrypted(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        await _make_patient(db_session, clinic_a, dob="1965-01-15", phone="555-1234")

        result = await db_session.execute(select(Patient))
        patient = result.scalars().one()

    # ORM round-trip: decrypted on read.
    assert patient.dob == "1965-01-15"
    assert patient.phone == "555-1234"


async def test_ciphertext_differs_for_same_plaintext(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    """Fernet uses a random IV, so two identical plaintexts produce different ciphertexts."""
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        p1 = await _make_patient(db_session, clinic_a, dob="1965-01-15")
        p2 = await _make_patient(db_session, clinic_a, dob="1965-01-15")

        raw = await db_session.execute(
            text("SELECT id, dob FROM patients WHERE id IN (:a, :b)").bindparams(a=p1.id, b=p2.id)
        )
        ciphertexts = {row.id: row.dob for row in raw}

    assert ciphertexts[p1.id] != ciphertexts[p2.id], (
        "two patients with same DOB plaintext produced identical ciphertext (IV randomness broken)"
    )
