"""EmbeddingProvider abstract class.

Providers implement `embed(texts)` (batch) and expose `dimension`. The
`embed_query` single-string helper is concrete on the base.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract embedding interface. Concrete providers implement `embed`."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension produced by `embed`."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text."""

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""
        vectors = await self.embed([query])
        return vectors[0]
