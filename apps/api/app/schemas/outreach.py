"""Pydantic schemas for the authenticated outreach endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.outreach_attempt import OutreachAttempt, OutreachChannel, OutreachStatus


class OutreachAttemptResponse(BaseModel):
    id: UUID
    patient_id: UUID
    referral_id: UUID | None
    discharge_summary_id: UUID | None
    channel: OutreachChannel
    status: OutreachStatus
    scheduled_at: datetime
    sent_at: datetime | None
    outcome: dict[str, Any]
    attempt_number: int
    scheduling_link_url: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m: OutreachAttempt) -> OutreachAttemptResponse:
        return cls(
            id=m.id,
            patient_id=m.patient_id,
            referral_id=m.referral_id,
            discharge_summary_id=m.discharge_summary_id,
            channel=m.channel,
            status=m.status,
            scheduled_at=m.scheduled_at,
            sent_at=m.sent_at,
            outcome=m.outcome or {},
            attempt_number=m.attempt_number,
            scheduling_link_url=m.scheduling_link_url,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class OutreachAttemptListResponse(BaseModel):
    items: list[OutreachAttemptResponse]


class TriggerOutreachResponse(BaseModel):
    attempt_ids: list[UUID]
    attempt_number: int
