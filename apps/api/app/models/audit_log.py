"""AuditLog — append-only record of every PHI access.

Inherits ClinicScopedBase but `clinic_id` is allowed to be NULL for global
/ system-level events (e.g. an admin viewing across clinics, or a system
job). Writes bypass the INSERT guard (`_audit_exempt`), so a NULL clinic_id
can be persisted.

Reads, however, are clinic-scoped like any other ClinicScopedBase model: the
`do_orm_execute` guard injects `clinic_id == current_clinic_id`, which in SQL
EXCLUDES NULL. So NULL-clinic system rows are written but are NOT visible via
the ORM under a clinic context (and a read with no context fails closed).
A future admin/system audit-review feature must read them through an explicit
guard-bypass path. (This is safe — it fails closed — but was previously
mis-documented as "the guard treats NULL rows as visible".)
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class AuditAction(enum.StrEnum):
    view = "view"
    create = "create"
    update = "update"
    delete = "delete"
    export = "export"
    ai_query = "ai_query"


class AuditLog(ClinicScopedBase):
    __tablename__ = "audit_logs"
    # Audit rows are themselves audit-exempt — don't audit the audit log.
    _audit_exempt: bool = True

    # Override base clinic_id: audit_logs allows NULL for system-level events
    # (admin acting across clinics, background jobs, etc.).
    clinic_id: Mapped[UUID | None] = mapped_column(  # type: ignore[assignment]
        PG_UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
