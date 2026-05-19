"""Fax — inbound (raw) or outbound (confirmation, auth packet)."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class FaxDirection(enum.StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class FaxType(enum.StrEnum):
    referral = "referral"
    discharge = "discharge"
    confirmation = "confirmation"
    auth_packet = "auth_packet"
    other = "other"


class FaxStatus(enum.StrEnum):
    generated = "generated"
    sending = "sending"
    sent = "sent"
    failed = "failed"


class Fax(ClinicScopedBase):
    __tablename__ = "faxes"

    direction: Mapped[FaxDirection] = mapped_column(
        Enum(FaxDirection, name="fax_direction"), nullable=False
    )
    patient_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    fax_type: Mapped[FaxType] = mapped_column(Enum(FaxType, name="fax_type"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_fax_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[FaxStatus] = mapped_column(
        Enum(FaxStatus, name="fax_status"),
        nullable=False,
        default=FaxStatus.generated,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
