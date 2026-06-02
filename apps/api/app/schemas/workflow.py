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


class DischargeDetail(BaseModel):
    """Server-rendered detail payload for the discharge UI."""

    id: UUID
    patient_id: UUID
    patient_first_name: str
    patient_last_name: str
    status: DischargeStatus
    urgency_tier: str
    discharge_date: str
    primary_diagnosis: str | None
    diagnosis_codes: list[str]
    urgent_flags: list[str]
    follow_up_window_days: int | None
    follow_up_deadline: str | None
    recommended_specialist: str | None
    confirmation_fax_sent_at: datetime | None
    confirmation_fax_path: str | None


class ConfirmDischargeResponse(BaseModel):
    discharge_id: UUID
    status: str
    confirmation_fax_sent_at: datetime | None
    fax_available: bool


class AppointmentCompleteResponse(BaseModel):
    appointment_id: UUID
    appointment_status: str
    discharge_status: str | None  # None if not linked to a discharge
