"""Verify the denial-appeal PDF generator.

The appeal generator re-runs the determination internally (to recover
policy excerpts), so both LLM and embedding providers are stubbed.
"""

from __future__ import annotations

import io
from uuid import UUID, uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import (
    Patient,
    PriorAuth,
    PriorAuthStatus,
)
from app.services.prior_auth.appeal import generate_denial_appeal
from tests.prior_auth_helpers import (
    FakeEmbeddingProvider,
    FakeLLMProvider,
    cleanup_prior_auth_tables,
    insert_payer_rule,
    unit_vector,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def _clean() -> None:
    await cleanup_prior_auth_tables(async_session_maker)
    yield
    await cleanup_prior_auth_tables(async_session_maker)


async def _seed_denied_prior_auth(db: AsyncSession, clinic_id: UUID) -> PriorAuth:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Eleanor",
        last_name="Ratchett",
        dob="1952-07-04",
        phone="412-555-0144",
        mrn="MRN-APPEAL-001",
    )
    db.add(patient)
    await db.flush()
    prior_auth = PriorAuth(
        clinic_id=clinic_id,
        patient_id=patient.id,
        payer_name="Highmark BCBS PA",
        procedure_codes=["93458"],
        diagnosis_codes=["I25.10"],
        auth_required=True,
        auth_required_reasoning="LHC for stable angina with documented ischemia.",
        status=PriorAuthStatus.denied,
        auth_number="AUTH-XYZ-789",
    )
    db.add(prior_auth)
    await db.commit()
    return prior_auth


async def test_appeal_pdf_parses_and_quotes_denial_reason(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    _clean: None,
) -> None:
    clinic_a, _ = two_clinics
    denial_reason = "Insufficient documentation of failed conservative therapy."

    # Patch determination's providers since appeal re-runs check_prior_auth.
    fake_llm = FakeLLMProvider(
        response_text='{"reasoning": "Procedure meets coverage criteria.", "confidence": 0.85, "supports_structured_result": true}'
    )
    fake_emb = FakeEmbeddingProvider(vector_fn=lambda _i, _t: unit_vector(0))
    monkeypatch.setattr(
        "app.services.prior_auth.determine.get_llm_provider", lambda: fake_llm
    )
    monkeypatch.setattr(
        "app.services.prior_auth.determine.get_embedding_provider", lambda: fake_emb
    )

    # Seed payer_rules so RAG retrieval inside the appeal flow finds something.
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        await insert_payer_rule(
            db_session,
            payer_name="Highmark BCBS PA",
            cpt="93458",
            auth_required=True,
            embedding=unit_vector(0),
            guidelines_text="Highmark commercial PPO requires PA for 93458 with documented non-invasive testing.",
            required_documents=["Non-invasive study"],
            common_denial_reasons=["no prior non-invasive testing"],
            typical_turnaround_days=5,
        )

        prior_auth = await _seed_denied_prior_auth(db_session, clinic_a)
        pdf_bytes = await generate_denial_appeal(db_session, prior_auth.id, denial_reason)

    assert pdf_bytes.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    # Denial reason quoted verbatim.
    assert denial_reason in full_text
    # Patient identity present.
    assert "Ratchett" in full_text
    assert "MRN-APPEAL-001" in full_text
    # Procedure + payer present.
    assert "93458" in full_text
    assert "Highmark" in full_text
    # Auth number from the original submission.
    assert "AUTH-XYZ-789" in full_text


async def test_appeal_raises_for_missing_prior_auth(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    _clean: None,
) -> None:
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        with pytest.raises(ValueError, match=r"prior_auth .* not found"):
            await generate_denial_appeal(db_session, uuid4(), "anything")
