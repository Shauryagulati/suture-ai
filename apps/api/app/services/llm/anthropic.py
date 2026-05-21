"""AnthropicProvider — BYOK opt-in. Lazy-imports `anthropic`.

Distinct from `seeds/scripts/_claude.py` (which is sync, Haiku-only, fixture-cached
for synthetic-data generation). This provider is async and intended for runtime
application calls under the BYOK abstraction.
"""

from __future__ import annotations

import os

from app.services.llm.base import LLMProvider

_DEFAULT_MODEL = "claude-sonnet-4-5"


class AnthropicProvider(LLMProvider):
    """LLMProvider backed by Anthropic's Messages API."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "pip install anthropic to use AnthropicProvider"
                " (or unset LLM_PROVIDER to use Ollama)"
            ) from e

        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError("AnthropicProvider requires ANTHROPIC_API_KEY")

        self.model = model or os.getenv("ANTHROPIC_MODEL") or _DEFAULT_MODEL
        self._client = anthropic.AsyncAnthropic(api_key=resolved_key)

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
    ) -> str:
        message = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        parts: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(str(text))
        return "".join(parts)
