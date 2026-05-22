"""core_tables

Gate B1: clinics, users, clinic_memberships, patients, providers, audit_logs.

Revision ID: 0001
Revises:
Create Date: 2026-05-19

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── enums ──
    membership_role = sa.Enum(
        "admin", "reviewer", "readonly", name="membership_role"
    )
    provider_type = sa.Enum("referring", "internal", name="provider_type")
    audit_action = sa.Enum(
        "view",
        "create",
        "update",
        "delete",
        "export",
        "ai_query",
        name="audit_action",
    )

    # ── clinics ──
    op.create_table(
        "clinics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("settings", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── users (global identity, email globally unique — ADR 005) ──
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", postgresql.CITEXT, nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── clinic_memberships ──
    op.create_table(
        "clinic_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "clinic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", membership_role, nullable=False),
        sa.Column(
            "is_default", sa.Boolean, nullable=False, server_default="false"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "clinic_id", name="uq_clinic_memberships_user_clinic"
        ),
    )
    # At most one default membership per user.
    op.create_index(
        "uq_clinic_memberships_one_default_per_user",
        "clinic_memberships",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )

    # ── patients (PHI; dob/phone/ssn encrypted at app layer via Fernet) ──
    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clinic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("last_name", sa.String(120), nullable=False),
        sa.Column("dob", sa.String, nullable=False),  # encrypted at app layer
        sa.Column("phone", sa.String, nullable=False),  # encrypted at app layer
        sa.Column("ssn", sa.String, nullable=True),  # encrypted at app layer
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("zip_code", sa.String(10), nullable=True),
        sa.Column("mrn", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_patients_clinic_id", "patients", ["clinic_id"])
    op.create_index("ix_patients_mrn", "patients", ["mrn"])

    # ── providers ──
    op.create_table(
        "providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clinic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("last_name", sa.String(120), nullable=False),
        sa.Column("npi", sa.String(10), nullable=False),
        sa.Column("practice_name", sa.String(255), nullable=True),
        sa.Column("practice_phone", sa.String(32), nullable=True),
        sa.Column("practice_fax", sa.String(32), nullable=True),
        sa.Column("practice_address", sa.String(512), nullable=True),
        sa.Column("provider_type", provider_type, nullable=False),
        sa.Column("specialty", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_providers_clinic_id", "providers", ["clinic_id"])
    op.create_index("ix_providers_npi", "providers", ["npi"])

    # ── audit_logs ──
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clinic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clinics.id", ondelete="RESTRICT"),
            # Audit rows for system events legitimately have no clinic.
            # The tenant guard treats this table as guard-exempt.
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", audit_action, nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "details", postgresql.JSONB, nullable=False, server_default="{}"
        ),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_logs_clinic_id", "audit_logs", ["clinic_id"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    # Reverse FK dependency order. Drop indexes implicitly via drop_table.
    op.drop_index("ix_audit_logs_timestamp", table_name="audit_logs")
    op.drop_index("ix_audit_logs_resource_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_clinic_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_providers_npi", table_name="providers")
    op.drop_index("ix_providers_clinic_id", table_name="providers")
    op.drop_table("providers")

    op.drop_index("ix_patients_mrn", table_name="patients")
    op.drop_index("ix_patients_clinic_id", table_name="patients")
    op.drop_table("patients")

    op.drop_index(
        "uq_clinic_memberships_one_default_per_user", table_name="clinic_memberships"
    )
    op.drop_table("clinic_memberships")

    op.drop_table("users")
    op.drop_table("clinics")

    # Drop named enums explicitly so a re-upgrade works.
    op.execute("DROP TYPE IF EXISTS audit_action")
    op.execute("DROP TYPE IF EXISTS provider_type")
    op.execute("DROP TYPE IF EXISTS membership_role")
