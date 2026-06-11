"""Pydantic schemas for the authenticated outreach endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.outreach_attempt import OutreachAttempt, OutreachChannel, OutreachStatus


def _strip_tokens(outcome: dict[str, Any]) -> dict[str, Any]:
    """Drop any ``*_token`` key from the outcome (incl. nested provider_raw).

    Defense-in-depth: room-join tokens must never reach a client even if some
    upstream path persisted them. The service layer already avoids persisting
    them; this is the second line.
    """
    cleaned = {k: v for k, v in outcome.items() if not k.endswith("_token")}
    raw = cleaned.get("provider_raw")
    if isinstance(raw, dict):
        cleaned["provider_raw"] = {k: v for k, v in raw.items() if not k.endswith("_token")}
    return cleaned


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
            outcome=_strip_tokens(m.outcome or {}),
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


class OutreachDashboardRow(BaseModel):
    """One outreach attempt enriched for the staff dashboard: patient name
    joined, related entity, and the rendered message a patient would receive."""

    id: UUID
    channel: OutreachChannel
    status: OutreachStatus
    scheduled_at: datetime
    sent_at: datetime | None
    attempt_number: int
    patient_first_name: str
    patient_last_name: str
    related_type: str | None  # "referral" | "discharge" | None
    message_subject: str | None
    message_body: str


class OutreachDashboardResponse(BaseModel):
    items: list[OutreachDashboardRow]
