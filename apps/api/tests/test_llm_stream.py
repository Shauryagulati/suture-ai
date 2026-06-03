"""Streaming tests for LLMProvider.stream().

Voice agent (Ember / Module 6) needs token streaming for low-latency
TTS. Concrete coverage focuses on the Ollama provider — the default
path the voice agent uses — via httpx MockTransport. BYOK providers
share the same async-iterator contract; we assert the interface holds
without booting their SDKs.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.services.llm.factory import get_llm_provider as _factory
from app.services.llm.ollama import OllamaProvider


@pytest.fixture(autouse=True)
def _clear_llm_factory_cache() -> Iterator[None]:
    _factory.cache_clear()
    yield
    _factory.cache_clear()


def _ollama_with_streaming_mock(
    ndjson_lines: list[dict[str, Any]],
    *,
    model: str = "medgemma1.5",
) -> OllamaProvider:
    """Build an OllamaProvider whose mock transport replies with NDJSON chunks."""
    body = "\n".join(json.dumps(line) for line in ndjson_lines).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=body, headers={"content-type": "application/x-ndjson"})

    provider = OllamaProvider(model=model, base_url="http://mock")
    provider._client = httpx.AsyncClient(
        base_url="http://mock", transport=httpx.MockTransport(handler)
    )
    return provider


@pytest.mark.asyncio
async def test_stream_yields_deltas_in_order() -> None:
    provider = _ollama_with_streaming_mock(
        [
            {"response": "Hello", "done": False},
            {"response": ", ", "done": False},
            {"response": "Sarah", "done": False},
            {"response": ".", "done": False},
            {"response": "", "done": True},
        ]
    )
    chunks = [c async for c in provider.stream(system="s", prompt="p", max_tokens=50)]
    assert chunks == ["Hello", ", ", "Sarah", "."]


@pytest.mark.asyncio
async def test_stream_concatenation_matches_full_response() -> None:
    """The joined stream equals what generate() would return for the same payload."""
    full = "Hello, this is Suture."
    deltas = ["Hello", ", ", "this", " is", " Suture", "."]
    assert "".join(deltas) == full

    provider = _ollama_with_streaming_mock(
        [{"response": d, "done": False} for d in deltas] + [{"response": "", "done": True}]
    )
    chunks = [c async for c in provider.stream(system="s", prompt="p")]
    assert "".join(chunks) == full


@pytest.mark.asyncio
async def test_stream_skips_empty_response_chunks() -> None:
    """Ollama occasionally emits chunks with empty response — must not yield ''."""
    provider = _ollama_with_streaming_mock(
        [
            {"response": "", "done": False},
            {"response": "ok", "done": False},
            {"response": "", "done": False},
            {"response": "", "done": True},
        ]
    )
    chunks = [c async for c in provider.stream(system="s", prompt="p")]
    assert chunks == ["ok"]


@pytest.mark.asyncio
async def test_stream_stops_at_done_true() -> None:
    """Chunks after done=true are ignored (server should not send any, but be safe)."""
    provider = _ollama_with_streaming_mock(
        [
            {"response": "first", "done": False},
            {"response": "", "done": True},
            {"response": "this-must-be-skipped", "done": False},
        ]
    )
    chunks = [c async for c in provider.stream(system="s", prompt="p")]
    assert chunks == ["first"]


def test_llm_provider_abstract_methods_include_stream() -> None:
    """The ABC must mark stream() abstract — every concrete provider implements it."""
    from app.services.llm.base import LLMProvider

    assert "stream" in LLMProvider.__abstractmethods__
    assert "generate" in LLMProvider.__abstractmethods__


def test_all_concrete_providers_implement_stream() -> None:
    """Smoke-check that Ollama/Anthropic/OpenAI override stream() (no ABC error at import)."""
    from app.services.llm.anthropic import AnthropicProvider
    from app.services.llm.ollama import OllamaProvider as _Oll
    from app.services.llm.openai import OpenAIProvider

    for cls in (_Oll, AnthropicProvider, OpenAIProvider):
        assert "stream" not in cls.__abstractmethods__, f"{cls.__name__} did not override stream()"
