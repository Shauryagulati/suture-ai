"""payer_rule_embedding_1024

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-21 12:00:00.000000

Bump payer_rules.embedding from vector(384) (sized for `all-MiniLM-L6-v2`)
to vector(1024) for bge-m3. The column is nullable and currently unpopulated,
so the ALTER uses `USING NULL` — no data conversion needed. ivfflat index is
deferred to Module 4 RAG work. See ADR 007.

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Raw SQL with USING NULL for maximum pgvector-version compatibility:
    # op.alter_column with a pgvector type isn't reliable across versions.
    op.execute("ALTER TABLE payer_rules ALTER COLUMN embedding TYPE vector(1024) USING NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE payer_rules ALTER COLUMN embedding TYPE vector(384) USING NULL")
