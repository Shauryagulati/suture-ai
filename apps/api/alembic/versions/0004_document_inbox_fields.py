"""document_inbox_fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-21 14:00:00.000000

Add three nullable columns to `documents` needed by the Module 1
inbox pipeline:

- `extracted_text TEXT` — raw OCR output (Docling or pypdf)
- `ocr_engine VARCHAR(32)` — which engine produced `extracted_text`
- `notes TEXT` — reviewer notes captured via PATCH /api/documents/{id}

All three are nullable so existing rows remain valid. Module 2 will
read `extracted_text` as input for structured field extraction.

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
    op.add_column("documents", sa.Column("extracted_text", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("ocr_engine", sa.String(length=32), nullable=True))
    op.add_column("documents", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "notes")
    op.drop_column("documents", "ocr_engine")
    op.drop_column("documents", "extracted_text")
