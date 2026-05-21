"""Extraction-review endpoints.

GET /api/extractions/        list, optional ?needs_review=true filter
GET /api/extractions/{id}    full detail (audited via track_view)

Tenant scoping comes from the SQLAlchemy session guard
(``do_orm_execute`` listener). Every route must declare
``get_current_user`` BEFORE ``get_db`` so the ContextVar is populated
before the session opens.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.ai_invocation import AiInvocation
from app.models.document import Document
from app.models.document_extraction import DocumentExtraction
from app.schemas.extraction import (
    ExtractionDetail,
    ExtractionListItem,
    ExtractionListResponse,
)
from app.utils.audit import track_view

router = APIRouter(prefix="/api/extractions", tags=["extractions"])


def _avg_confidence(field_confidences: dict[str, Any]) -> float:
    if not field_confidences:
        return 0.0
    values = [float(v) for v in field_confidences.values() if isinstance(v, int | float)]
    if not values:
        return 0.0
    return sum(values) / len(values)


async def _track_extraction_view(db: AsyncSession, extraction_id: UUID) -> None:
    """Bridge AsyncSession → sync Connection so track_view (sync) can run."""
    from sqlalchemy.orm import Session as SyncSession

    def _emit(sync_session: SyncSession) -> None:
        track_view(
            sync_session.connection(),
            resource_type="document_extraction",
            resource_id=extraction_id,
        )

    await db.run_sync(_emit)


@router.get("", response_model=ExtractionListResponse)
@router.get("/", response_model=ExtractionListResponse)
async def list_extractions(
    needs_review: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExtractionListResponse:
    stmt = select(DocumentExtraction, Document).join(
        Document, DocumentExtraction.document_id == Document.id
    )
    if needs_review is not None:
        stmt = stmt.where(DocumentExtraction.human_review_required.is_(needs_review))

    stmt = stmt.order_by(
        desc(DocumentExtraction.human_review_required),
        desc(DocumentExtraction.created_at),
    ).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).all()

    count_stmt = select(func.count(DocumentExtraction.id))
    if needs_review is not None:
        count_stmt = count_stmt.where(
            DocumentExtraction.human_review_required.is_(needs_review)
        )
    total = (await db.execute(count_stmt)).scalar_one()

    items = [
        ExtractionListItem(
            id=ext.id,
            document_id=ext.document_id,
            document_file_name=doc.file_name,
            classification=doc.classification,
            human_review_required=ext.human_review_required,
            created_at=ext.created_at,
            avg_confidence=_avg_confidence(ext.field_confidences),
            missing_fields_count=len(ext.missing_fields or []),
        )
        for ext, doc in rows
    ]
    return ExtractionListResponse(items=items, total=int(total), limit=limit, offset=offset)


@router.get("/{extraction_id}", response_model=ExtractionDetail)
async def get_extraction(
    extraction_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExtractionDetail:
    row = (
        await db.execute(
            select(DocumentExtraction, Document)
            .join(Document, DocumentExtraction.document_id == Document.id)
            .where(DocumentExtraction.id == extraction_id)
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="extraction not found"
        )
    ext, doc = row

    # Pull model + prompt_version from the linked AiInvocation, if any.
    model_name: str | None = None
    prompt_version: str | None = None
    if ext.ai_invocation_id is not None:
        inv = await db.get(AiInvocation, ext.ai_invocation_id)
        if inv is not None:
            model_name = inv.model
            scores = inv.confidence_scores or {}
            pv = scores.get("prompt_version")
            prompt_version = str(pv) if pv is not None else None

    await _track_extraction_view(db, extraction_id)
    await db.commit()

    return ExtractionDetail(
        id=ext.id,
        document_id=ext.document_id,
        document_file_name=doc.file_name,
        classification=doc.classification,
        extraction_data=ext.extraction_data,
        field_confidences=ext.field_confidences,
        missing_fields=list(ext.missing_fields or []),
        human_edits=list(ext.human_edits or []),
        human_review_required=ext.human_review_required,
        extraction_version=ext.extraction_version,
        created_at=ext.created_at,
        human_reviewed_by=ext.human_reviewed_by,
        human_reviewed_at=ext.human_reviewed_at,
        model=model_name,
        prompt_version=prompt_version,
        avg_confidence=_avg_confidence(ext.field_confidences),
    )
