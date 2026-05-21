"""DischargeSummary transition + timeline endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.discharge_summary import DischargeSummary
from app.schemas.workflow import (
    DischargeTransitionRequest,
    TimelineResponse,
    TransitionResponse,
)
from app.services.workflow.state_machine import (
    InvalidTransitionError,
    apply_discharge_transition,
)
from app.services.workflow.timeline import build_discharge_timeline

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


@router.get("/{discharge_id}/timeline", response_model=TimelineResponse)
async def discharge_timeline(
    discharge_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    await _get_discharge_or_404(db, discharge_id)
    events = await build_discharge_timeline(db, discharge_id=discharge_id)
    return TimelineResponse(events=events)
