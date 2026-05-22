"""Public patient-facing scheduling endpoints.

These endpoints are NOT authed by the staff JWT. Instead they accept a
signed scheduling token (issued when an outreach SMS/email is sent) and
extract the `clinic_id` from the token's claims. The clinic ID is then
written to the `current_clinic_id` ContextVar so the existing tenant
guard scopes every query to that clinic for the duration of the handler.

If the token is invalid, expired, or of the wrong type, the handler
returns 401 before touching the database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.outreach_attempt import OutreachAttempt, OutreachStatus
from app.models.patient import Patient
from app.models.provider import Provider, ProviderType
from app.models.referral import Referral
from app.schemas.scheduling import (
    AvailableSlotsResponse,
    BookSlotRequest,
    BookSlotResponse,
)
from app.services.outreach.scheduling import mock_available_slots
from app.utils.context import current_clinic_id
from app.utils.security import JwtError, decode_scheduling_token

router = APIRouter(prefix="/api/schedule", tags=["scheduling"])


def _decode_or_401(token: str) -> dict[str, str | None]:
    try:
        return decode_scheduling_token(token)
    except JwtError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc


@router.get("/{token}", response_model=AvailableSlotsResponse)
async def get_available_slots(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> AvailableSlotsResponse:
    """Decode the token, return patient greeting + mock slots."""
    claims = _decode_or_401(token)
    clinic_id = UUID(claims["clinic_id"])
    cid_token = current_clinic_id.set(clinic_id)
    try:
        patient = (
            await db.execute(
                select(Patient).where(Patient.id == UUID(claims["patient_id"]))
            )
        ).scalar_one_or_none()
        if patient is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="patient not found"
            )
        return AvailableSlotsResponse(
            patient_first_name=patient.first_name,
            slots=mock_available_slots(),
            outreach_attempt_id=UUID(claims["outreach_attempt_id"]),
            referral_id=UUID(claims["referral_id"]) if claims.get("referral_id") else None,
            discharge_summary_id=(
                UUID(claims["discharge_summary_id"])
                if claims.get("discharge_summary_id")
                else None
            ),
        )
    finally:
        current_clinic_id.reset(cid_token)


@router.post("/{token}/book", response_model=BookSlotResponse)
async def book_slot(
    token: str,
    body: BookSlotRequest,
    db: AsyncSession = Depends(get_db),
) -> BookSlotResponse:
    """Decode the token, create an Appointment, mark the originating
    OutreachAttempt as `responded`."""
    claims = _decode_or_401(token)
    clinic_id = UUID(claims["clinic_id"])
    cid_token = current_clinic_id.set(clinic_id)
    try:
        provider_id = await _pick_provider(db, claims)

        appt = Appointment(
            patient_id=UUID(claims["patient_id"]),
            provider_id=provider_id,
            referral_id=UUID(claims["referral_id"]) if claims.get("referral_id") else None,
            discharge_summary_id=(
                UUID(claims["discharge_summary_id"])
                if claims.get("discharge_summary_id")
                else None
            ),
            appointment_at=body.slot,
            appointment_type=body.appointment_type,
            status=AppointmentStatus.scheduled,
        )
        db.add(appt)
        await db.flush()

        attempt = (
            await db.execute(
                select(OutreachAttempt).where(
                    OutreachAttempt.id == UUID(claims["outreach_attempt_id"])
                )
            )
        ).scalar_one_or_none()
        if attempt is not None:
            attempt.status = OutreachStatus.responded
            attempt.outcome = {
                **(attempt.outcome or {}),
                "scheduling_link_clicked": True,
                "response_at": datetime.now(UTC).isoformat(),
                "appointment_id": str(appt.id),
            }

        # If this booking is against a discharge, advance the discharge
        # state machine. Tolerate a race where some other path already
        # moved it past patient_contacted — booking still succeeds.
        if claims.get("discharge_summary_id"):
            from app.models.discharge_summary import (
                DischargeStatus,
                DischargeSummary,
            )
            from app.services.workflow.state_machine import (
                InvalidTransitionError,
                apply_discharge_transition,
            )

            discharge = await db.get(
                DischargeSummary, UUID(claims["discharge_summary_id"])
            )
            if discharge is not None and discharge.status == DischargeStatus.patient_contacted:
                try:
                    await apply_discharge_transition(
                        db,
                        discharge=discharge,
                        target=DischargeStatus.scheduled,
                    )
                except InvalidTransitionError:
                    # Concurrent transition already advanced the workflow.
                    pass

        await db.commit()
        return BookSlotResponse(
            appointment_id=appt.id,
            appointment_at=appt.appointment_at,
            status=appt.status.value,
        )
    finally:
        current_clinic_id.reset(cid_token)


async def _pick_provider(db: AsyncSession, claims: dict[str, str | None]) -> UUID:
    """Choose which provider the booked appointment should reference.

    Preferred: the referral's assigned_provider_id. Fallback: any internal
    provider in the clinic. Raises 503 if the clinic has no internal
    providers configured."""
    if claims.get("referral_id"):
        referral = (
            await db.execute(
                select(Referral).where(Referral.id == UUID(claims["referral_id"]))
            )
        ).scalar_one_or_none()
        if referral is not None and referral.assigned_provider_id is not None:
            return referral.assigned_provider_id

    provider = (
        await db.execute(
            select(Provider).where(Provider.provider_type == ProviderType.internal).limit(1)
        )
    ).scalar_one_or_none()
    if provider is None:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="no internal providers configured for clinic",
        )
    return provider.id
