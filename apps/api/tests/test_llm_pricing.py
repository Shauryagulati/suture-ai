"""Unit tests for the model -> price table + cost estimation."""

from __future__ import annotations

import pytest

from app.services.llm.pricing import estimate_cost_usd


def test_local_model_is_free() -> None:
    # Ollama/local models run on-box — genuinely $0.
    assert estimate_cost_usd("medgemma1.5", 1000, 1000) == 0.0
    assert estimate_cost_usd("bge-m3", 1000, 1000) == 0.0


def test_unknown_model_is_zero() -> None:
    assert estimate_cost_usd("some-mystery-model", 1000, 1000) == 0.0


def test_hosted_model_is_nonzero() -> None:
    # Haiku 4.5: $1.00/Mtok in, $5.00/Mtok out → 1M in + 1M out = $6.00.
    assert estimate_cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000) == pytest.approx(6.0)


def test_hosted_cost_scales_with_tokens() -> None:
    small = estimate_cost_usd("claude-haiku-4-5", 1000, 1000)
    big = estimate_cost_usd("claude-haiku-4-5", 10_000, 10_000)
    assert small > 0
    assert big == pytest.approx(small * 10)
