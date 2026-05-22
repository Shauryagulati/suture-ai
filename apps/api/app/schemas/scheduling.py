"""Pydantic schemas for the public scheduling endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AvailableSlotsResponse(BaseModel):
    """Returned by GET /api/schedule/{token}."""

    patient_first_name: str
    slots: list[datetime]
    outreach_attempt_id: UUID
    referral_id: UUID | None = None
    discharge_summary_id: UUID | None = None


class BookSlotRequest(BaseModel):
    """Payload for POST /api/schedule/{token}/book."""

    slot: datetime
    appointment_type: str | None = Field(default=None, max_length=64)


class BookSlotResponse(BaseModel):
    """Returned after a successful book call."""

    appointment_id: UUID
    appointment_at: datetime
    status: str
