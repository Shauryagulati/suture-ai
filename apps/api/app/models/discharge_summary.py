"""DischargeSummary — hospital discharge with cardiology follow-up needed."""

from __future__ import annotations

import enum
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import ARRAY, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class UrgencyTier(enum.StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    routine = "routine"


class DischargeStatus(enum.StrEnum):
    new = "new"
    patient_contacted = "patient_contacted"
    scheduled = "scheduled"
    seen = "seen"
    confirmation_sent = "confirmation_sent"
    at_risk = "at_risk"


class DischargeSummary(ClinicScopedBase):
    __tablename__ = "discharge_summaries"

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
    discharge_date: Mapped[date] = mapped_column(Date, nullable=False)
    primary_diagnosis: Mapped[str | None] = mapped_column(String(512), nullable=True)
    diagnosis_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    follow_up_window_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    follow_up_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    recommended_specialist: Mapped[str | None] = mapped_column(String(128), nullable=True)
    urgent_flags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    urgency_tier: Mapped[UrgencyTier] = mapped_column(
        Enum(UrgencyTier, name="urgency_tier"),
        nullable=False,
        default=UrgencyTier.routine,
    )
    status: Mapped[DischargeStatus] = mapped_column(
        Enum(DischargeStatus, name="discharge_status"),
        nullable=False,
        default=DischargeStatus.new,
    )
    confirmation_fax_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmation_fax_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
