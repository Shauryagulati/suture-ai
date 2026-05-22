"""discharge_confirmation_fax_path

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-21 19:30:00.000000

Add `confirmation_fax_path` (nullable string) to `discharge_summaries`. The
column stores the on-disk path of the most-recent confirmation-fax PDF so
`GET /api/discharges/{id}/fax` can stream it.

The companion timestamp column `confirmation_fax_sent_at` already exists
(see 0002). This migration only adds the file-path side.

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "discharge_summaries",
        sa.Column("confirmation_fax_path", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discharge_summaries", "confirmation_fax_path")
