"""Model -> price table + USD cost estimation for ``ai_invocations``.

Local/Ollama models run on-box and are genuinely free ($0). Hosted models
(Anthropic, OpenAI — the BYOK paths) carry published per-million-token
prices. Costs are estimates whenever token counts are estimated (the
``LLMProvider.generate`` interface returns only text, no usage); callers
flag the row via ``confidence_scores["tokens_estimated"]``.

Keeping cost in a table — rather than hardcoding 0.0 at each call site —
means the BYOK paths report real spend and the local default reports a
truthful $0, both derived from the same place.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# (input_usd_per_mtok, output_usd_per_mtok). Matched by case-insensitive
# prefix against ``provider.model`` so versioned ids (e.g. claude-haiku-4-5
# -20251001) resolve. Haiku 4.5 mirrors seeds/scripts/_claude.py.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic Claude (USD per 1M tokens)
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku": (1.00, 5.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-opus": (15.00, 75.00),
    # OpenAI (USD per 1M tokens)
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}

# Local providers (Ollama et al.) run on-box — genuinely $0.
_LOCAL_PREFIXES = ("medgemma", "bge-m3", "llama", "qwen", "mistral", "phi", "gemma", "nomic")


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost for a single call.

    Hosted models price from ``MODEL_PRICING``; local models are $0; unknown
    models return 0.0 and log a warning so a missing price entry is visible
    rather than silently undercounting spend.
    """
    key = model.lower()
    # Longest-prefix wins so "gpt-4o-mini" doesn't match "gpt-4o" first.
    for prefix in sorted(MODEL_PRICING, key=len, reverse=True):
        if key.startswith(prefix):
            in_price, out_price = MODEL_PRICING[prefix]
            return round(
                (prompt_tokens / 1_000_000) * in_price
                + (completion_tokens / 1_000_000) * out_price,
                6,
            )
    if any(key.startswith(p) for p in _LOCAL_PREFIXES):
        return 0.0
    logger.warning("pricing.unknown_model", model=model)
    return 0.0
