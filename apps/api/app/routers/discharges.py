"""DischargeSummary endpoints — detail, transition, timeline, confirm, fax download."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.discharge_summary import DischargeStatus, DischargeSummary
from app.models.patient import Patient
from app.schemas.workflow import (
    ConfirmDischargeResponse,
    DischargeDetail,
    DischargeTransitionRequest,
    TimelineResponse,
    TransitionResponse,
)
from app.services.workflow.state_machine import (
    InvalidTransitionError,
    apply_discharge_transition,
)
from app.services.workflow.timeline import build_discharge_timeline
from app.utils.audit import track_view

router = APIRouter(prefix="/api/discharges", tags=["discharges"])


async def _get_discharge_or_404(session: AsyncSession, discharge_id: UUID) -> DischargeSummary:
    ds = (
        await session.execute(
            select(DischargeSummary).where(DischargeSummary.id == discharge_id)
        )
    ).scalar_one_or_none()
    if ds is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="discharge not found"
        )
    return ds


@router.get("/{discharge_id}", response_model=DischargeDetail)
async def get_discharge(
    discharge_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DischargeDetail:
    ds = await _get_discharge_or_404(db, discharge_id)
    patient = (
        await db.execute(select(Patient).where(Patient.id == ds.patient_id))
    ).scalar_one_or_none()
    if patient is None:
        # Patient FK is RESTRICT — should never happen, but fail loud if it does.
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="patient not found"
        )
    await db.run_sync(
        lambda sync_session: track_view(
            sync_session.connection(),
            resource_type="discharge_summaries",
            resource_id=ds.id,
        )
    )
    await db.commit()
    return DischargeDetail(
        id=ds.id,
        patient_id=ds.patient_id,
        patient_first_name=patient.first_name,
        patient_last_name=patient.last_name,
        status=ds.status,
        urgency_tier=ds.urgency_tier.value,
        discharge_date=ds.discharge_date.isoformat(),
        primary_diagnosis=ds.primary_diagnosis,
        diagnosis_codes=list(ds.diagnosis_codes),
        urgent_flags=list(ds.urgent_flags),
        follow_up_window_days=ds.follow_up_window_days,
        follow_up_deadline=ds.follow_up_deadline.isoformat() if ds.follow_up_deadline else None,
        recommended_specialist=ds.recommended_specialist,
        confirmation_fax_sent_at=ds.confirmation_fax_sent_at,
        confirmation_fax_path=ds.confirmation_fax_path,
    )


@router.post("/{discharge_id}/transition", response_model=TransitionResponse)
async def transition_discharge(
    discharge_id: UUID,
    body: DischargeTransitionRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransitionResponse:
    ds = await _get_discharge_or_404(db, discharge_id)
    try:
        await apply_discharge_transition(db, discharge=ds, target=body.target)
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(ds)
    return TransitionResponse(id=ds.id, status=ds.status.value)


@router.post("/{discharge_id}/confirm", response_model=ConfirmDischargeResponse)
async def confirm_discharge(
    discharge_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConfirmDischargeResponse:
    """Advance a `seen` discharge to `confirmation_sent` and fire the fax."""
    ds = await _get_discharge_or_404(db, discharge_id)
    if ds.status != DischargeStatus.seen:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=(
                f"can only confirm a discharge in status=seen; "
                f"current status={ds.status.value}"
            ),
        )
    try:
        await apply_discharge_transition(
            db, discharge=ds, target=DischargeStatus.confirmation_sent
        )
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(ds)
    return ConfirmDischargeResponse(
        discharge_id=ds.id,
        status=ds.status.value,
        confirmation_fax_sent_at=ds.confirmation_fax_sent_at,
        fax_available=ds.confirmation_fax_path is not None,
    )


@router.get("/{discharge_id}/fax")
async def download_confirmation_fax(
    discharge_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    ds = await _get_discharge_or_404(db, discharge_id)
    if not ds.confirmation_fax_path:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="no confirmation fax generated yet",
        )
    path = Path(ds.confirmation_fax_path)
    if not path.exists():
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="confirmation fax file missing on disk",
        )
    await db.run_sync(
        lambda sync_session: track_view(
            sync_session.connection(),
            resource_type="discharge_summaries",
            resource_id=ds.id,
            extra={"action": "download_fax"},
        )
    )
    await db.commit()
    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="discharge-{ds.id}-confirmation.pdf"'
            ),
        },
    )


@router.get("/{discharge_id}/timeline", response_model=TimelineResponse)
async def discharge_timeline(
    discharge_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    await _get_discharge_or_404(db, discharge_id)
    events = await build_discharge_timeline(db, discharge_id=discharge_id)
    return TimelineResponse(events=events)
