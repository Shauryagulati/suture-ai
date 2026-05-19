"""AiInvocation — every Claude API call logged here. No PHI."""

from __future__ import annotations

import enum
from typing import Any
from uuid import UUID

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class InvocationType(enum.StrEnum):
    classification = "classification"
    extraction = "extraction"
    auth_check = "auth_check"
    voice_dialogue = "voice_dialogue"
    appeal_generation = "appeal_generation"
    other = "other"


class AiInvocation(ClinicScopedBase):
    __tablename__ = "ai_invocations"

    invocation_type: Mapped[InvocationType] = mapped_column(
        Enum(InvocationType, name="invocation_type"),
        nullable=False,
        index=True,
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Both summary columns must be PHI-free — descriptions only.
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    patient_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
    )
