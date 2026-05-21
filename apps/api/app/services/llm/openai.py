"""OpenAIProvider — BYOK opt-in. Lazy-imports `openai` so it's not a hard dep."""

from __future__ import annotations

import os

from app.services.llm.base import LLMProvider

_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(LLMProvider):
    """LLMProvider backed by OpenAI's chat completions API."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        try:
            from openai import AsyncOpenAI  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError(
                "pip install openai to use OpenAIProvider (or unset LLM_PROVIDER to use Ollama)"
            ) from e

        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError("OpenAIProvider requires OPENAI_API_KEY")

        self.model = model or os.getenv("OPENAI_MODEL") or _DEFAULT_MODEL
        self._client = AsyncOpenAI(api_key=resolved_key)

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        return str(content)
