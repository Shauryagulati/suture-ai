"""Embedding provider factory — env-driven, cached.

`get_embedding_provider()` returns the single process-wide instance based on
the `EMBEDDING_PROVIDER` env var (default `"ollama"`). Tests reset the cache
via an autouse fixture.
"""

from __future__ import annotations

import functools
import os

from app.services.embedding.base import EmbeddingProvider
from app.services.embedding.ollama import OllamaEmbeddingProvider

_DEFAULT_PROVIDER = "ollama"


@functools.lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured EmbeddingProvider. Defaults to Ollama (bge-m3)."""
    name = os.getenv("EMBEDDING_PROVIDER", _DEFAULT_PROVIDER).lower()

    if name == "ollama":
        return OllamaEmbeddingProvider()

    raise ValueError(f"Unknown EMBEDDING_PROVIDER={name!r}; expected: ollama")
