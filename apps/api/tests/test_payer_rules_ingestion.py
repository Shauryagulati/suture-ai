"""Verify the payer-rules ingestion pipeline.

Mocks the embedding provider so the test does not need Ollama running.
Runs against the real `seeds/payer_rules/` corpus so we exercise the
markdown chunker on the actual content.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import PayerRule
from app.services.prior_auth.ingestion import (
    chunk_markdown_by_procedure,
    ingest_all,
)
from tests.prior_auth_helpers import (
    VECTOR_DIM,
    FakeEmbeddingProvider,
    cleanup_prior_auth_tables,
)

pytestmark = pytest.mark.asyncio

_SEEDS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "seeds" / "payer_rules"
_EXPECTED_CPTS = {"93015", "93306", "93458", "93620", "93224"}
_EXPECTED_PAYERS = {
    "Highmark BCBS PA",
    "UPMC Health Plan",
    "Aetna",
    "Cigna",
    "UnitedHealthcare",
}


@pytest.fixture
async def _clean_payer_rules() -> None:
    """Wipe payer_rules + ai_invocations before and after each test."""
    await cleanup_prior_auth_tables(async_session_maker)
    yield
    await cleanup_prior_auth_tables(async_session_maker)


@pytest.fixture
def fake_embedding(monkeypatch: pytest.MonkeyPatch) -> FakeEmbeddingProvider:
    """Patch the embedding provider used by ingestion.py."""
    fake = FakeEmbeddingProvider()
    monkeypatch.setattr(
        "app.services.prior_auth.ingestion.get_embedding_provider",
        lambda: fake,
    )
    return fake


async def test_chunk_markdown_by_procedure_finds_all_5_cpts() -> None:
    md = (_SEEDS_ROOT / "highmark.md").read_text(encoding="utf-8")
    chunks = chunk_markdown_by_procedure(md)
    assert set(chunks.keys()) == _EXPECTED_CPTS
    # Each chunk includes the payer-level preamble plus the procedure section,
    # so it should be longer than a bare heading line.
    for cpt, body in chunks.items():
        assert len(body) > 200, f"chunk for {cpt} is too short: {len(body)}"


async def test_chunk_markdown_raises_on_no_headings() -> None:
    with pytest.raises(ValueError, match="no procedure headings"):
        chunk_markdown_by_procedure("# Random markdown\n\nNo procedure headings here.")


async def test_ingest_all_inserts_25_rows(
    db_session: AsyncSession,
    fake_embedding: FakeEmbeddingProvider,
    _clean_payer_rules: None,
) -> None:
    """Real seeds: 5 payers x 5 procedures = 25 rows, all embedded."""
    counts = await ingest_all(db_session, _SEEDS_ROOT)
    assert sum(counts.values()) == 25
    assert len(counts) == 5

    rows = (await db_session.execute(select(PayerRule))).scalars().all()
    assert len(rows) == 25

    # Every row has an embedding of the configured dim.
    for row in rows:
        assert row.embedding is not None, f"missing embedding on {row.payer_name}/{row.procedure_code}"
        assert len(row.embedding) == VECTOR_DIM

    # Every (payer, CPT) cell is present.
    matrix = {(r.payer_name, r.procedure_code) for r in rows}
    assert {p for p, _ in matrix} == _EXPECTED_PAYERS
    for payer in _EXPECTED_PAYERS:
        for cpt in _EXPECTED_CPTS:
            assert (payer, cpt) in matrix


async def test_ingest_all_is_idempotent(
    db_session: AsyncSession,
    fake_embedding: FakeEmbeddingProvider,
    _clean_payer_rules: None,
) -> None:
    """Re-running clears + re-inserts — still exactly 25 rows."""
    await ingest_all(db_session, _SEEDS_ROOT)
    await ingest_all(db_session, _SEEDS_ROOT)
    count = (await db_session.execute(select(PayerRule))).scalars().all()
    assert len(count) == 25


async def test_ingest_structured_fields_match_seeds(
    db_session: AsyncSession,
    fake_embedding: FakeEmbeddingProvider,
    _clean_payer_rules: None,
) -> None:
    """Structured fields from the .json must round-trip into payer_rules."""
    await ingest_all(db_session, _SEEDS_ROOT)
    # Highmark + 93458 is a known PA-required row with documents + denials.
    row = (
        await db_session.execute(
            select(PayerRule).where(
                PayerRule.payer_name == "Highmark BCBS PA",
                PayerRule.procedure_code == "93458",
            )
        )
    ).scalar_one()
    assert row.auth_required is True
    assert row.typical_turnaround_days == 5  # max of [3, 5] per the JSON
    assert any("Anginal" in doc or "CCS class" in doc for doc in row.required_documents)
    assert any("non-invasive" in reason or "CCS" in reason for reason in row.common_denial_reasons)

    # Highmark + 93306 (echo) has no PA required.
    echo = (
        await db_session.execute(
            select(PayerRule).where(
                PayerRule.payer_name == "Highmark BCBS PA",
                PayerRule.procedure_code == "93306",
            )
        )
    ).scalar_one()
    assert echo.auth_required is False
    assert echo.typical_turnaround_days is None  # 0 in JSON collapses to None


# Avoid pytest warning about unused UUID import; keeping the file
# self-contained for future tests.
_ = UUID  # type: ignore[func-returns-value]
