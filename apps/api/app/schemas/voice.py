"""Pydantic schemas for the voice (Ember) routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.call import Call, CallStatus, CallType


class CallResponse(BaseModel):
    """A single Call row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    outreach_attempt_id: UUID | None
    call_type: CallType
    status: CallStatus
    duration_seconds: int | None
    started_at: datetime
    ended_at: datetime | None
    outcome: dict[str, Any]

    @classmethod
    def from_model(cls, call: Call) -> CallResponse:
        return cls.model_validate(call)


class CallListResponse(BaseModel):
    items: list[CallResponse]


class CallTokenResponse(BaseModel):
    """LiveKit access token for a browser client to join the call's room."""

    room_name: str
    livekit_url: str
    token: str
    identity: str


class TranscriptResponse(BaseModel):
    """Persisted (decrypted) transcript for a completed call."""

    call_id: UUID
    full_transcript: str
    structured_data: dict[str, Any]


class StartCallResponse(BaseModel):
    """Result of POST /api/voice/calls/{call_id}/start."""

    call_id: UUID
    room_name: str
    redispatched: bool


class EndCallResponse(BaseModel):
    """Result of POST /api/voice/calls/{call_id}/end."""

    call_id: UUID
    status: CallStatus
    ended_at: datetime
