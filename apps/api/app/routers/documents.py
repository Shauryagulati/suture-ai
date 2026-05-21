"""Document inbox endpoints.

Multi-tenant filtering is enforced by the SQLAlchemy session guard
(`do_orm_execute` listener in `app.database`). Every route here must list
``get_current_user`` BEFORE ``get_db`` so the ContextVar is set before the
session opens.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.document import (
    Document,
    DocumentClassification,
    DocumentStatus,
    UrgencyLevel,
)
from app.schemas.document import (
    DocumentDetail,
    DocumentListItem,
    DocumentListResponse,
    DocumentPatchRequest,
    DocumentUploadResponse,
)
from app.services.classification import classify_document
from app.services.document_storage import save_pdf
from app.services.extraction import extract_document
from app.services.ocr import extract_text
from app.utils.audit import track_view

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


async def _track_document_view(db: AsyncSession, document_id: UUID) -> None:
    """Bridge AsyncSession → sync Connection so track_view (sync) can run."""
    from sqlalchemy.orm import Session as SyncSession

    def _emit(sync_session: SyncSession) -> None:
        track_view(
            sync_session.connection(),
            resource_type="document",
            resource_id=document_id,
        )

    await db.run_sync(_emit)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    settings = get_settings()

    if file.content_type not in settings.allowed_mime_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"unsupported media type: {file.content_type}. "
                f"allowed: {', '.join(settings.allowed_mime_types)}"
            ),
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="uploaded file is empty",
        )
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file exceeds max upload size of {settings.max_upload_bytes} bytes",
        )

    path, size = await save_pdf(clinic_id=user.active_clinic_id, content=content)

    doc = Document(
        file_path=str(path),
        file_name=file.filename or "upload.pdf",
        file_size=size,
        mime_type=file.content_type or "application/pdf",
        status=DocumentStatus.classifying,
        uploaded_by=user.user_id,
    )
    db.add(doc)
    await db.flush()

    try:
        text, engine = await extract_text(path)
        doc.extracted_text = text
        doc.ocr_engine = engine
        result = await classify_document(text=text, document_id=doc.id, db=db)
        doc.classification = result.classification
        doc.classification_confidence = result.confidence
        doc.status = DocumentStatus.classified
    except Exception as exc:
        logger.exception(
            "documents.upload_post_processing_failed",
            document_id=str(doc.id),
            error=str(exc),
        )
        doc.status = DocumentStatus.error
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="document post-processing failed",
        ) from exc

    # Auto-extract for referrals and discharge summaries. Failure here is
    # non-fatal: the document stays at `classified` so a future job can
    # re-run extraction. The upload still returns 201.
    if doc.classification in (
        DocumentClassification.referral,
        DocumentClassification.discharge_summary,
    ):
        doc.status = DocumentStatus.extracting
        try:
            await extract_document(document_id=doc.id, db=db)
            doc.status = DocumentStatus.extracted
        except Exception as exc:
            logger.exception(
                "documents.extraction_failed",
                document_id=str(doc.id),
                error=str(exc),
            )
            doc.status = DocumentStatus.classified

    await db.commit()
    await db.refresh(doc)
    return DocumentUploadResponse.model_validate(doc)


@router.get("", response_model=DocumentListResponse)
@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    classification: DocumentClassification | None = Query(default=None),
    urgency: UrgencyLevel | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    filters = []
    if status_filter is not None:
        filters.append(Document.status == status_filter)
    if classification is not None:
        filters.append(Document.classification == classification)
    if urgency is not None:
        filters.append(Document.urgency == urgency)
    if date_from is not None:
        filters.append(Document.created_at >= date_from)
    if date_to is not None:
        filters.append(Document.created_at <= date_to)

    stmt = select(Document)
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(desc(Document.created_at)).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()

    # Count via a Document-column reference (Document.id) so state.all_mappers
    # includes Document and the tenant guard's _is_clinic_scoped_statement returns
    # True — otherwise the COUNT bypasses the guard and reports cross-clinic totals.
    count_stmt = select(func.count(Document.id))
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    return DocumentListResponse(
        items=[DocumentListItem.model_validate(d) for d in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    await _track_document_view(db, document_id)
    await db.commit()
    return DocumentDetail.model_validate(doc)


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    path = Path(doc.file_path)
    if not path.exists():
        logger.error(
            "documents.file_missing_on_disk",
            document_id=str(document_id),
            file_path=str(path),
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="document file no longer available",
        )

    await _track_document_view(db, document_id)
    await db.commit()
    return FileResponse(
        path=str(path),
        media_type=doc.mime_type,
        filename=doc.file_name,
    )


@router.patch("/{document_id}", response_model=DocumentDetail)
async def patch_document(
    document_id: UUID,
    body: DocumentPatchRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    if body.status is not None:
        doc.status = body.status
    if body.notes is not None:
        doc.notes = body.notes

    await db.commit()
    await db.refresh(doc)
    return DocumentDetail.model_validate(doc)
