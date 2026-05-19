"""Document — uploaded PDF / fax page. PHI-bearing."""

from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class DocumentClassification(enum.StrEnum):
    referral = "referral"
    discharge_summary = "discharge_summary"
    lab = "lab"
    imaging = "imaging"
    other = "other"
    unclassified = "unclassified"


class DocumentStatus(enum.StrEnum):
    uploaded = "uploaded"
    classifying = "classifying"
    classified = "classified"
    extracting = "extracting"
    extracted = "extracted"
    needs_review = "needs_review"
    reviewed = "reviewed"
    processed = "processed"
    error = "error"


class UrgencyLevel(enum.StrEnum):
    stat = "stat"
    urgent = "urgent"
    routine = "routine"
    unclassified = "unclassified"


class Document(ClinicScopedBase):
    __tablename__ = "documents"

    patient_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    classification: Mapped[DocumentClassification] = mapped_column(
        Enum(DocumentClassification, name="document_classification"),
        nullable=False,
        default=DocumentClassification.unclassified,
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        nullable=False,
        default=DocumentStatus.uploaded,
    )
    urgency: Mapped[UrgencyLevel] = mapped_column(
        Enum(UrgencyLevel, name="urgency_level"),
        nullable=False,
        default=UrgencyLevel.unclassified,
    )
    uploaded_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_fax_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
