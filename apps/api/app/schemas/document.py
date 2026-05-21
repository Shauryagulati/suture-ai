"""Pydantic schemas for the document inbox endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import (
    DocumentClassification,
    DocumentStatus,
    UrgencyLevel,
)


class _DocumentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    file_name: str
    file_size: int
    mime_type: str
    status: DocumentStatus
    classification: DocumentClassification
    classification_confidence: float | None
    urgency: UrgencyLevel
    ocr_engine: str | None
    patient_id: UUID | None
    uploaded_by: UUID | None
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(_DocumentBase):
    """Returned from POST /upload — caller wants the new id + classification verdict."""


class DocumentListItem(_DocumentBase):
    """Compact row for the inbox table — same fields as upload response for now."""


class DocumentDetail(_DocumentBase):
    """Full detail view, including OCR text and notes."""

    extracted_text: str | None
    notes: str | None


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    total: int
    limit: int
    offset: int


class DocumentPatchRequest(BaseModel):
    status: DocumentStatus | None = None
    notes: str | None = Field(default=None, max_length=10_000)
