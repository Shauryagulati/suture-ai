"""Provider-agnostic embedding access.

Every embedding call in application code goes through `get_embedding_provider()`.
Defaults to bge-m3 via Ollama (1024-dim). See ADR 007.
"""

from __future__ import annotations

from app.services.embedding.base import EmbeddingProvider
from app.services.embedding.factory import get_embedding_provider

__all__ = ["EmbeddingProvider", "get_embedding_provider"]
