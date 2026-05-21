"""Celery tasks for the workflow engine."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.database import async_session_maker
from app.models.referral import Referral, ReferralStatus
from app.services.workflow.state_machine import apply_referral_transition
from services.workers.app import celery_app
from services.workers.async_bridge import run_async


@celery_app.task(name="services.workers.tasks.process_document_workflow")
def process_document_workflow(
    *,
    referral_id: str,
    clinic_id: str,
    user_id: str | None = None,
    target_status: str,
) -> dict:
    """Run a state-machine transition outside the HTTP request cycle.

    Called by Module 2 after extraction completes and the human approves.
    """
    async def _impl() -> dict:
        async with async_session_maker() as session:
            referral = (
                await session.execute(
                    select(Referral).where(Referral.id == UUID(referral_id))
                )
            ).scalar_one()
            await apply_referral_transition(
                session, referral=referral, target=ReferralStatus(target_status)
            )
            await session.commit()
            return {"referral_id": str(referral.id), "status": referral.status.value}

    return run_async(
        _impl,
        clinic_id=UUID(clinic_id),
        user_id=UUID(user_id) if user_id else None,
    )


# check_overdue_tasks is implemented in Phase 8.
