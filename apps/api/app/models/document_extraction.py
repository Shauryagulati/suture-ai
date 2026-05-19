"""DocumentExtraction — structured fields pulled from a Document via Claude."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class DocumentExtraction(ClinicScopedBase):
    __tablename__ = "document_extractions"

    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    extraction_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    field_confidences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    missing_fields: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    human_edits: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    human_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    human_reviewed_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    human_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ai_invocation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ai_invocations.id", ondelete="SET NULL"),
        nullable=True,
    )
    extraction_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
