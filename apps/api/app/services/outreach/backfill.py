"""Waitlist / cancellation backfill.

When an appointment is cancelled, find at-risk patients waiting on
similar care and offer them the freed slot via SMS. v1 ranks
candidates by referral age (oldest ready_to_schedule first) and caps
the offer to top N.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.referral import Referral, ReferralStatus
from app.services.outreach.scheduling import build_scheduling_link_url
from app.utils.security import encode_scheduling_token


async def offer_cancelled_slot(
    session: AsyncSession,
    *,
    appointment_id: UUID,
    top_n: int = 3,
) -> list[OutreachAttempt]:
    """Create up to `top_n` backfill SMS OutreachAttempts targeting the
    oldest ready_to_schedule referrals (excluding the patient whose
    appointment was just cancelled).

    Each attempt is scheduled for immediate send (scheduled_at=now) so
    the next beat tick picks it up. Outcome JSONB carries
    `backfill_offered=True` and the cancelled appointment id so the
    timeline can render it distinctly."""
    appt = (
        await session.execute(select(Appointment).where(Appointment.id == appointment_id))
    ).scalar_one()

    candidates = (
        (
            await session.execute(
                select(Referral)
                .where(
                    Referral.status == ReferralStatus.ready_to_schedule,
                    Referral.patient_id != appt.patient_id,
                )
                .order_by(Referral.created_at.asc())
                .limit(top_n)
            )
        )
        .scalars()
        .all()
    )

    now = datetime.now(UTC)
    created: list[OutreachAttempt] = []
    for ref in candidates:
        attempt = OutreachAttempt(
            patient_id=ref.patient_id,
            referral_id=ref.id,
            channel=OutreachChannel.sms,
            status=OutreachStatus.pending,
            scheduled_at=now,
            outcome={
                "backfill_offered": True,
                "cancelled_appointment_id": str(appt.id),
                "slot_at": appt.appointment_at.isoformat(),
                "appointment_type": appt.appointment_type,
            },
            attempt_number=1,
        )
        session.add(attempt)
        await session.flush()
        token, _ = encode_scheduling_token(
            patient_id=ref.patient_id,
            clinic_id=ref.clinic_id,
            outreach_attempt_id=attempt.id,
            referral_id=ref.id,
        )
        attempt.scheduling_link_url = build_scheduling_link_url(token)
        created.append(attempt)
    return created
