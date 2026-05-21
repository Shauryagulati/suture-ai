"""OllamaEmbeddingProvider — local embeddings via Ollama (default).

Defaults to bge-m3 (1024-dim, hybrid dense+sparse, 8K context).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.services.embedding.base import EmbeddingProvider

_DEFAULT_MODEL = "bge-m3"
_DEFAULT_BASE_URL = "http://localhost:11434"
_BGE_M3_DIMENSION = 1024


class OllamaEmbeddingProvider(EmbeddingProvider):
    """EmbeddingProvider backed by a local Ollama server."""

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        dimension: int = _BGE_M3_DIMENSION,
    ) -> None:
        self.model = model or os.getenv("EMBEDDING_MODEL") or _DEFAULT_MODEL
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL") or _DEFAULT_BASE_URL
        self._dimension = dimension
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {"model": self.model, "input": texts}
        response = await self._client.post("/api/embed", json=payload)
        response.raise_for_status()
        data = response.json()
        embeddings: list[list[float]] = data["embeddings"]
        return embeddings

    async def aclose(self) -> None:
        await self._client.aclose()
