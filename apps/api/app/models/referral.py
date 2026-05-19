"""Referral — a request for cardiology consultation/care."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import ARRAY, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase
from app.models.document import UrgencyLevel


class ReferralStatus(enum.StrEnum):
    new = "new"
    needs_review = "needs_review"
    missing_info = "missing_info"
    ready_to_schedule = "ready_to_schedule"
    auth_needed = "auth_needed"
    scheduled = "scheduled"
    completed = "completed"
    at_risk = "at_risk"
    cancelled = "cancelled"


class Referral(ClinicScopedBase):
    __tablename__ = "referrals"

    document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    patient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    referring_provider_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_provider_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[ReferralStatus] = mapped_column(
        Enum(ReferralStatus, name="referral_status"),
        nullable=False,
        default=ReferralStatus.new,
        index=True,
    )
    urgency: Mapped[UrgencyLevel] = mapped_column(
        Enum(UrgencyLevel, name="urgency_level"),
        nullable=False,
        default=UrgencyLevel.unclassified,
    )
    diagnosis_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    procedure_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    follow_up_window_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Renamed from scheduled_date — instant, not calendar date. ADR 004.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
