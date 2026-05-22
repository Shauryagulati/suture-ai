"""Patient + Provider resolvers for extraction approval.

These run when a human approves an extraction. They look up an existing
row by stable identifier (MRN for patients, NPI for providers) or build
a new row from the extracted fields. **Neither resolver commits** — the
caller (approval endpoint) owns the transaction.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.models.provider import Provider, ProviderType


class ExtractionResolverError(ValueError):
    """A required field for resolution is missing or invalid."""


def _required(extracted: dict[str, Any], key: str, *, parent: str) -> str:
    value = extracted.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ExtractionResolverError(f"{parent}.{key} is required to create a row")
    if not isinstance(value, str):
        raise ExtractionResolverError(f"{parent}.{key} must be a string, got {type(value).__name__}")
    return value.strip()


def _optional_str(extracted: dict[str, Any], key: str) -> str | None:
    value = extracted.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


async def resolve_or_create_patient(
    db: AsyncSession, extracted_patient: dict[str, Any]
) -> tuple[Patient, bool]:
    """Return ``(patient, was_created)``.

    Lookup by ``mrn`` (plaintext, tenant-guarded). Falls through to creation
    when MRN is missing or no row matches. Raises ``ExtractionResolverError``
    if required fields (first_name, last_name, dob, phone) are missing for
    the create path.
    """
    mrn = _optional_str(extracted_patient, "mrn")
    if mrn:
        existing = (
            await db.execute(select(Patient).where(Patient.mrn == mrn))
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False

    first_name = _required(extracted_patient, "first_name", parent="patient")
    last_name = _required(extracted_patient, "last_name", parent="patient")
    dob = _required(extracted_patient, "dob", parent="patient")
    phone = _required(extracted_patient, "phone", parent="patient")

    patient = Patient(
        first_name=first_name,
        last_name=last_name,
        dob=dob,
        phone=phone,
        mrn=mrn,
        address_line1=_optional_str(extracted_patient, "address_line1"),
        city=_optional_str(extracted_patient, "city"),
        state=_optional_str(extracted_patient, "state"),
        zip_code=_optional_str(extracted_patient, "zip_code"),
    )
    db.add(patient)
    await db.flush()
    return patient, True


async def resolve_or_create_referring_provider(
    db: AsyncSession, extracted_provider: dict[str, Any]
) -> tuple[Provider | None, bool]:
    """Return ``(provider, was_created)`` or ``(None, False)`` if no NPI was extracted.

    Returning ``None`` is intentional: ``Referral.referring_provider_id`` is
    nullable, so an approved referral with an unknown provider stays valid.
    Raises ``ExtractionResolverError`` if NPI is present but provider names
    are missing.
    """
    npi = _optional_str(extracted_provider, "npi")
    if not npi:
        return None, False

    existing = (
        await db.execute(
            select(Provider).where(
                Provider.npi == npi,
                Provider.provider_type == ProviderType.referring,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    first_name = _required(extracted_provider, "first_name", parent="referring_provider")
    last_name = _required(extracted_provider, "last_name", parent="referring_provider")

    provider = Provider(
        first_name=first_name,
        last_name=last_name,
        npi=npi,
        provider_type=ProviderType.referring,
        practice_name=_optional_str(extracted_provider, "practice_name"),
        practice_phone=_optional_str(extracted_provider, "practice_phone"),
        practice_fax=_optional_str(extracted_provider, "practice_fax"),
    )
    db.add(provider)
    await db.flush()
    return provider, True
