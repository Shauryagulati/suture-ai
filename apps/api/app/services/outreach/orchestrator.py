"""Outreach orchestrator — materializes the cadence + dispatches sends.

Two responsibilities:
1. `schedule_outreach_sequence` — given a referral or discharge, INSERTs N
   OutreachAttempt rows with future `scheduled_at` and `status=pending`,
   generating a signed scheduling-link token for the SMS attempt.
2. `execute_outreach_attempt` — given an attempt id, dispatches to the
   per-channel send service and mutates the attempt in place.

The beat task in `services.workers.outreach_tasks.process_pending_outreach`
polls for due `pending` rows every 5 minutes and calls
`execute_outreach_attempt` for each one. This gives us durability
(everything survives broker restarts) and easy introspection
("what outreach is queued?" is a simple SELECT).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.outreach.base import OutreachResult
from app.services.outreach.cadence import cadence_for_urgency
from app.services.outreach.email import send_email
from app.services.outreach.scheduling import build_scheduling_link_url
from app.services.outreach.sms import send_sms
from app.services.outreach.voice import initiate_voice_call
from app.utils.logging import get_logger
from app.utils.security import encode_scheduling_token

log = get_logger(__name__)


async def schedule_outreach_sequence(
    session: AsyncSession,
    *,
    referral: Referral | None = None,
    discharge: DischargeSummary | None = None,
    attempt_number: int = 1,
    now: datetime | None = None,
) -> list[OutreachAttempt]:
    """Materialize the cadence as pending OutreachAttempt rows.

    Exactly one of `referral` / `discharge` must be provided. At
    `attempt_number=1` this is idempotent: if any attempt already exists
    for the referral / discharge, the existing rows are returned
    untouched. Higher `attempt_number` is used by the manual re-trigger
    endpoint to schedule a fresh sequence after a previous round
    completed without response.
    """
    if (referral is None) == (discharge is None):
        raise ValueError("exactly one of referral / discharge must be provided")
    parent: Referral | DischargeSummary = referral if referral is not None else discharge  # type: ignore[assignment]
    urgency: UrgencyTier | UrgencyLevel = (
        referral.urgency if referral is not None else discharge.urgency_tier  # type: ignore[union-attr]
    )
    now = now or datetime.now(UTC)

    if attempt_number == 1:
        existing_q = select(OutreachAttempt)
        if referral is not None:
            existing_q = existing_q.where(OutreachAttempt.referral_id == referral.id)
        else:
            assert discharge is not None
            existing_q = existing_q.where(
                OutreachAttempt.discharge_summary_id == discharge.id
            )
        existing = (await session.execute(existing_q)).scalars().all()
        if existing:
            return list(existing)

    steps = cadence_for_urgency(urgency)
    created: list[OutreachAttempt] = []
    for channel, offset_hours in steps:
        attempt = OutreachAttempt(
            patient_id=parent.patient_id,
            referral_id=referral.id if referral is not None else None,
            discharge_summary_id=discharge.id if discharge is not None else None,
            channel=channel,
            status=OutreachStatus.pending,
            scheduled_at=now + timedelta(hours=offset_hours),
            outcome={},
            attempt_number=attempt_number,
        )
        session.add(attempt)
        await session.flush()
        # Generate the scheduling link for the SMS attempt up-front so the
        # link can be referenced from the timeline even before send time.
        if channel == OutreachChannel.sms:
            token, _ = encode_scheduling_token(
                patient_id=parent.patient_id,
                clinic_id=parent.clinic_id,
                outreach_attempt_id=attempt.id,
                referral_id=referral.id if referral is not None else None,
                discharge_summary_id=discharge.id if discharge is not None else None,
            )
            attempt.scheduling_link_url = build_scheduling_link_url(token)
        created.append(attempt)
    return created


async def execute_outreach_attempt(
    session: AsyncSession, *, attempt_id: UUID
) -> OutreachResult:
    """Dispatch the attempt to the matching per-channel send service.

    Skips (returns delivered=False, error="not pending") if the attempt
    has already been sent or responded to — defensive against double
    delivery if the beat task fires twice."""
    attempt = (
        await session.execute(
            select(OutreachAttempt).where(OutreachAttempt.id == attempt_id)
        )
    ).scalar_one()
    if attempt.status != OutreachStatus.pending:
        log.info(
            "outreach.skip_non_pending",
            attempt_id=str(attempt_id),
            status=attempt.status.value,
        )
        return OutreachResult(delivered=False, error="not pending")

    patient = (
        await session.execute(select(Patient).where(Patient.id == attempt.patient_id))
    ).scalar_one()
    clinic = (
        await session.execute(select(Clinic).where(Clinic.id == attempt.clinic_id))
    ).scalar_one()
    urgency = await _resolve_urgency(session, attempt)

    if attempt.channel == OutreachChannel.sms:
        return await send_sms(
            attempt=attempt,
            patient=patient,
            urgency=urgency,
            scheduling_link_url=attempt.scheduling_link_url or "",
        )

    if attempt.channel == OutreachChannel.email:
        # Email's scheduling link is generated lazily at send time so the
        # email URL is distinct from the SMS URL (lets the timeline /
        # response webhook tell which channel the patient clicked).
        token, _ = encode_scheduling_token(
            patient_id=patient.id,
            clinic_id=clinic.id,
            outreach_attempt_id=attempt.id,
            referral_id=attempt.referral_id,
            discharge_summary_id=attempt.discharge_summary_id,
        )
        attempt.scheduling_link_url = build_scheduling_link_url(token)
        return await send_email(
            attempt=attempt,
            patient=patient,
            urgency=urgency,
            scheduling_link_url=attempt.scheduling_link_url,
            clinic_name=clinic.name,
        )

    if attempt.channel == OutreachChannel.voice:
        return await initiate_voice_call(
            session,
            attempt=attempt,
            patient=patient,
            urgency=urgency,
            clinic_name=clinic.name,
        )

    raise ValueError(f"unknown channel: {attempt.channel!r}")


async def _resolve_urgency(
    session: AsyncSession, attempt: OutreachAttempt
) -> UrgencyTier | UrgencyLevel:
    """Look up the parent referral / discharge's urgency.

    Falls back to `UrgencyLevel.unclassified` if neither parent exists
    (e.g., the parent was cancelled and FK was set NULL); the cadence
    config has a sensible default for that case."""
    if attempt.referral_id is not None:
        ref = (
            await session.execute(
                select(Referral).where(Referral.id == attempt.referral_id)
            )
        ).scalar_one_or_none()
        if ref is not None:
            return ref.urgency
    if attempt.discharge_summary_id is not None:
        disc = (
            await session.execute(
                select(DischargeSummary).where(
                    DischargeSummary.id == attempt.discharge_summary_id
                )
            )
        ).scalar_one_or_none()
        if disc is not None:
            return disc.urgency_tier
    return UrgencyLevel.unclassified


async def next_attempt_number_for_referral(
    session: AsyncSession, *, referral_id: UUID
) -> int:
    """Return the next attempt_number to use for re-triggering outreach
    on the given referral. Used by the manual trigger endpoint."""
    rows = (
        (
            await session.execute(
                select(OutreachAttempt.attempt_number).where(
                    OutreachAttempt.referral_id == referral_id
                )
            )
        )
        .scalars()
        .all()
    )
    return (max(rows) + 1) if rows else 1


async def next_attempt_number_for_discharge(
    session: AsyncSession, *, discharge_id: UUID
) -> int:
    rows = (
        (
            await session.execute(
                select(OutreachAttempt.attempt_number).where(
                    OutreachAttempt.discharge_summary_id == discharge_id
                )
            )
        )
        .scalars()
        .all()
    )
    return (max(rows) + 1) if rows else 1
