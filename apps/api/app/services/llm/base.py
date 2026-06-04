"""LLMProvider abstract class + JSON-extraction helpers shared by all providers.

Providers only implement `generate()`. Markdown-fence stripping, `<think>` block
stripping, and JSON parsing all live here so every provider gets the same
hardening and one test covers all of them.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


class JSONExtractionError(Exception):
    """Raised when an LLM response cannot be parsed as JSON."""

    def __init__(self, raw_text: str, cause: Exception | None = None) -> None:
        self.raw_text = raw_text
        self.cause = cause
        preview = raw_text[:200].replace("\n", "\\n")
        suffix = f" (cause: {cause})" if cause is not None else ""
        super().__init__(f"could not parse LLM response as JSON{suffix} | preview={preview!r}")


def _strip_to_json(text: str) -> str:
    """Strip thinking blocks, markdown fences, and leading/trailing prose."""
    cleaned = _THINK_BLOCK_RE.sub("", text).strip()

    fence_match = _FENCE_RE.match(cleaned)
    if fence_match is not None:
        cleaned = fence_match.group(1).strip()

    # Trim leading/trailing prose by finding the outermost JSON braces/brackets.
    first_obj = cleaned.find("{")
    first_arr = cleaned.find("[")
    candidates = [i for i in (first_obj, first_arr) if i != -1]
    if not candidates:
        return cleaned
    start = min(candidates)
    if cleaned[start] == "{":
        end = cleaned.rfind("}")
    else:
        end = cleaned.rfind("]")
    if end == -1 or end < start:
        return cleaned
    return cleaned[start : end + 1]


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token).

    Used to populate ``ai_invocations`` token counts when the provider doesn't
    surface exact usage (the ``generate``/``extract_json`` interface returns only
    text). Callers that use this MUST flag the row as estimated so cost reporting
    can distinguish it from exact provider usage. Better than logging 0, which
    reads as "we don't track cost at all."
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def parse_json_or_raise(raw: str) -> dict[str, Any]:
    """Strip wrappers from `raw` and parse it as a JSON object.

    Shared by every provider's `extract_json` so the strip + parse + dict-check
    behaviour is identical regardless of how the raw text was produced (plain
    generation, or constrained-decoding modes like Ollama `format: json`).
    Raises JSONExtractionError on malformed JSON or a non-object top level.
    """
    candidate = _strip_to_json(raw)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise JSONExtractionError(raw, cause=e) from e
    if not isinstance(parsed, dict):
        raise JSONExtractionError(
            raw, cause=TypeError(f"expected dict, got {type(parsed).__name__}")
        )
    return parsed


class LLMProvider(ABC):
    """Abstract LLM interface. Concrete providers implement `generate`."""

    model: str

    @abstractmethod
    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
    ) -> str:
        """Return the raw text response. No parsing, no stripping."""

    @abstractmethod
    def stream(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 500,
    ) -> AsyncIterator[str]:
        """Yield text deltas as the LLM produces them.

        Used by the voice agent (Module 6 / Ember) for low-latency replies
        — the TTS pipeline can start synthesizing on the first chunk
        instead of waiting for the full utterance.

        Subclasses implement this as an `async def` generator so the
        return type is implicitly an `AsyncIterator[str]`.
        """

    async def extract_json(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        """Call `generate`, strip wrappers, parse JSON. Raise JSONExtractionError on failure."""
        raw = await self.generate(system=system, prompt=prompt, max_tokens=max_tokens)
        return parse_json_or_raise(raw)
