"""Shared helpers for prior-auth test files.

Provides fake LLM/embedding providers and cleanup utilities. These tests
hit a real Postgres (test DB) so we exercise pgvector cosine search and
the SQLAlchemy tenant guard — but the LLM/embedding HTTP calls are stubbed
so the suite runs without Ollama.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding.base import EmbeddingProvider
from app.services.llm.base import LLMProvider

VECTOR_DIM = 1024


@dataclass
class FakeLLMProvider(LLMProvider):
    """Returns a fixed JSON string for every call. Records call args."""

    response_text: str = '{"reasoning": "test reasoning", "confidence": 0.85, "supports_structured_result": true}'
    model: str = "fake-llm-v0"  # type: ignore[assignment]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def generate(self, *, system: str, prompt: str, max_tokens: int = 1500) -> str:
        self.calls.append({"system": system, "prompt": prompt, "max_tokens": max_tokens})
        return self.response_text


@dataclass
class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic embeddings via a per-text callable.

    Default `vector_fn` derives a stable vector from the SHA-256 of the
    text so semantically similar inputs do NOT cluster — tests that care
    about retrieval ordering must inject a custom `vector_fn`.
    """

    dim: int = VECTOR_DIM
    vector_fn: Callable[[int, str], list[float]] | None = None
    calls: list[list[str]] = field(default_factory=list)

    @property
    def dimension(self) -> int:
        return self.dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        fn = self.vector_fn or _hash_vector(self.dim)
        return [fn(i, t) for i, t in enumerate(texts)]


def _hash_vector(dim: int) -> Callable[[int, str], list[float]]:
    import hashlib

    def fn(_i: int, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Repeat the digest to fill `dim` floats in [-1, 1].
        out: list[float] = []
        while len(out) < dim:
            for b in digest:
                out.append((b - 128) / 128.0)
                if len(out) >= dim:
                    break
        return out

    return fn


def unit_vector(index: int, dim: int = VECTOR_DIM) -> list[float]:
    """Sparse one-hot vector — useful for deterministic cosine-distance tests."""
    v = [0.0] * dim
    v[index % dim] = 1.0
    return v


async def cleanup_prior_auth_tables(session_factory: Any) -> None:
    """Clear every table this feature touches. Run between tests.

    Order matters — FKs are RESTRICT. Children before parents.
    """
    async with session_factory() as cleanup:
        for table in [
            "prior_auth_events",
            "prior_auths",
            "ai_invocations",
            "eligibility_checks",
            "insurance_policies",
            "referrals",
            "documents",
            "payer_rules",
        ]:
            await cleanup.execute(text(f"DELETE FROM {table}"))
        await cleanup.commit()


async def insert_payer_rule(
    db: AsyncSession,
    *,
    payer_name: str,
    cpt: str,
    auth_required: bool,
    embedding: list[float],
    guidelines_text: str = "synthetic rule text",
    required_documents: list[str] | None = None,
    common_denial_reasons: list[str] | None = None,
    typical_turnaround_days: int | None = None,
) -> None:
    """Insert one payer_rules row directly (bypasses the ingestion pipeline)."""
    from app.models import PayerRule

    db.add(
        PayerRule(
            payer_name=payer_name,
            procedure_code=cpt,
            procedure_name=f"{cpt} procedure",
            auth_required=auth_required,
            required_documents=required_documents or [],
            common_denial_reasons=common_denial_reasons or [],
            typical_turnaround_days=typical_turnaround_days,
            guidelines_text=guidelines_text,
            embedding=embedding,
        )
    )
    await db.commit()
