"""Authenticated outreach endpoints — staff list, detail, history, trigger."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.discharge_summary import DischargeSummary
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.referral import Referral
from app.schemas.outreach import (
    OutreachAttemptListResponse,
    OutreachAttemptResponse,
    TriggerOutreachResponse,
)
from app.services.outreach.orchestrator import (
    next_attempt_number_for_discharge,
    next_attempt_number_for_referral,
    schedule_outreach_sequence,
)
from app.utils.audit import track_view

router = APIRouter(prefix="/api/outreach", tags=["outreach"])


async def _track_view(db: AsyncSession, resource_id: UUID) -> None:
    from sqlalchemy.orm import Session as SyncSession

    def _emit(sync_session: SyncSession) -> None:
        track_view(
            sync_session.connection(),
            resource_type="outreach_attempts",
            resource_id=resource_id,
        )

    await db.run_sync(_emit)


@router.get("", response_model=OutreachAttemptListResponse)
async def list_attempts(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    channel: OutreachChannel | None = None,
    status: OutreachStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OutreachAttemptListResponse:
    q = (
        select(OutreachAttempt)
        .order_by(OutreachAttempt.scheduled_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if channel is not None:
        q = q.where(OutreachAttempt.channel == channel)
    if status is not None:
        q = q.where(OutreachAttempt.status == status)
    rows = (await db.execute(q)).scalars().all()
    return OutreachAttemptListResponse(
        items=[OutreachAttemptResponse.from_model(r) for r in rows]
    )


@router.get("/patient/{patient_id}", response_model=OutreachAttemptListResponse)
async def patient_history(
    patient_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OutreachAttemptListResponse:
    rows = (
        (
            await db.execute(
                select(OutreachAttempt)
                .where(OutreachAttempt.patient_id == patient_id)
                .order_by(OutreachAttempt.scheduled_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return OutreachAttemptListResponse(
        items=[OutreachAttemptResponse.from_model(r) for r in rows]
    )


@router.get("/{attempt_id}", response_model=OutreachAttemptResponse)
async def get_attempt(
    attempt_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OutreachAttemptResponse:
    attempt = (
        await db.execute(
            select(OutreachAttempt).where(OutreachAttempt.id == attempt_id)
        )
    ).scalar_one_or_none()
    if attempt is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="outreach attempt not found"
        )
    await _track_view(db, attempt.id)
    await db.commit()
    return OutreachAttemptResponse.from_model(attempt)


@router.post("/trigger/referral/{referral_id}", response_model=TriggerOutreachResponse)
async def trigger_for_referral(
    referral_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TriggerOutreachResponse:
    referral = (
        await db.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one_or_none()
    if referral is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="referral not found"
        )
    next_num = await next_attempt_number_for_referral(db, referral_id=referral.id)
    attempts = await schedule_outreach_sequence(
        db, referral=referral, attempt_number=next_num
    )
    await db.commit()
    return TriggerOutreachResponse(
        attempt_ids=[a.id for a in attempts], attempt_number=next_num
    )


@router.post(
    "/trigger/discharge/{discharge_id}", response_model=TriggerOutreachResponse
)
async def trigger_for_discharge(
    discharge_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TriggerOutreachResponse:
    discharge = (
        await db.execute(
            select(DischargeSummary).where(DischargeSummary.id == discharge_id)
        )
    ).scalar_one_or_none()
    if discharge is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="discharge not found"
        )
    next_num = await next_attempt_number_for_discharge(db, discharge_id=discharge.id)
    attempts = await schedule_outreach_sequence(
        db, discharge=discharge, attempt_number=next_num
    )
    await db.commit()
    return TriggerOutreachResponse(
        attempt_ids=[a.id for a in attempts], attempt_number=next_num
    )
