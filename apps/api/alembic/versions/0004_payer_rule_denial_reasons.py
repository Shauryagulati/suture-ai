"""payer_rule_denial_reasons

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-21 18:00:00.000000

Add `common_denial_reasons` (text array) to `payer_rules`. The structured
seed JSON already carries this field; it joins the RAG corpus so the
determination service can surface it without an extra LLM round-trip.

No backfill: existing rows are unpopulated and will be re-inserted by the
ingestion pipeline. Server default `'{}'` keeps the column non-null even
during the small window after the ALTER and before re-ingest.

Vector index on `embedding` is still deferred — 25 rows in v1 makes seq
scan strictly faster than IVFFlat/HNSW. Revisit past ~1K rows.

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payer_rules",
        sa.Column(
            "common_denial_reasons",
            sa.ARRAY(sa.String()),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("payer_rules", "common_denial_reasons")
