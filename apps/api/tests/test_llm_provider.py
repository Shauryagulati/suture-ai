"""Tests for the LLM provider abstraction (ADR 007).

Covers factory dispatch (defaults to Ollama, BYOK arms require keys) and the
Ollama provider's response handling (markdown-fence stripping, Qwen `<think>`
suppression, JSONExtractionError on garbage).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.services.llm import JSONExtractionError, get_llm_provider
from app.services.llm.factory import get_llm_provider as _factory
from app.services.llm.ollama import OllamaProvider


@pytest.fixture(autouse=True)
def _clear_llm_factory_cache() -> Iterator[None]:
    """lru_cache on the factory must be reset between tests that flip env vars."""
    _factory.cache_clear()
    yield
    _factory.cache_clear()


def _ollama_with_mock(handler: Any, *, model: str = "medgemma1.5") -> OllamaProvider:
    """Build an OllamaProvider whose httpx client is wired to a MockTransport."""
    provider = OllamaProvider(model=model, base_url="http://mock")
    transport = httpx.MockTransport(handler)
    # Replace the real client with one bound to the mock transport.
    provider._client = httpx.AsyncClient(base_url="http://mock", transport=transport)
    return provider


def _fake_response(text: str) -> Any:
    """Return a handler that always responds with `{"response": text}`."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": text})

    return handler


def test_factory_defaults_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)


def test_factory_openai_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        get_llm_provider()


def test_factory_anthropic_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_llm_provider()


async def test_ollama_extract_json_strips_markdown_fence() -> None:
    fenced = '```json\n{"foo": 1, "bar": "baz"}\n```'
    provider = _ollama_with_mock(_fake_response(fenced))
    result = await provider.extract_json(system="s", prompt="p", max_tokens=100)
    assert result == {"foo": 1, "bar": "baz"}


async def test_ollama_extract_json_strips_thinking() -> None:
    # Qwen-style response: thinking block before JSON. Use model="qwen3:8b" so
    # the provider also prepends /no_think on the request side — we assert both.
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        body = '<think>let me reason about this</think>\n{"foo": 1}'
        return httpx.Response(200, json={"response": body})

    provider = _ollama_with_mock(handler, model="qwen3:8b")
    result = await provider.extract_json(system="s", prompt="hello", max_tokens=100)
    assert result == {"foo": 1}
    # /no_think was prepended on the request side
    assert captured["body"]["prompt"].startswith("/no_think\n")


async def test_ollama_extract_json_raises_on_invalid() -> None:
    provider = _ollama_with_mock(_fake_response("not json at all, just prose"))
    with pytest.raises(JSONExtractionError):
        await provider.extract_json(system="s", prompt="p", max_tokens=100)


async def test_ollama_extract_json_requests_constrained_format() -> None:
    # extract_json must use Ollama's `format: json` constrained decoding so small
    # local models can't emit JSON with unescaped newlines. generate() must NOT.
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"response": '{"ok": true}'})

    provider = _ollama_with_mock(handler)
    result = await provider.extract_json(system="s", prompt="p", max_tokens=100)
    assert result == {"ok": True}
    assert captured["body"]["format"] == "json"


async def test_ollama_generate_omits_constrained_format() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"response": "plain text"})

    provider = _ollama_with_mock(handler)
    await provider.generate(system="s", prompt="p", max_tokens=100)
    assert "format" not in captured["body"]
