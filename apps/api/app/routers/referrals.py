"""Referral transition + timeline endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.referral import Referral
from app.schemas.workflow import (
    ReferralTransitionRequest,
    TimelineResponse,
    TransitionResponse,
)
from app.services.workflow.state_machine import (
    InvalidTransitionError,
    apply_referral_transition,
)
from app.services.workflow.timeline import build_referral_timeline

router = APIRouter(prefix="/api/referrals", tags=["referrals"])


async def _get_referral_or_404(session: AsyncSession, referral_id: UUID) -> Referral:
    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one_or_none()
    if referral is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="referral not found")
    return referral


@router.post("/{referral_id}/transition", response_model=TransitionResponse)
async def transition_referral(
    referral_id: UUID,
    body: ReferralTransitionRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransitionResponse:
    referral = await _get_referral_or_404(db, referral_id)
    try:
        await apply_referral_transition(db, referral=referral, target=body.target)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(referral)
    return TransitionResponse(id=referral.id, status=referral.status.value)


@router.get("/{referral_id}/timeline", response_model=TimelineResponse)
async def referral_timeline(
    referral_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    await _get_referral_or_404(db, referral_id)
    events = await build_referral_timeline(db, referral_id=referral_id)
    return TimelineResponse(events=events)
