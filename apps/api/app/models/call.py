"""Call + CallTranscript — voice agent (Ember) calls and transcripts."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class CallType(enum.StrEnum):
    outbound_scheduling = "outbound_scheduling"
    outbound_followup = "outbound_followup"
    inbound = "inbound"


class CallStatus(enum.StrEnum):
    initiated = "initiated"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    no_answer = "no_answer"
    voicemail = "voicemail"


class Call(ClinicScopedBase):
    __tablename__ = "calls"

    patient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    outreach_attempt_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("outreach_attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
    call_type: Mapped[CallType] = mapped_column(Enum(CallType, name="call_type"), nullable=False)
    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, name="call_status"),
        nullable=False,
        default=CallStatus.initiated,
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


class CallTranscript(ClinicScopedBase):
    __tablename__ = "call_transcripts"

    call_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("calls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_transcript: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
