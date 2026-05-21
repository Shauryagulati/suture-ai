"""Celery tasks for the outreach pipeline.

Two periodic tasks:
- process_pending_outreach (every 5m) — find pending attempts whose
  scheduled_at has passed, dispatch the send.
- check_outreach_responses (every 15m) — flip stale `sent` attempts
  that never got a response to `no_response` after 72h so they don't
  block future cadence rounds.

Both iterate clinics individually and set `current_clinic_id`
per-clinic so the tenant guard applies.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.database import async_session_maker
from app.models.clinic import Clinic
from app.models.outreach_attempt import OutreachAttempt, OutreachStatus
from app.services.outreach.orchestrator import execute_outreach_attempt
from app.utils.context import current_clinic_id, current_user_id
from services.workers.app import celery_app
from services.workers.async_bridge import run_async_unscoped


@celery_app.task(name="services.workers.outreach_tasks.process_pending_outreach")
def process_pending_outreach() -> dict:
    """Find pending OutreachAttempt rows with scheduled_at <= now and
    dispatch them through the per-channel send service."""

    async def _impl() -> dict:
        sent = 0
        failed = 0
        async with async_session_maker() as session:
            # Clinic is GlobalBase — no tenant context needed.
            clinic_rows = (await session.execute(select(Clinic.id))).scalars().all()

        for clinic_id in clinic_rows:
            cid_token = current_clinic_id.set(clinic_id)
            uid_token = current_user_id.set(None)
            try:
                s, f = await _process_clinic_outreach(clinic_id)
                sent += s
                failed += f
            finally:
                current_clinic_id.reset(cid_token)
                current_user_id.reset(uid_token)
        return {"sent": sent, "failed": failed}

    return run_async_unscoped(_impl)


async def _process_clinic_outreach(clinic_id: UUID) -> tuple[int, int]:
    sent = 0
    failed = 0
    async with async_session_maker() as session:
        due = (
            (
                await session.execute(
                    select(OutreachAttempt).where(
                        OutreachAttempt.status == OutreachStatus.pending,
                        OutreachAttempt.scheduled_at <= datetime.now(UTC),
                    )
                )
            )
            .scalars()
            .all()
        )
        for attempt in due:
            result = await execute_outreach_attempt(session, attempt_id=attempt.id)
            if result.delivered:
                sent += 1
            else:
                failed += 1
        await session.commit()
    return sent, failed


@celery_app.task(name="services.workers.outreach_tasks.check_outreach_responses")
def check_outreach_responses() -> dict:
    """Periodic stale-flipper. Real response webhooks arrive in v2; v1
    just marks anything `sent` more than 72h ago as `no_response` so the
    next cadence round can be triggered manually if needed."""

    async def _impl() -> dict:
        flipped = 0
        async with async_session_maker() as session:
            clinic_rows = (await session.execute(select(Clinic.id))).scalars().all()
        for clinic_id in clinic_rows:
            cid_token = current_clinic_id.set(clinic_id)
            uid_token = current_user_id.set(None)
            try:
                flipped += await _flip_stale_for_clinic(clinic_id)
            finally:
                current_clinic_id.reset(cid_token)
                current_user_id.reset(uid_token)
        return {"flipped": flipped}

    return run_async_unscoped(_impl)


async def _flip_stale_for_clinic(clinic_id: UUID) -> int:
    flipped = 0
    cutoff = datetime.now(UTC) - timedelta(hours=72)
    async with async_session_maker() as session:
        stale = (
            (
                await session.execute(
                    select(OutreachAttempt).where(
                        OutreachAttempt.status == OutreachStatus.sent,
                        OutreachAttempt.sent_at.is_not(None),
                        OutreachAttempt.sent_at < cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        for a in stale:
            a.status = OutreachStatus.no_response
            flipped += 1
        await session.commit()
    return flipped
