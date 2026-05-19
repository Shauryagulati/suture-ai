"""ClinicMembership — joins users to clinics. ADR 005."""

from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GlobalBase


class MembershipRole(enum.StrEnum):
    admin = "admin"
    reviewer = "reviewer"
    readonly = "readonly"


class ClinicMembership(GlobalBase):
    __tablename__ = "clinic_memberships"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    clinic_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, name="membership_role"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("user_id", "clinic_id", name="uq_clinic_memberships_user_clinic"),
        Index(
            "uq_clinic_memberships_one_default_per_user",
            "user_id",
            unique=True,
            postgresql_where="is_default IS TRUE",
        ),
    )
