"""Test the three-step prior-auth determination pipeline.

Stubs the LLM with a fixed JSON response and the embedding provider with
deterministic unit vectors. The real cosine search + structured lookup
run against Postgres.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import AiInvocation, InvocationType
from app.services.prior_auth.determine import (
    AuthCheckRequest,
    check_prior_auth,
)
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


def _patch_providers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    llm_response: str,
    embedding_fn: object,
) -> tuple[FakeLLMProvider, FakeEmbeddingProvider]:
    fake_llm = FakeLLMProvider(response_text=llm_response)
    fake_emb = FakeEmbeddingProvider(vector_fn=embedding_fn)  # type: ignore[arg-type]
    monkeypatch.setattr(
        "app.services.prior_auth.determine.get_llm_provider", lambda: fake_llm
    )
    monkeypatch.setattr(
        "app.services.prior_auth.determine.get_embedding_provider", lambda: fake_emb
    )
    return fake_llm, fake_emb


async def _seed_highmark_rules(db: AsyncSession) -> None:
    """Seed the two Highmark rows needed for the test cases below."""
    await insert_payer_rule(
        db,
        payer_name="Highmark BCBS PA",
        cpt="93458",
        auth_required=True,
        embedding=unit_vector(0),
        guidelines_text="Highmark requires PA for cardiac catheterization (93458). Documentation must include non-invasive study results and CCS class.",
        required_documents=["Non-invasive study", "CCS class characterization"],
        common_denial_reasons=["no prior non-invasive testing", "stable symptoms"],
        typical_turnaround_days=5,
    )
    await insert_payer_rule(
        db,
        payer_name="Highmark BCBS PA",
        cpt="93306",
        auth_required=False,
        embedding=unit_vector(1),
        guidelines_text="Highmark does not require PA for transthoracic echo (93306) under typical office billing.",
        required_documents=["Order with ICD-10"],
        common_denial_reasons=["repeat study within 90 days"],
        typical_turnaround_days=None,
    )


async def test_check_returns_auth_required_for_lhc(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    _clean: None,
) -> None:
    clinic_a, _ = two_clinics
    await _seed_highmark_rules(db_session)

    _patch_providers(
        monkeypatch,
        llm_response='{"reasoning": "PA is required for LHC.", "confidence": 0.9, "supports_structured_result": true}',
        embedding_fn=lambda _i, _t: unit_vector(0),
    )

    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        result = await check_prior_auth(
            db_session,
            AuthCheckRequest(
                payer_name="Highmark BCBS PA",
                procedure_codes=["93458"],
                diagnosis_codes=["I25.10"],
            ),
        )

    assert result.auth_required is True
    assert result.confidence == pytest.approx(0.9, abs=1e-3)
    assert result.typical_turnaround_days == 5
    assert "Non-invasive study" in result.required_documents
    assert "no prior non-invasive testing" in result.common_denial_reasons
    assert len(result.relevant_policy_excerpts) > 0
    assert result.relevant_policy_excerpts[0].payer_name == "Highmark BCBS PA"


async def test_check_returns_no_auth_for_echo(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    _clean: None,
) -> None:
    clinic_a, _ = two_clinics
    await _seed_highmark_rules(db_session)

    _patch_providers(
        monkeypatch,
        llm_response='{"reasoning": "TTE does not require PA.", "confidence": 0.85, "supports_structured_result": true}',
        embedding_fn=lambda _i, _t: unit_vector(1),
    )

    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        result = await check_prior_auth(
            db_session,
            AuthCheckRequest(
                payer_name="Highmark BCBS PA",
                procedure_codes=["93306"],
                diagnosis_codes=["I50.9"],
            ),
        )

    assert result.auth_required is False
    assert result.typical_turnaround_days is None


async def test_check_logs_ai_invocation_row(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    _clean: None,
) -> None:
    """Every determination must insert an ai_invocations row for the call."""
    clinic_a, _ = two_clinics
    await _seed_highmark_rules(db_session)

    _patch_providers(
        monkeypatch,
        llm_response='{"reasoning": "x", "confidence": 0.7, "supports_structured_result": true}',
        embedding_fn=lambda _i, _t: unit_vector(0),
    )

    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        await check_prior_auth(
            db_session,
            AuthCheckRequest(payer_name="Highmark BCBS PA", procedure_codes=["93458"]),
        )

        rows = (
            await db_session.execute(
                select(AiInvocation).where(
                    AiInvocation.invocation_type == InvocationType.auth_check
                )
            )
        ).scalars().all()

    assert len(rows) == 1
    row = rows[0]
    assert row.model == "fake-llm-v0"
    assert row.latency_ms >= 0
    assert row.confidence_scores.get("auth_check") == pytest.approx(0.7, abs=1e-3)
    assert row.output_summary == "auth_required=True"


async def test_check_falls_back_when_llm_returns_garbage(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    _clean: None,
) -> None:
    """If the LLM returns un-parseable text, the structured rule still drives the answer."""
    clinic_a, _ = two_clinics
    await _seed_highmark_rules(db_session)

    _patch_providers(
        monkeypatch,
        llm_response="this is not JSON, just prose without any braces or brackets",
        embedding_fn=lambda _i, _t: unit_vector(0),
    )

    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        result = await check_prior_auth(
            db_session,
            AuthCheckRequest(payer_name="Highmark BCBS PA", procedure_codes=["93458"]),
        )

    # Structured fields still correct, reasoning is the fallback string.
    assert result.auth_required is True
    assert result.confidence == pytest.approx(0.5, abs=1e-3)  # matched-fallback path
    assert "Fallback" in result.reasoning
