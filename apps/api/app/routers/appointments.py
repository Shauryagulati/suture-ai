"""Authenticated appointment endpoints.

- POST /api/appointments/{id}/cancel   — flip to cancelled + backfill
- POST /api/appointments/{id}/complete — mark the visit as done. If the
  appointment is linked to a discharge in status=scheduled, the
  discharge is advanced to `seen` in the same commit so the staff "mark
  seen" action drives the discharge state machine.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.appointment import Appointment, AppointmentStatus
from app.models.discharge_summary import DischargeStatus, DischargeSummary
from app.schemas.workflow import AppointmentCompleteResponse
from app.services.outreach.backfill import offer_cancelled_slot
from app.services.workflow.state_machine import (
    InvalidTransitionError,
    apply_discharge_transition,
)

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


class CancelAppointmentResponse(BaseModel):
    appointment_id: UUID
    status: str
    backfill_attempt_ids: list[UUID]


@router.post("/{appointment_id}/cancel", response_model=CancelAppointmentResponse)
async def cancel_appointment(
    appointment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CancelAppointmentResponse:
    appt = (
        await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    ).scalar_one_or_none()
    if appt is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="appointment not found"
        )
    appt.status = AppointmentStatus.cancelled
    backfill_attempts = await offer_cancelled_slot(db, appointment_id=appt.id)
    await db.commit()
    return CancelAppointmentResponse(
        appointment_id=appt.id,
        status=appt.status.value,
        backfill_attempt_ids=[a.id for a in backfill_attempts],
    )


@router.post("/{appointment_id}/complete", response_model=AppointmentCompleteResponse)
async def complete_appointment(
    appointment_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AppointmentCompleteResponse:
    """Mark a scheduled appointment as completed. If a discharge is
    linked and still in `scheduled`, advance it to `seen`. Idempotent:
    re-calling on an already-completed appointment returns current state."""
    appt = (
        await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    ).scalar_one_or_none()
    if appt is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="appointment not found"
        )

    discharge_status_value: str | None = None

    if appt.status == AppointmentStatus.completed:
        # Already completed — surface the linked discharge's current status if any.
        if appt.discharge_summary_id is not None:
            d = (
                await db.execute(
                    select(DischargeSummary).where(DischargeSummary.id == appt.discharge_summary_id)
                )
            ).scalar_one_or_none()
            if d is not None:
                discharge_status_value = d.status.value
        return AppointmentCompleteResponse(
            appointment_id=appt.id,
            appointment_status=appt.status.value,
            discharge_status=discharge_status_value,
        )

    appt.status = AppointmentStatus.completed

    if appt.discharge_summary_id is not None:
        discharge = (
            await db.execute(
                select(DischargeSummary).where(DischargeSummary.id == appt.discharge_summary_id)
            )
        ).scalar_one_or_none()
        if discharge is not None and discharge.status == DischargeStatus.scheduled:
            try:
                await apply_discharge_transition(
                    db, discharge=discharge, target=DischargeStatus.seen
                )
            except InvalidTransitionError as exc:
                raise HTTPException(
                    status_code=http_status.HTTP_409_CONFLICT, detail=str(exc)
                ) from exc
        if discharge is not None:
            discharge_status_value = discharge.status.value

    await db.commit()
    return AppointmentCompleteResponse(
        appointment_id=appt.id,
        appointment_status=appt.status.value,
        discharge_status=discharge_status_value,
    )
