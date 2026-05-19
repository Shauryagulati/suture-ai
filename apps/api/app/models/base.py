"""Declarative bases.

Two bases:
- `ClinicScopedBase`: tenant-scoped rows. Inherits clinic_id + tenant guard +
  audit eligibility.
- `GlobalBase`: rows that legitimately span tenants (clinics, users,
  clinic_memberships). Skip the tenant guard.

Both share one declarative `Base` (so a single metadata is used for
migrations).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base — single metadata for all models."""


class _TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class GlobalBase(Base, _TimestampMixin):
    """For tables that span tenants (clinics, users, clinic_memberships).

    Models inheriting from this skip the tenant guard. The set of such
    tables is closed: any new model defaults to ClinicScopedBase unless
    there's a documented reason (ADR).
    """

    __abstract__ = True
    _skip_tenant_guard: bool = True

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)


class ClinicScopedBase(Base, _TimestampMixin):
    """For all tenant-scoped tables.

    Carries `clinic_id` automatically. The tenant guard event listener
    filters every SELECT/UPDATE/DELETE by `current_clinic_id`, and
    the `before_insert` listener sets clinic_id from the ContextVar.
    """

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    @declared_attr
    def clinic_id(cls) -> Mapped[UUID]:  # noqa: N805 - SQLAlchemy declared_attr convention
        return mapped_column(
            PG_UUID(as_uuid=True),
            ForeignKey("clinics.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
