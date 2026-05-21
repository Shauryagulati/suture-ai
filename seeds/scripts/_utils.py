"""Shared helpers for synthetic-data generators.

All values produced here are deterministic given a seed — re-running the same
generator with the same `--seed` MUST yield byte-identical output. This is the
core reproducibility guarantee for the eval corpus.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from faker import Faker

# Stable namespace for UUID5 derivations. Do NOT change — would break any
# downstream code that relied on these IDs.
_SUTURE_NAMESPACE = uuid.UUID("c0bb1ed1-7e57-4c0d-b1e5-d0c9be9e57ed")


def make_faker(seed: int) -> Faker:
    """Return a seeded Faker. Locale en_US to keep names/addresses stable."""
    fake = Faker("en_US")
    Faker.seed(seed)
    # Reset .unique state so repeated runs at the same seed see the same exhaustion.
    fake.unique.clear()
    return fake


def deterministic_uuid(seed: int, key: str) -> uuid.UUID:
    """Stable UUID5 derived from (seed, key). Same inputs → same UUID forever."""
    return uuid.uuid5(_SUTURE_NAMESPACE, f"{seed}:{key}")


def write_json(path: Path, data: Any) -> None:
    """Write JSON with sorted keys, 2-space indent, trailing newline.

    Sort + indent are non-negotiable: they keep diffs reviewable across runs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


# Regex matches "<LABEL>: <value>" where LABEL is something that should ALREADY
# be a structured field in the eval ground truth. If the LLM-generated narrative
# duplicates these, the extraction harness gets a free easy hit.
_PHI_KEYWORD_RE = re.compile(
    r"\b(SSN|MRN|Member\s*ID|NPI|DOB)\s*[:#=]\s*\S",
    flags=re.IGNORECASE,
)


def assert_no_phi_keywords(text: str, *, where: str) -> None:
    """Guard: clinical prose must not restate structured fields with their labels.

    Catches a class of LLM-duplication bugs where the generator says
    "MRN: 12345" inside the narrative, which would make extraction-from-prose
    trivially easy and corrupt the eval signal. Structured fields belong in
    the structured section of the PDF, not the narrative.

    Raises ValueError on hit — the caller's job to re-prompt or re-seed.
    """
    match = _PHI_KEYWORD_RE.search(text)
    if match:
        raise ValueError(
            f"narrative for {where} contains structured-field label "
            f"({match.group(0)!r}); regenerate with a stronger negative instruction"
        )


@contextmanager
def run_log(log_path: Path, generator_name: str) -> Iterator["_RunLogCtx"]:
    """Append a run record to seeds/scripts/generation.log.

    Records: timestamp, generator name, total wall time, item count, cost in USD.
    NEVER logs generated content body — only counts and metadata. This matches
    the project-wide PHI-safe-logging discipline (CLAUDE.md): even synthetic
    narratives stay out of logs.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ctx = _RunLogCtx(generator_name)
    start = time.monotonic()
    try:
        yield ctx
    finally:
        elapsed = time.monotonic() - start
        line = (
            f"{datetime.now(UTC).isoformat(timespec='seconds')}  "
            f"generator={generator_name}  "
            f"items={ctx.items}  "
            f"api_calls={ctx.api_calls}  "
            f"input_tokens={ctx.input_tokens}  "
            f"output_tokens={ctx.output_tokens}  "
            f"usd_cost={ctx.usd_cost:.4f}  "
            f"elapsed_sec={elapsed:.2f}\n"
        )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)


class _RunLogCtx:
    """Accumulator passed into the `run_log` context."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.items = 0
        self.api_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.usd_cost = 0.0


# Repo paths — derived once so callers don't sprinkle Path arithmetic.
REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDS_ROOT = REPO_ROOT / "seeds"
DATA_DIR = SEEDS_ROOT / "data"
DOCUMENTS_DIR = SEEDS_ROOT / "documents"
SCHEMAS_DIR = SEEDS_ROOT / "schemas"
PAYER_RULES_DIR = SEEDS_ROOT / "payer_rules"
LLM_FIXTURES_DIR = SEEDS_ROOT / "scripts" / "llm_fixtures"
GENERATION_LOG = SEEDS_ROOT / "scripts" / "generation.log"
