"""Tests for the embedding provider abstraction (ADR 007)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.services.embedding import get_embedding_provider
from app.services.embedding.factory import get_embedding_provider as _factory
from app.services.embedding.ollama import OllamaEmbeddingProvider


@pytest.fixture(autouse=True)
def _clear_embedding_factory_cache() -> Iterator[None]:
    _factory.cache_clear()
    yield
    _factory.cache_clear()


def test_embedding_factory_defaults_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    provider = get_embedding_provider()
    assert isinstance(provider, OllamaEmbeddingProvider)
    assert provider.dimension == 1024
