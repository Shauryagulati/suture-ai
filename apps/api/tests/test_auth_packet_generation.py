"""Smoke-test the auth-packet PDF generator.

Builds a full referral + patient + clinic + insurance fixture, then runs
`generate_auth_packet` with a synthetic AuthDetermination so no LLM/
embedding calls are required.
"""

from __future__ import annotations

import io
from uuid import UUID, uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import InsurancePolicy, Patient, Referral, VerificationStatus
from app.services.prior_auth.determine import AuthDetermination, PolicyExcerpt
from app.services.prior_auth.packet import generate_auth_packet
from tests.prior_auth_helpers import cleanup_prior_auth_tables

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def _clean() -> None:
    await cleanup_prior_auth_tables(async_session_maker)
    yield
    await cleanup_prior_auth_tables(async_session_maker)


async def _seed_referral(db: AsyncSession, clinic_id: UUID) -> Referral:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Marcus",
        last_name="Hollowell",
        dob="1958-04-12",
        phone="412-555-0199",
        address_line1="1234 Forbes Ave",
        city="Pittsburgh",
        state="PA",
        zip_code="15217",
        mrn="MRN-PA-2026-001",
    )
    db.add(patient)
    await db.flush()
    db.add(
        InsurancePolicy(
            clinic_id=clinic_id,
            patient_id=patient.id,
            payer_name="Highmark BCBS PA",
            payer_id="HMK",
            member_id="HMK-AB-12345",
            is_primary=True,
            verification_status=VerificationStatus.verified,
        )
    )
    referral = Referral(
        clinic_id=clinic_id,
        patient_id=patient.id,
        procedure_codes=["93458"],
        diagnosis_codes=["I25.10"],
        notes="65 y/o male with stable angina; abnormal stress test 2026-03.",
    )
    db.add(referral)
    await db.commit()
    return referral


def _synthetic_determination() -> AuthDetermination:
    return AuthDetermination(
        auth_required=True,
        confidence=0.9,
        reasoning="Highmark BCBS PA requires prior authorization for 93458 (LHC).",
        required_documents=[
            "Prior non-invasive study (stress, CTA, MPI)",
            "Anginal symptom characterization (CCS class)",
        ],
        typical_turnaround_days=5,
        relevant_policy_excerpts=[
            PolicyExcerpt(
                payer_name="Highmark BCBS PA",
                procedure_code="93458",
                text="Highmark commercial PPO: 93458 requires PA. Documentation must include prior non-invasive testing and symptom characterization.",
                distance=0.12,
            )
        ],
        common_denial_reasons=["no prior non-invasive testing documented"],
    )


async def test_packet_pdf_parses_and_contains_expected_text(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    _clean: None,
) -> None:
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        referral = await _seed_referral(db_session, clinic_a)
        determination = _synthetic_determination()

        pdf_bytes = await generate_auth_packet(db_session, referral.id, determination)

    # Bytes must parse as a PDF.
    assert pdf_bytes.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1

    # Concatenate every page so layout/wrap doesn't hide content.
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    # Patient block
    assert "Hollowell" in full_text
    assert "Marcus" in full_text
    assert "MRN-PA-2026-001" in full_text
    # Payer + procedure
    assert "Highmark" in full_text
    assert "93458" in full_text
    # Required documents checklist
    assert "Non-invasive" in full_text or "non-invasive" in full_text
    # Excerpt attribution
    assert "Highmark BCBS PA, CPT 93458" in full_text
    # Common denial reasons section
    assert "no prior non-invasive testing documented" in full_text


async def test_packet_raises_for_unknown_referral(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    _clean: None,
) -> None:
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        with pytest.raises(ValueError, match=r"referral .* not found"):
            await generate_auth_packet(db_session, uuid4(), _synthetic_determination())
