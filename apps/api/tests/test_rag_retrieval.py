"""Exercise the cosine-distance retrieval over `payer_rules`.

Embeddings are inserted directly with sparse unit vectors so the test
verifies the SQL retrieval path independent of any embedding model.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.services.prior_auth.determine import _retrieve_excerpts
from tests.prior_auth_helpers import (
    VECTOR_DIM,
    FakeEmbeddingProvider,
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


async def test_cosine_search_returns_nearest_first(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    _clean: None,
) -> None:
    """The row whose embedding matches the query vector exactly is returned first."""
    # Seed 4 payer rules with distinct one-hot vectors.
    await insert_payer_rule(
        db_session,
        payer_name="Highmark BCBS PA",
        cpt="93458",
        auth_required=True,
        embedding=unit_vector(0),
        guidelines_text="Highmark requires PA for cardiac catheterization (93458).",
    )
    await insert_payer_rule(
        db_session,
        payer_name="Highmark BCBS PA",
        cpt="93306",
        auth_required=False,
        embedding=unit_vector(1),
        guidelines_text="Highmark does not require PA for transthoracic echo (93306).",
    )
    await insert_payer_rule(
        db_session,
        payer_name="UPMC Health Plan",
        cpt="93458",
        auth_required=True,
        embedding=unit_vector(2),
        guidelines_text="UPMC requires PA for LHC (93458).",
    )
    await insert_payer_rule(
        db_session,
        payer_name="Aetna",
        cpt="93458",
        auth_required=True,
        embedding=unit_vector(3),
        guidelines_text="Aetna requires PA for LHC (93458).",
    )

    # Inject an embedding provider whose query vector matches the Highmark/93458 row.
    fake = FakeEmbeddingProvider(vector_fn=lambda _i, _t: unit_vector(0))
    monkeypatch.setattr(
        "app.services.prior_auth.determine.get_embedding_provider",
        lambda: fake,
    )

    results = await _retrieve_excerpts(db_session, "any query — vector is hardcoded", limit=3)
    assert len(results) == 3
    # First result must be the exactly-matching row.
    assert results[0].payer_name == "Highmark BCBS PA"
    assert results[0].procedure_code == "93458"
    assert results[0].distance is not None
    # Distances must be sorted ASC (closest first).
    distances = [r.distance for r in results if r.distance is not None]
    assert distances == sorted(distances)


async def test_cosine_search_skips_rows_without_embedding(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    _clean: None,
) -> None:
    """Rows with NULL embedding must not appear in the result set."""
    from app.models import PayerRule

    # One row with embedding, one without.
    await insert_payer_rule(
        db_session,
        payer_name="Cigna",
        cpt="93458",
        auth_required=True,
        embedding=unit_vector(0),
    )
    db_session.add(
        PayerRule(
            payer_name="UnitedHealthcare",
            procedure_code="93458",
            procedure_name="LHC",
            auth_required=True,
            required_documents=[],
            common_denial_reasons=[],
            typical_turnaround_days=5,
            guidelines_text="(no embedding yet)",
            embedding=None,
        )
    )
    await db_session.commit()

    fake = FakeEmbeddingProvider(vector_fn=lambda _i, _t: unit_vector(0))
    monkeypatch.setattr(
        "app.services.prior_auth.determine.get_embedding_provider",
        lambda: fake,
    )

    results = await _retrieve_excerpts(db_session, "anything", limit=5)
    assert all(r.text != "(no embedding yet)" for r in results)
    assert {r.payer_name for r in results} == {"Cigna"}


async def test_cosine_search_respects_limit(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    _clean: None,
) -> None:
    """`limit=N` must return at most N rows even when more candidates exist."""
    for i in range(5):
        await insert_payer_rule(
            db_session,
            payer_name=f"Payer-{i}",
            cpt="93458",
            auth_required=True,
            embedding=unit_vector(i),
        )

    fake = FakeEmbeddingProvider(vector_fn=lambda _i, _t: unit_vector(0))
    monkeypatch.setattr(
        "app.services.prior_auth.determine.get_embedding_provider",
        lambda: fake,
    )

    results = await _retrieve_excerpts(db_session, "anything", limit=2)
    assert len(results) == 2


_ = VECTOR_DIM  # silence unused-import lint if any
