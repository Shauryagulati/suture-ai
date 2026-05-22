"""Authenticated appointment endpoints.

Currently exposes only `POST /api/appointments/{id}/cancel`, which flips
the appointment status to cancelled and triggers waitlist backfill.
Cancellation can also originate from the patient via the public
scheduling link in a later iteration; for v1 staff initiate.
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
from app.services.outreach.backfill import offer_cancelled_slot

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
