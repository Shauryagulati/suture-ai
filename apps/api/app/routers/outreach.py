"""Authenticated outreach endpoints — staff list, detail, history, trigger."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.clinic import Clinic
from app.models.discharge_summary import DischargeSummary, UrgencyTier
from app.models.document import UrgencyLevel
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.models.referral import Referral
from app.schemas.outreach import (
    OutreachAttemptListResponse,
    OutreachAttemptResponse,
    OutreachDashboardResponse,
    OutreachDashboardRow,
    TriggerOutreachResponse,
)
from app.services.outreach.orchestrator import (
    next_attempt_number_for_discharge,
    next_attempt_number_for_referral,
    schedule_outreach_sequence,
)
from app.services.outreach.templates import (
    RenderedMessage,
    render_email,
    render_sms,
    render_voice_script_context,
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
    return OutreachAttemptListResponse(items=[OutreachAttemptResponse.from_model(r) for r in rows])


@router.get("/dashboard", response_model=OutreachDashboardResponse)
async def outreach_dashboard(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
) -> OutreachDashboardResponse:
    """Every outreach attempt enriched with the patient's name + the rendered
    message a patient would actually receive (reconstructed from the per-channel
    templates). Powers the staff outreach dashboard."""
    clinic = await db.get(Clinic, user.active_clinic_id)
    clinic_name = clinic.name if clinic is not None else "your clinic"

    attempts = (
        (
            await db.execute(
                select(OutreachAttempt).order_by(OutreachAttempt.scheduled_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    # Batch-load related rows so message rendering isn't an N+1.
    patients: dict[UUID, Patient] = {}
    pids = {a.patient_id for a in attempts}
    if pids:
        patients = {
            p.id: p
            for p in (await db.execute(select(Patient).where(Patient.id.in_(pids)))).scalars().all()
        }
    referrals: dict[UUID, Referral] = {}
    rids = {a.referral_id for a in attempts if a.referral_id}
    if rids:
        referrals = {
            r.id: r
            for r in (await db.execute(select(Referral).where(Referral.id.in_(rids))))
            .scalars()
            .all()
        }
    discharges: dict[UUID, DischargeSummary] = {}
    dids = {a.discharge_summary_id for a in attempts if a.discharge_summary_id}
    if dids:
        discharges = {
            d.id: d
            for d in (
                await db.execute(select(DischargeSummary).where(DischargeSummary.id.in_(dids)))
            )
            .scalars()
            .all()
        }

    items: list[OutreachDashboardRow] = []
    for a in attempts:
        patient = patients.get(a.patient_id)
        first = patient.first_name if patient is not None else "Patient"
        last = patient.last_name if patient is not None else ""
        related_type: str | None = None
        urgency: UrgencyTier | UrgencyLevel = UrgencyLevel.routine
        if a.referral_id and a.referral_id in referrals:
            urgency = referrals[a.referral_id].urgency
            related_type = "referral"
        elif a.discharge_summary_id and a.discharge_summary_id in discharges:
            urgency = discharges[a.discharge_summary_id].urgency_tier
            related_type = "discharge"

        link = a.scheduling_link_url or ""
        if a.channel == OutreachChannel.sms:
            msg = render_sms(patient_first_name=first, scheduling_link_url=link, urgency=urgency)
        elif a.channel == OutreachChannel.email:
            msg = render_email(
                patient_first_name=first,
                scheduling_link_url=link,
                urgency=urgency,
                clinic_name=clinic_name,
            )
        else:
            ctx = render_voice_script_context(
                patient_first_name=first, urgency=urgency, clinic_name=clinic_name
            )
            msg = RenderedMessage(body=ctx["greeting"])

        items.append(
            OutreachDashboardRow(
                id=a.id,
                channel=a.channel,
                status=a.status,
                scheduled_at=a.scheduled_at,
                sent_at=a.sent_at,
                attempt_number=a.attempt_number,
                patient_first_name=first,
                patient_last_name=last,
                related_type=related_type,
                message_subject=msg.subject,
                message_body=msg.body,
            )
        )
    return OutreachDashboardResponse(items=items)


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
    return OutreachAttemptListResponse(items=[OutreachAttemptResponse.from_model(r) for r in rows])


@router.get("/{attempt_id}", response_model=OutreachAttemptResponse)
async def get_attempt(
    attempt_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OutreachAttemptResponse:
    attempt = (
        await db.execute(select(OutreachAttempt).where(OutreachAttempt.id == attempt_id))
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
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="referral not found")
    next_num = await next_attempt_number_for_referral(db, referral_id=referral.id)
    attempts = await schedule_outreach_sequence(db, referral=referral, attempt_number=next_num)
    await db.commit()
    return TriggerOutreachResponse(attempt_ids=[a.id for a in attempts], attempt_number=next_num)


@router.post("/trigger/discharge/{discharge_id}", response_model=TriggerOutreachResponse)
async def trigger_for_discharge(
    discharge_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TriggerOutreachResponse:
    discharge = (
        await db.execute(select(DischargeSummary).where(DischargeSummary.id == discharge_id))
    ).scalar_one_or_none()
    if discharge is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="discharge not found"
        )
    next_num = await next_attempt_number_for_discharge(db, discharge_id=discharge.id)
    attempts = await schedule_outreach_sequence(db, discharge=discharge, attempt_number=next_num)
    await db.commit()
    return TriggerOutreachResponse(attempt_ids=[a.id for a in attempts], attempt_number=next_num)
