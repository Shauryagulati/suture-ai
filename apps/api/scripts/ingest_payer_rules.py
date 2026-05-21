"""CLI: ingest payer rules into the local Postgres.

Reads `seeds/payer_rules/*.json` + matching `.md`, embeds each markdown
chunk via the configured embedding provider, and writes one row per
(payer, CPT) into `payer_rules`. Idempotent — re-running clears and
re-inserts per payer.

Run via `make ingest-payer-rules`.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.database import async_session_maker
from app.services.prior_auth.ingestion import ingest_all

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SEEDS_ROOT = _REPO_ROOT / "seeds" / "payer_rules"


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("ingest_payer_rules")
    if not _SEEDS_ROOT.exists():
        raise FileNotFoundError(f"seeds dir not found: {_SEEDS_ROOT}")

    async with async_session_maker() as db:
        counts = await ingest_all(db, _SEEDS_ROOT)

    total = sum(counts.values())
    log.info("ingested %d rules across %d payers", total, len(counts))
    for slug, n in counts.items():
        log.info("  %s: %d", slug, n)


if __name__ == "__main__":
    asyncio.run(_main())
