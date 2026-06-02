"""Patient + ReferringProvider resolver tests (Phase 1c)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider import Provider, ProviderType
from app.services.extraction.resolvers import (
    ExtractionResolverError,
    resolve_or_create_patient,
    resolve_or_create_referring_provider,
)

pytestmark = pytest.mark.asyncio


def _patient_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "first_name": "Amy",
        "last_name": "Robinson",
        "dob": "1966-03-13",
        "mrn": "MRN-654235",
        "phone": "412-555-1234",
        "address_line1": "33890 Jennifer Squares",
        "city": "Pittsburgh",
        "state": "PA",
        "zip_code": "15222",
    }
    base.update(overrides)
    return base


def _provider_dict(**overrides: Any) -> dict[str, Any]:
    base = {
        "first_name": "Shawn",
        "last_name": "Flowers",
        "npi": "2423884966",
        "practice_name": "Greater Pittsburgh Primary Care",
        "practice_phone": "878-555-6543",
        "practice_fax": "878-555-7517",
    }
    base.update(overrides)
    return base


# ---------------------------- Patient ----------------------------


async def test_patient_creates_when_mrn_not_found(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: Any,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, created = await resolve_or_create_patient(db_session, _patient_dict())
        assert created is True
        assert patient.id is not None
        assert patient.mrn == "MRN-654235"
        assert patient.first_name == "Amy"
        # Encrypted columns round-trip via the EncryptedString TypeDecorator.
        assert patient.dob == "1966-03-13"
        assert patient.phone == "412-555-1234"
        await db_session.commit()


async def test_patient_returns_existing_match(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: Any,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        first, _ = await resolve_or_create_patient(db_session, _patient_dict())
        await db_session.commit()
        # Same MRN, different last_name in extraction — must still resolve to the same row.
        second, created = await resolve_or_create_patient(
            db_session, _patient_dict(last_name="DifferentName")
        )
        assert created is False
        assert second.id == first.id
        assert second.last_name == "Robinson"  # original wins; resolver does not mutate.


async def test_patient_creates_when_mrn_missing(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: Any,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, created = await resolve_or_create_patient(db_session, _patient_dict(mrn=None))
        assert created is True
        assert patient.mrn is None
        await db_session.commit()


@pytest.mark.parametrize("missing", ["first_name", "last_name", "dob", "phone"])
async def test_patient_missing_required_raises(
    missing: str,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: Any,
) -> None:
    clinic_a_id, _ = two_clinics
    payload = _patient_dict(mrn=None, **{missing: None})
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        with pytest.raises(ExtractionResolverError) as exc:
            await resolve_or_create_patient(db_session, payload)
        assert f"patient.{missing}" in str(exc.value)


async def test_patient_tenant_isolated_lookup(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: Any,
) -> None:
    """Clinic B must NOT see a Patient with the same MRN that exists in clinic A."""
    clinic_a_id, clinic_b_id = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await resolve_or_create_patient(db_session, _patient_dict())
        await db_session.commit()

    with set_clinic_context(clinic_id=clinic_b_id, user_id=test_user):
        patient_b, created = await resolve_or_create_patient(db_session, _patient_dict())
        assert created is True  # tenant guard hid clinic A's row; we created a new one in B
        assert patient_b.clinic_id == clinic_b_id
        await db_session.commit()


# ---------------------------- Provider ----------------------------


async def test_provider_creates_when_npi_not_found(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: Any,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        provider, created = await resolve_or_create_referring_provider(db_session, _provider_dict())
        assert created is True
        assert provider is not None
        assert provider.npi == "2423884966"
        assert provider.provider_type == ProviderType.referring
        await db_session.commit()


async def test_provider_returns_existing_match(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: Any,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        first, _ = await resolve_or_create_referring_provider(db_session, _provider_dict())
        await db_session.commit()
        second, created = await resolve_or_create_referring_provider(db_session, _provider_dict())
        assert created is False
        assert second is not None
        assert second.id == first.id


async def test_provider_returns_none_when_no_npi(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: Any,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        provider, created = await resolve_or_create_referring_provider(
            db_session, _provider_dict(npi=None)
        )
        assert provider is None
        assert created is False


@pytest.mark.parametrize("missing", ["first_name", "last_name"])
async def test_provider_missing_required_raises(
    missing: str,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: Any,
) -> None:
    clinic_a_id, _ = two_clinics
    payload = _provider_dict(**{missing: None})
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        with pytest.raises(ExtractionResolverError) as exc:
            await resolve_or_create_referring_provider(db_session, payload)
        assert f"referring_provider.{missing}" in str(exc.value)


async def test_provider_lookup_filtered_by_referring_type(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context: Any,
) -> None:
    """An internal provider with the same NPI must NOT shadow the referring lookup."""
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        db_session.add(
            Provider(
                first_name="Internal",
                last_name="Doc",
                npi="2423884966",
                provider_type=ProviderType.internal,
            )
        )
        await db_session.commit()

        provider, created = await resolve_or_create_referring_provider(db_session, _provider_dict())
        assert created is True
        assert provider is not None
        assert provider.provider_type == ProviderType.referring

        # Verify both rows now exist in the clinic.
        rows = (await db_session.execute(select(Provider))).scalars().all()
        types = sorted(p.provider_type.value for p in rows)
        assert types == ["internal", "referring"]
