"""Anthropic SDK wrapper with on-disk fixture storage.

Naming: `llm_fixtures/` (not `.cache/`) deliberately — the directory holds
COMMITTED test fixtures, not a regenerable cache. The agent reading code
should not be tempted to delete it.

Behavior:
- `generate()` hashes (model, system, prompt, max_tokens, temperature).
- If `llm_fixtures/<sha>.json` exists, returns the cached content. Zero
  network. This is the path CI takes.
- If not, requires `ANTHROPIC_API_KEY`. Calls Anthropic, writes the fixture
  atomically (in_flight/<sha>.tmp → rename), returns content.
- Maintains a cumulative USD cost and raises `CostCapExceeded` if it crosses
  $5.00. Per the plan's Execution Safety Rules, this is a hard stop, not a
  warning.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path


HAIKU_4_5_MODEL = "claude-haiku-4-5-20251001"

# Anthropic Haiku 4.5 pricing (USD per million tokens).
# Source: https://docs.anthropic.com/en/docs/about-claude/pricing
HAIKU_4_5_INPUT_USD_PER_MTOK = 1.00
HAIKU_4_5_OUTPUT_USD_PER_MTOK = 5.00

DEFAULT_COST_CAP_USD = 5.00


class FixtureMissingError(RuntimeError):
    """Raised on cache miss when no ANTHROPIC_API_KEY is available."""


class CostCapExceeded(RuntimeError):
    """Raised mid-run if cumulative USD cost crosses the cap."""


@dataclass
class GenerationResult:
    content: str
    input_tokens: int
    output_tokens: int
    usd_cost: float
    from_fixture: bool


class FixtureBackedClaude:
    """Claude wrapper that prefers committed fixtures over live API calls."""

    def __init__(
        self,
        fixtures_dir: Path,
        *,
        model: str = HAIKU_4_5_MODEL,
        temperature: float = 0.2,
        cost_cap_usd: float = DEFAULT_COST_CAP_USD,
        client: object | None = None,
    ) -> None:
        self.fixtures_dir = fixtures_dir
        self.in_flight_dir = fixtures_dir / "in_flight"
        self.model = model
        self.temperature = temperature
        self.cost_cap_usd = cost_cap_usd
        self.cumulative_cost = 0.0
        self.cumulative_input_tokens = 0
        self.cumulative_output_tokens = 0
        self.api_calls = 0
        self._client = client  # injected for testing; None = lazy-init from env

    def _hash_key(self, system: str, prompt: str, max_tokens: int) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": self.temperature,
                "max_tokens": max_tokens,
                "system": system,
                "prompt": prompt,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _fixture_path(self, sha: str) -> Path:
        return self.fixtures_dir / f"{sha}.json"

    def _get_client(self) -> object:
        if self._client is not None:
            return self._client
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise FixtureMissingError(
                "first-run generation requires ANTHROPIC_API_KEY in the environment "
                "(or .env). Subsequent runs read from committed fixtures and do not "
                "need a key."
            )
        # Lazy import so test environments without the SDK installed still work.
        import anthropic  # type: ignore[import-not-found]

        self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
    ) -> GenerationResult:
        sha = self._hash_key(system, prompt, max_tokens)
        fixture_path = self._fixture_path(sha)
        if fixture_path.exists():
            data = json.loads(fixture_path.read_text(encoding="utf-8"))
            return GenerationResult(
                content=data["content"],
                input_tokens=data["input_tokens"],
                output_tokens=data["output_tokens"],
                usd_cost=data["usd_cost"],
                from_fixture=True,
            )

        # Cache miss → API call. Check cost cap BEFORE calling so we never
        # exceed the cap by even one over-budget call.
        if self.cumulative_cost > self.cost_cap_usd:
            raise CostCapExceeded(
                f"cumulative cost ${self.cumulative_cost:.4f} already exceeds "
                f"cap ${self.cost_cap_usd:.2f}; refusing further API calls"
            )

        client = self._get_client()
        # Anthropic SDK call. Keeping the call shape minimal so the test stub
        # only has to implement `messages.create`.
        response = client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text content. Anthropic SDK returns content blocks.
        content_parts: list[str] = []
        for block in response.content:  # type: ignore[attr-defined]
            text = getattr(block, "text", None)
            if text:
                content_parts.append(text)
        content = "".join(content_parts).strip()

        usage = response.usage  # type: ignore[attr-defined]
        input_tokens = int(usage.input_tokens)
        output_tokens = int(usage.output_tokens)
        usd_cost = (
            input_tokens / 1_000_000 * HAIKU_4_5_INPUT_USD_PER_MTOK
            + output_tokens / 1_000_000 * HAIKU_4_5_OUTPUT_USD_PER_MTOK
        )

        # Update running totals BEFORE writing the fixture, so cap-exceeded
        # state is visible even if the fixture write fails.
        self.cumulative_input_tokens += input_tokens
        self.cumulative_output_tokens += output_tokens
        self.cumulative_cost += usd_cost
        self.api_calls += 1

        if self.cumulative_cost > self.cost_cap_usd:
            raise CostCapExceeded(
                f"cumulative cost ${self.cumulative_cost:.4f} crossed cap "
                f"${self.cost_cap_usd:.2f} after API call (model={self.model}); "
                "halting per execution safety rules"
            )

        # Atomic write: in_flight tmp → final fixture path. The in_flight
        # directory is gitignored; the final path is committed.
        self.in_flight_dir.mkdir(parents=True, exist_ok=True)
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.in_flight_dir / f"{sha}.tmp"
        tmp_path.write_text(
            json.dumps(
                {
                    "model": self.model,
                    "temperature": self.temperature,
                    "max_tokens": max_tokens,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "usd_cost": round(usd_cost, 6),
                    "content": content,
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, fixture_path)

        return GenerationResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usd_cost=usd_cost,
            from_fixture=False,
        )
