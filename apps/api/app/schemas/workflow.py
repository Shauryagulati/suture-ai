"""Pydantic schemas for workflow transitions and timeline."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.discharge_summary import DischargeStatus
from app.models.referral import ReferralStatus


class ReferralTransitionRequest(BaseModel):
    target: ReferralStatus


class DischargeTransitionRequest(BaseModel):
    target: DischargeStatus


class TransitionResponse(BaseModel):
    id: UUID
    status: str


class TimelineEvent(BaseModel):
    at: datetime
    actor_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID
    changed_columns: list[str]
    # Optional channel + outcome summary for outreach_* events. Empty
    # dict for audit-derived events.
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimelineResponse(BaseModel):
    events: list[TimelineEvent]
