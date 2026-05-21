"""Pydantic request/response schemas for the prior-auth endpoints.

The `AuthCheckRequest` / `AuthDetermination` types are imported from the
determination service so there is one source of truth — the schemas
module re-exports them for OpenAPI grouping.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.prior_auth import PriorAuthEventType, PriorAuthStatus
from app.services.prior_auth.determine import (
    AuthCheckRequest,
    AuthDetermination,
    PolicyExcerpt,
)

__all__ = [
    "AuthCheckRequest",
    "AuthDetermination",
    "PacketGenerateRequest",
    "PolicyExcerpt",
    "PriorAuthAppealRequest",
    "PriorAuthDetailRead",
    "PriorAuthEventRead",
    "PriorAuthRead",
    "PriorAuthStatusUpdate",
]


class PacketGenerateRequest(BaseModel):
    """Body for POST /packet/{referral_id} — caller supplies the clinical
    summary the determination should reason against (or the route falls
    back to the referral's `notes`)."""

    clinical_summary: str | None = None


class PriorAuthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    referral_id: UUID | None
    patient_id: UUID
    payer_name: str
    payer_id: str | None
    procedure_codes: list[str]
    diagnosis_codes: list[str]
    auth_required: bool | None
    auth_required_reasoning: str | None
    status: PriorAuthStatus
    submitted_at: datetime | None
    approved_at: datetime | None
    denied_at: datetime | None
    auth_number: str | None
    packet_file_path: str | None
    follow_up_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PriorAuthEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    prior_auth_id: UUID
    event_type: PriorAuthEventType
    details: dict[str, Any]
    created_by: UUID | None
    created_at: datetime


class PriorAuthDetailRead(PriorAuthRead):
    events: list[PriorAuthEventRead]


class PriorAuthStatusUpdate(BaseModel):
    status: PriorAuthStatus
    auth_number: str | None = Field(default=None, max_length=128)
    denial_reason: str | None = None


class PriorAuthAppealRequest(BaseModel):
    denial_reason: str = Field(min_length=1)
