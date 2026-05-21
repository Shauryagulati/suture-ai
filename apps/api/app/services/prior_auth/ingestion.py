"""Ingest payer-rules seeds into the `payer_rules` table.

For each payer:
- structured fields come from `<payer>.json` (validated against
  `payer_rule.schema.json` by `seeds.load_payer_json`)
- the markdown narrative is chunked **by procedure section** so each row
  holds both the structured fields AND a self-contained RAG chunk
- chunks are embedded in a single batch via `get_embedding_provider()`

Idempotency: re-running deletes every row for the payer first, then
re-inserts. Safe because `PayerRule` is `GlobalBase` (skips the tenant
guard) and not user-edited.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PayerRule
from app.services.embedding import get_embedding_provider
from app.services.prior_auth.seeds import load_payer_json

# Matches a procedure heading like "### 93458 — LHC with contrast".
# Accepts em-dash, en-dash, or hyphen-minus as the separator (typographic
# variants creep in across the seed files).
_PROCEDURE_HEADING_RE = re.compile(
    r"^###\s+(\d{5})\s*[—–\-]\s*(.+)$",  # noqa: RUF001 — typographic dashes are intentional
    re.MULTILINE,
)


def chunk_markdown_by_procedure(md_text: str) -> dict[str, str]:
    """Split a payer `.md` into one chunk per `### NNNNN — …` section.

    The pre-procedure preamble (payer-level posture, policy notes) is
    prepended to EVERY chunk so each row carries enough payer-level context
    to retrieve sensibly on its own. Returns `{cpt_code: chunk_text}`.
    """
    matches = list(_PROCEDURE_HEADING_RE.finditer(md_text))
    if not matches:
        raise ValueError("no procedure headings (### NNNNN — …) found in markdown")
    preamble = md_text[: matches[0].start()].strip()
    chunks: dict[str, str] = {}
    for i, match in enumerate(matches):
        cpt = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        section = md_text[start:end].strip()
        chunks[cpt] = f"{preamble}\n\n{section}".strip() if preamble else section
    return chunks


async def ingest_payer(
    db: AsyncSession,
    payer_slug: str,
    seeds_root: Path,
) -> int:
    """Ingest one payer pair (`<slug>.json` + `<slug>.md`). Returns row count."""
    json_path = seeds_root / f"{payer_slug}.json"
    md_path = seeds_root / f"{payer_slug}.md"
    seed = load_payer_json(json_path)
    chunks = chunk_markdown_by_procedure(md_path.read_text(encoding="utf-8"))

    missing = [p.cpt_code for p in seed.procedures if p.cpt_code not in chunks]
    if missing:
        raise ValueError(
            f"{payer_slug}.md missing markdown sections for CPTs: {missing}"
        )

    chunk_texts = [chunks[p.cpt_code] for p in seed.procedures]
    embeddings = await get_embedding_provider().embed(chunk_texts)
    if len(embeddings) != len(seed.procedures):
        raise RuntimeError(
            f"embedding provider returned {len(embeddings)} vectors for "
            f"{len(seed.procedures)} chunks"
        )

    # Idempotency: clear this payer's existing rows before re-inserting.
    await db.execute(delete(PayerRule).where(PayerRule.payer_name == seed.payer_name))

    for proc, chunk_text, vec in zip(seed.procedures, chunk_texts, embeddings, strict=True):
        db.add(
            PayerRule(
                payer_name=seed.payer_name,
                procedure_code=proc.cpt_code,
                procedure_name=proc.description,
                auth_required=proc.auth_required,
                required_documents=list(proc.required_documents),
                common_denial_reasons=list(proc.common_denial_reasons),
                typical_turnaround_days=proc.typical_turnaround_days,
                guidelines_text=chunk_text,
                embedding=vec,
            )
        )
    await db.commit()
    return len(seed.procedures)


async def ingest_all(db: AsyncSession, seeds_root: Path) -> dict[str, int]:
    """Ingest every payer `.json`/`.md` pair in `seeds_root`.

    Skips `payer_rule.schema.json`. Returns `{payer_slug: row_count}`.
    """
    counts: dict[str, int] = {}
    for json_path in sorted(seeds_root.glob("*.json")):
        if json_path.name == "payer_rule.schema.json":
            continue
        slug = json_path.stem
        counts[slug] = await ingest_payer(db, slug, seeds_root)
    return counts
