"""encrypt call_transcripts.full_transcript

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-22 09:00:00.000000

Swap `call_transcripts.full_transcript` from plain `Text` to the
`EncryptedString` TypeDecorator (Fernet symmetric encryption at the
ORM boundary). PHI at rest per CLAUDE.md.

Guard: refuses to run if the table already has rows. Existing rows
would be plaintext and would fail Fernet decryption after the swap,
silently orphaning PHI. The dev / test DB is always empty here; any
non-empty table needs a separate re-encryption migration first (see
docs/SECURITY.md key-rotation runbook).

The SQL column type change (TEXT → VARCHAR) is semantically a no-op
in Postgres for unbounded length, but we make it explicit so a future
reader of the schema sees the EncryptedString type and reaches for the
TypeDecorator rather than mishandling the column as plaintext.

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import app.utils.encryption
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    row_count = bind.execute(sa.text("SELECT COUNT(*) FROM call_transcripts")).scalar() or 0
    if row_count > 0:
        raise RuntimeError(
            f"call_transcripts has {row_count} plaintext rows. Swapping the "
            f"column type to EncryptedString without re-encryption would orphan "
            f"PHI. Run the re-encrypt migration first — see docs/SECURITY.md."
        )

    op.alter_column(
        "call_transcripts",
        "full_transcript",
        existing_type=sa.Text(),
        type_=app.utils.encryption.EncryptedString(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "call_transcripts",
        "full_transcript",
        existing_type=app.utils.encryption.EncryptedString(),
        type_=sa.Text(),
        existing_nullable=False,
    )
