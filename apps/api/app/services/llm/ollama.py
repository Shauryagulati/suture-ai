"""OllamaProvider — local LLM via the Ollama HTTP API (default provider).

Defaults to MedGemma 1.5 4B. For Qwen models, prepends `/no_think` to the prompt
AND regex-strips any `<think>...</think>` blocks from the response — belt and
suspenders, since Qwen sometimes ignores `/no_think`.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.services.llm.base import LLMProvider, parse_json_or_raise

_DEFAULT_MODEL = "medgemma1.5"
_DEFAULT_BASE_URL = "http://localhost:11434"
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class OllamaProvider(LLMProvider):
    """LLMProvider backed by a local Ollama server."""

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model or os.getenv("OLLAMA_MODEL") or _DEFAULT_MODEL
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL") or _DEFAULT_BASE_URL
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    def _is_qwen(self) -> bool:
        return self.model.lower().startswith("qwen")

    def _maybe_no_think(self, prompt: str) -> str:
        return f"/no_think\n{prompt}" if self._is_qwen() else prompt

    def _maybe_strip_thinking(self, text: str) -> str:
        return _THINK_BLOCK_RE.sub("", text) if self._is_qwen() else text

    async def _post_generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int,
        fmt: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "prompt": self._maybe_no_think(prompt),
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if fmt is not None:
            # Ollama constrained decoding: `"format": "json"` guarantees the
            # response is syntactically valid JSON. Small local models (e.g.
            # MedGemma 4B) otherwise emit JSON with unescaped newlines inside
            # string values, which breaks `json.loads`. See extract_json.
            payload["format"] = fmt
        response = await self._client.post("/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        text: str = data.get("response", "")
        return self._maybe_strip_thinking(text)

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
    ) -> str:
        return await self._post_generate(
            system=system, prompt=prompt, max_tokens=max_tokens
        )

    async def extract_json(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        """Extract JSON using Ollama's constrained `format: json` decoding.

        Overrides the base (which calls plain `generate`) so structured
        extraction is reliable on small local models. Parsing is still the
        shared `parse_json_or_raise` so fence/thinking-block stripping and the
        dict-check behave identically to every other provider.
        """
        raw = await self._post_generate(
            system=system, prompt=prompt, max_tokens=max_tokens, fmt="json"
        )
        return parse_json_or_raise(raw)

    async def stream(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 500,
    ) -> AsyncIterator[str]:
        """Stream text deltas from `/api/generate?stream=true`.

        Ollama emits one JSON object per line: `{"response": "...", "done": false}`
        with a terminal `{"done": true}`. We yield the `response` field of each
        non-empty chunk.

        Qwen `<think>` blocks are NOT filtered on the streaming path — voice
        callers should pick a non-thinking model (medgemma default, or
        explicitly disable thinking with `/no_think`, which we still prepend
        for Qwen).
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "prompt": self._maybe_no_think(prompt),
            "stream": True,
            "options": {"num_predict": max_tokens},
        }
        async with self._client.stream("POST", "/api/generate", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                chunk = data.get("response", "")
                if chunk:
                    yield chunk
                if data.get("done"):
                    return

    async def aclose(self) -> None:
        await self._client.aclose()
