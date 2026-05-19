"""OutreachAttempt — SMS / email / voice contact attempt."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class OutreachChannel(enum.StrEnum):
    sms = "sms"
    email = "email"
    voice = "voice"


class OutreachStatus(enum.StrEnum):
    pending = "pending"
    sent = "sent"
    delivered = "delivered"
    responded = "responded"
    no_response = "no_response"
    failed = "failed"


class OutreachAttempt(ClinicScopedBase):
    __tablename__ = "outreach_attempts"

    patient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referral_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="SET NULL"),
        nullable=True,
    )
    discharge_summary_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discharge_summaries.id", ondelete="SET NULL"),
        nullable=True,
    )
    channel: Mapped[OutreachChannel] = mapped_column(
        Enum(OutreachChannel, name="outreach_channel"), nullable=False
    )
    status: Mapped[OutreachStatus] = mapped_column(
        Enum(OutreachStatus, name="outreach_status"),
        nullable=False,
        default=OutreachStatus.pending,
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scheduling_link_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
