"""Pydantic schemas for the extraction-review API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentClassification


class ExtractionListItem(BaseModel):
    """Compact row for the review queue."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    document_file_name: str
    classification: DocumentClassification
    human_review_required: bool
    created_at: datetime
    avg_confidence: float = Field(ge=0.0, le=1.0)
    missing_fields_count: int


class ExtractionListResponse(BaseModel):
    items: list[ExtractionListItem]
    total: int
    limit: int
    offset: int


class ExtractionDetail(BaseModel):
    """Full payload for the split-view review page."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    document_file_name: str
    classification: DocumentClassification
    extraction_data: dict[str, Any]
    field_confidences: dict[str, float]
    missing_fields: list[str]
    human_edits: list[dict[str, Any]]
    human_review_required: bool
    extraction_version: int
    created_at: datetime
    human_reviewed_by: UUID | None
    human_reviewed_at: datetime | None
    model: str | None
    prompt_version: str | None
    avg_confidence: float = Field(ge=0.0, le=1.0)


class ExtractionPatchRequest(BaseModel):
    """A single dot-notation field update from the review UI."""

    field_path: str = Field(min_length=1, max_length=512)
    new_value: Any


class ExtractionApproveResponse(BaseModel):
    """Result of POST /api/extractions/{id}/approve."""

    referral_id: UUID | None = None
    discharge_summary_id: UUID | None = None
    patient_id: UUID
    patient_created: bool
    referring_provider_id: UUID | None = None
    provider_created: bool | None = None
