"""PriorAuth + PriorAuthEvent — payer authorization tracking."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase
from app.utils.encryption import EncryptedString


class PriorAuthStatus(enum.StrEnum):
    not_needed = "not_needed"
    checking = "checking"
    required = "required"
    submitted = "submitted"
    approved = "approved"
    denied = "denied"
    appealing = "appealing"
    appeal_approved = "appeal_approved"
    appeal_denied = "appeal_denied"


class PriorAuthEventType(enum.StrEnum):
    created = "created"
    submitted = "submitted"
    approved = "approved"
    denied = "denied"
    appeal_submitted = "appeal_submitted"
    appeal_approved = "appeal_approved"
    appeal_denied = "appeal_denied"
    follow_up_scheduled = "follow_up_scheduled"
    follow_up_completed = "follow_up_completed"


class PriorAuth(ClinicScopedBase):
    __tablename__ = "prior_auths"

    referral_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=True,
    )
    patient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    payer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # PHI: encrypted at app layer.
    member_id: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    procedure_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    diagnosis_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    auth_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    auth_required_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PriorAuthStatus] = mapped_column(
        Enum(PriorAuthStatus, name="prior_auth_status"),
        nullable=False,
        default=PriorAuthStatus.checking,
        index=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    denied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Absolute on-disk path to the rendered packet PDF. Internal only — the API
    # exposes `packet_available` (below), never this path, to avoid leaking the
    # server filesystem layout into responses/UI.
    packet_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Renamed from follow_up_date — instant. ADR 004.
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def packet_available(self) -> bool:
        """Whether a packet PDF has been generated (API-safe; hides the path)."""
        return self.packet_file_path is not None


class PriorAuthEvent(ClinicScopedBase):
    __tablename__ = "prior_auth_events"

    prior_auth_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("prior_auths.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[PriorAuthEventType] = mapped_column(
        Enum(PriorAuthEventType, name="prior_auth_event_type"), nullable=False
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
