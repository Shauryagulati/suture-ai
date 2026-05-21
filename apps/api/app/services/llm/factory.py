"""LLM provider factory — env-driven, cached.

`get_llm_provider()` returns the single process-wide provider instance based on
the `LLM_PROVIDER` env var. Cached with `lru_cache` so providers (and their
underlying httpx / SDK clients) are reused. Tests reset the cache via the
autouse `_reset_provider_cache` fixture in `tests/conftest.py`.
"""

from __future__ import annotations

import functools
import os

from app.services.llm.base import LLMProvider
from app.services.llm.ollama import OllamaProvider

_DEFAULT_PROVIDER = "ollama"


@functools.lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """Return the configured LLMProvider. Defaults to Ollama if LLM_PROVIDER unset."""
    name = os.getenv("LLM_PROVIDER", _DEFAULT_PROVIDER).lower()

    if name == "ollama":
        return OllamaProvider()

    if name == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
        from app.services.llm.openai import OpenAIProvider

        return OpenAIProvider()

    if name == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        from app.services.llm.anthropic import AnthropicProvider

        return AnthropicProvider()

    raise ValueError(f"Unknown LLM_PROVIDER={name!r}; expected one of: ollama, openai, anthropic")
