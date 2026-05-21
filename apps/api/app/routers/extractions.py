"""Extraction-review endpoints.

GET   /api/extractions/                list, optional ?needs_review=true filter
GET   /api/extractions/{id}            full detail (audited via track_view)
PATCH /api/extractions/{id}            edit one field, append to human_edits
POST  /api/extractions/{id}/approve    create Referral / DischargeSummary

Tenant scoping comes from the SQLAlchemy session guard
(``do_orm_execute`` listener). Every route must declare
``get_current_user`` BEFORE ``get_db`` so the ContextVar is populated
before the session opens.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.ai_invocation import AiInvocation
from app.models.discharge_summary import (
    DischargeStatus,
    DischargeSummary,
    UrgencyTier,
)
from app.models.document import Document, DocumentClassification, DocumentStatus, UrgencyLevel
from app.models.document_extraction import DocumentExtraction
from app.models.referral import Referral, ReferralStatus
from app.schemas.extraction import (
    ExtractionApproveResponse,
    ExtractionDetail,
    ExtractionListItem,
    ExtractionListResponse,
    ExtractionPatchRequest,
)
from app.services.extraction.confidence import compute_field_confidences
from app.services.extraction.resolvers import (
    ExtractionResolverError,
    resolve_or_create_patient,
    resolve_or_create_referring_provider,
)
from app.services.workflow.state_machine import (
    InvalidTransitionError,
    apply_referral_transition,
)
from app.utils.audit import track_view

router = APIRouter(prefix="/api/extractions", tags=["extractions"])

_INDEX_RE = re.compile(r"^(.*?)\[(\d+)\]$")


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


# ---------------------------- PATCH ----------------------------


def _split_path(path: str) -> list[tuple[str, int | None]]:
    """Parse ``a.b[2].c`` → ``[('a', None), ('b', 2), ('c', None)]``."""
    segments: list[tuple[str, int | None]] = []
    for seg in path.split("."):
        m = _INDEX_RE.match(seg)
        if m:
            segments.append((m.group(1), int(m.group(2))))
        else:
            segments.append((seg, None))
    return segments


def _get_by_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for key, idx in _split_path(path):
        if not isinstance(current, dict):
            raise KeyError(path)
        if key not in current:
            return None
        current = current[key]
        if idx is not None:
            if not isinstance(current, list) or idx >= len(current):
                return None
            current = current[idx]
    return current


def _set_by_path(data: dict[str, Any], path: str, value: Any) -> None:
    segments = _split_path(path)
    current: Any = data
    for key, idx in segments[:-1]:
        if not isinstance(current, dict) or key not in current or current[key] is None:
            raise KeyError(f"intermediate path '{key}' is missing from extraction_data")
        current = current[key]
        if idx is not None:
            if not isinstance(current, list) or idx >= len(current):
                raise KeyError(f"index [{idx}] out of range for path segment '{key}'")
            current = current[idx]
    last_key, last_idx = segments[-1]
    if not isinstance(current, dict):
        raise KeyError(f"cannot set on non-dict at path '{path}'")
    if last_idx is None:
        current[last_key] = value
    else:
        if last_key not in current or not isinstance(current[last_key], list):
            current[last_key] = []
        lst = current[last_key]
        while len(lst) <= last_idx:
            lst.append(None)
        lst[last_idx] = value


async def _load_extraction_or_404(db: AsyncSession, extraction_id: UUID) -> DocumentExtraction:
    ext = await db.get(DocumentExtraction, extraction_id)
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="extraction not found"
        )
    return ext


@router.patch("/{extraction_id}", response_model=ExtractionDetail)
async def patch_extraction(
    extraction_id: UUID,
    body: ExtractionPatchRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExtractionDetail:
    ext = await _load_extraction_or_404(db, extraction_id)
    if ext.human_reviewed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="extraction already approved — cannot edit",
        )

    try:
        old_value = _get_by_path(ext.extraction_data, body.field_path)
        _set_by_path(ext.extraction_data, body.field_path, body.new_value)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid field_path: {exc}",
        ) from exc

    flag_modified(ext, "extraction_data")

    edit_entry = {
        "field": body.field_path,
        "old": old_value,
        "new": body.new_value,
        "edited_by": str(user.user_id),
        "edited_at": datetime.now(UTC).isoformat(),
    }
    edits = list(ext.human_edits or [])
    edits.append(edit_entry)
    ext.human_edits = edits
    flag_modified(ext, "human_edits")

    # Rebuild missing_fields: a human-provided non-null value removes that
    # path from the "missing" set so the score is no longer forced to 0.
    missing = list(ext.missing_fields or [])
    if body.new_value is not None and body.field_path in missing:
        missing.remove(body.field_path)
        ext.missing_fields = missing

    confidences, needs_review = compute_field_confidences(
        ext.extraction_data, list(ext.missing_fields or [])
    )
    ext.field_confidences = confidences
    flag_modified(ext, "field_confidences")
    ext.human_review_required = needs_review

    await db.commit()
    return await get_extraction(extraction_id, user=user, db=db)


# ---------------------------- APPROVE ----------------------------


def _coerce_urgency(value: Any) -> UrgencyLevel:
    if isinstance(value, str):
        try:
            return UrgencyLevel(value)
        except ValueError:
            pass
    return UrgencyLevel.unclassified


def _coerce_urgency_tier(value: Any) -> UrgencyTier:
    if isinstance(value, str):
        try:
            return UrgencyTier(value)
        except ValueError:
            pass
    return UrgencyTier.routine


def _coerce_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


async def _approve_referral(
    db: AsyncSession,
    *,
    ext: DocumentExtraction,
    doc: Document,
) -> ExtractionApproveResponse:
    data = ext.extraction_data
    patient_dict = data.get("patient") or {}
    provider_dict = data.get("referring_provider") or {}

    patient, patient_created = await resolve_or_create_patient(db, patient_dict)
    provider, provider_created = await resolve_or_create_referring_provider(db, provider_dict)

    referral = Referral(
        document_id=doc.id,
        patient_id=patient.id,
        referring_provider_id=provider.id if provider is not None else None,
        diagnosis_codes=list(data.get("diagnosis_codes") or []),
        procedure_codes=list(data.get("procedure_codes") or []),
        urgency=_coerce_urgency(data.get("urgency")),
        follow_up_window_days=data.get("follow_up_window_days"),
        notes=data.get("clinical_notes_excerpt"),
        status=ReferralStatus.new,
    )
    db.add(referral)
    await db.flush()

    try:
        await apply_referral_transition(
            db, referral=referral, target=ReferralStatus.needs_review
        )
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    return ExtractionApproveResponse(
        referral_id=referral.id,
        patient_id=patient.id,
        patient_created=patient_created,
        referring_provider_id=provider.id if provider is not None else None,
        provider_created=provider_created if provider is not None else None,
    )


async def _approve_discharge(
    db: AsyncSession,
    *,
    ext: DocumentExtraction,
    doc: Document,
) -> ExtractionApproveResponse:
    data = ext.extraction_data
    patient_dict = data.get("patient") or {}

    patient, patient_created = await resolve_or_create_patient(db, patient_dict)

    discharge_date = _coerce_date(data.get("discharge_date"))
    if discharge_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="discharge_date is required to approve a discharge summary",
        )

    discharge = DischargeSummary(
        document_id=doc.id,
        patient_id=patient.id,
        discharge_date=discharge_date,
        primary_diagnosis=data.get("primary_diagnosis"),
        diagnosis_codes=list(data.get("diagnosis_codes") or []),
        urgent_flags=list(data.get("urgent_flags") or []),
        urgency_tier=_coerce_urgency_tier(data.get("urgency_tier")),
        follow_up_window_days=data.get("follow_up_window_days"),
        recommended_specialist=data.get("recommended_specialist"),
        status=DischargeStatus.new,
    )
    db.add(discharge)
    await db.flush()

    return ExtractionApproveResponse(
        discharge_summary_id=discharge.id,
        patient_id=patient.id,
        patient_created=patient_created,
    )


@router.post(
    "/{extraction_id}/approve",
    response_model=ExtractionApproveResponse,
    status_code=status.HTTP_200_OK,
)
async def approve_extraction(
    extraction_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExtractionApproveResponse:
    ext = await _load_extraction_or_404(db, extraction_id)
    if ext.human_reviewed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="extraction already approved",
        )

    doc = await db.get(Document, ext.document_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="parent document not found",
        )

    try:
        if doc.classification == DocumentClassification.referral:
            response = await _approve_referral(db, ext=ext, doc=doc)
        elif doc.classification == DocumentClassification.discharge_summary:
            response = await _approve_discharge(db, ext=ext, doc=doc)
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"cannot approve a document with classification="
                    f"{doc.classification.value}"
                ),
            )
    except ExtractionResolverError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    ext.human_review_required = False
    ext.human_reviewed_by = user.user_id
    ext.human_reviewed_at = datetime.now(UTC)
    doc.status = DocumentStatus.reviewed

    await db.commit()
    return response
