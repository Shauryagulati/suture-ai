"""Patient registry endpoints — list/search + detail.

Search is limited to plaintext columns (name, MRN, city). dob/phone/ssn are
Fernet-encrypted (ADR 003) and therefore NOT searchable on value. Reads of a
single patient are audited via track_view; the list mirrors the existing
convention (documents/tasks lists are not per-row audited).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.patient import Patient
from app.schemas.patients import PatientDetail, PatientListItem, PatientListResponse
from app.utils.audit import track_view

router = APIRouter(prefix="/api/patients", tags=["patients"])


def _search_filter(q: str) -> ColumnElement[bool]:
    like = f"%{q.strip()}%"
    return or_(
        Patient.first_name.ilike(like),
        Patient.last_name.ilike(like),
        Patient.mrn.ilike(like),
        Patient.city.ilike(like),
    )


@router.get("/", response_model=PatientListResponse)
async def list_patients(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, description="Search name, MRN, or city"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PatientListResponse:
    stmt = select(Patient)
    count_stmt = select(func.count(Patient.id))
    if q and q.strip():
        stmt = stmt.where(_search_filter(q))
        count_stmt = count_stmt.where(_search_filter(q))

    total = int((await db.execute(count_stmt)).scalar_one())
    stmt = (
        stmt.order_by(Patient.last_name.asc(), Patient.first_name.asc()).limit(limit).offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return PatientListResponse(
        items=[PatientListItem.model_validate(p) for p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{patient_id}", response_model=PatientDetail)
async def get_patient(
    patient_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PatientDetail:
    patient = (
        await db.execute(select(Patient).where(Patient.id == patient_id))
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="patient not found")
    await db.run_sync(
        lambda sync_session: track_view(
            sync_session.connection(),
            resource_type="patients",
            resource_id=patient.id,
        )
    )
    # get_db does not auto-commit; the view-audit INSERT must be committed
    # explicitly or it rolls back when the session closes.
    await db.commit()
    return PatientDetail.model_validate(patient)
