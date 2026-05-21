"""Celery tasks for the workflow engine."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.database import async_session_maker
from app.models.clinic import Clinic
from app.models.discharge_summary import DischargeStatus, DischargeSummary
from app.models.referral import Referral, ReferralStatus
from app.models.referral_task import ReferralTask, TaskStatus
from app.services.workflow.state_machine import (
    InvalidTransitionError,
    apply_discharge_transition,
    apply_referral_transition,
)
from app.utils.context import current_clinic_id, current_user_id
from services.workers.app import celery_app
from services.workers.async_bridge import run_async, run_async_unscoped


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


@celery_app.task(name="services.workers.tasks.check_overdue_tasks")
def check_overdue_tasks() -> dict:
    """Periodic task: flip past-due tasks to TaskStatus.overdue and
    escalate the parent referral/discharge to at_risk when valid.

    Iterates every clinic individually — the tenant guard blocks
    cross-clinic SELECTs, so we set current_clinic_id per iteration."""

    async def _impl() -> dict:
        flipped = 0
        async with async_session_maker() as session:
            # Clinic is GlobalBase — no tenant context needed.
            clinic_rows = (await session.execute(select(Clinic.id))).scalars().all()

        for clinic_id in clinic_rows:
            cid_token = current_clinic_id.set(clinic_id)
            uid_token = current_user_id.set(None)
            try:
                flipped += await _process_clinic_overdue(clinic_id)
            finally:
                current_clinic_id.reset(cid_token)
                current_user_id.reset(uid_token)
        return {"flipped": flipped}

    return run_async_unscoped(_impl)


async def _process_clinic_overdue(clinic_id: UUID) -> int:
    flipped = 0
    async with async_session_maker() as session:
        now = datetime.now(UTC)
        overdue_rows = (
            (
                await session.execute(
                    select(ReferralTask).where(
                        ReferralTask.due_at.is_not(None),
                        ReferralTask.due_at < now,
                        ReferralTask.status.in_(
                            [TaskStatus.pending, TaskStatus.in_progress]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )

        seen_referrals: set[UUID] = set()
        seen_discharges: set[UUID] = set()

        for task in overdue_rows:
            task.status = TaskStatus.overdue
            flipped += 1
            if task.referral_id is not None and task.referral_id not in seen_referrals:
                seen_referrals.add(task.referral_id)
                parent = (
                    await session.execute(
                        select(Referral).where(Referral.id == task.referral_id)
                    )
                ).scalar_one_or_none()
                if parent is not None and parent.status == ReferralStatus.scheduled:
                    try:
                        await apply_referral_transition(
                            session, referral=parent, target=ReferralStatus.at_risk
                        )
                    except InvalidTransitionError:
                        pass  # raced; ignore
            elif (
                task.discharge_summary_id is not None
                and task.discharge_summary_id not in seen_discharges
            ):
                seen_discharges.add(task.discharge_summary_id)
                parent_d = (
                    await session.execute(
                        select(DischargeSummary).where(
                            DischargeSummary.id == task.discharge_summary_id
                        )
                    )
                ).scalar_one_or_none()
                if parent_d is not None and parent_d.status in (
                    DischargeStatus.patient_contacted,
                    DischargeStatus.scheduled,
                ):
                    try:
                        await apply_discharge_transition(
                            session, discharge=parent_d, target=DischargeStatus.at_risk
                        )
                    except InvalidTransitionError:
                        pass
        await session.commit()
    return flipped
