"""Status state machine for workflow items.

Two transition tables — REFERRAL_TRANSITIONS and DISCHARGE_TRANSITIONS —
map a current status to the set of statuses it may move to. The
`validate_*` functions raise InvalidTransitionError on illegal moves.

The DB-coupled `apply_*_transition` functions live alongside these in a
later phase; this file only owns validation today.
"""
from __future__ import annotations

from app.models.discharge_summary import DischargeStatus
from app.models.referral import ReferralStatus


class InvalidTransitionError(ValueError):
    """Raised when a status transition is not allowed."""


REFERRAL_TRANSITIONS: dict[ReferralStatus, frozenset[ReferralStatus]] = {
    ReferralStatus.new: frozenset(
        {ReferralStatus.needs_review, ReferralStatus.cancelled}
    ),
    ReferralStatus.needs_review: frozenset(
        {
            ReferralStatus.missing_info,
            ReferralStatus.ready_to_schedule,
            ReferralStatus.cancelled,
        }
    ),
    ReferralStatus.missing_info: frozenset(
        {
            ReferralStatus.needs_review,
            ReferralStatus.ready_to_schedule,
            ReferralStatus.cancelled,
        }
    ),
    ReferralStatus.ready_to_schedule: frozenset(
        {
            ReferralStatus.auth_needed,
            ReferralStatus.scheduled,
            ReferralStatus.cancelled,
        }
    ),
    ReferralStatus.auth_needed: frozenset(
        {
            ReferralStatus.ready_to_schedule,
            ReferralStatus.scheduled,
            ReferralStatus.cancelled,
        }
    ),
    ReferralStatus.scheduled: frozenset(
        {
            ReferralStatus.completed,
            ReferralStatus.at_risk,
            ReferralStatus.cancelled,
        }
    ),
    ReferralStatus.at_risk: frozenset(
        {ReferralStatus.scheduled, ReferralStatus.cancelled}
    ),
    ReferralStatus.completed: frozenset(),
    ReferralStatus.cancelled: frozenset(),
}


DISCHARGE_TRANSITIONS: dict[DischargeStatus, frozenset[DischargeStatus]] = {
    DischargeStatus.new: frozenset(
        {DischargeStatus.patient_contacted, DischargeStatus.at_risk}
    ),
    DischargeStatus.patient_contacted: frozenset(
        {DischargeStatus.scheduled, DischargeStatus.at_risk}
    ),
    DischargeStatus.scheduled: frozenset(
        {DischargeStatus.seen, DischargeStatus.at_risk}
    ),
    DischargeStatus.seen: frozenset({DischargeStatus.confirmation_sent}),
    DischargeStatus.at_risk: frozenset({DischargeStatus.scheduled}),
    DischargeStatus.confirmation_sent: frozenset(),
}


def validate_referral_transition(
    current: ReferralStatus, target: ReferralStatus
) -> None:
    allowed = REFERRAL_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(
            f"ReferralStatus.{current.value} -> {target.value} is not allowed"
        )


def validate_discharge_transition(
    current: DischargeStatus, target: DischargeStatus
) -> None:
    allowed = DISCHARGE_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(
            f"DischargeStatus.{current.value} -> {target.value} is not allowed"
        )


# ────────────────────────────────────────────────────────────────────
# DB-integrated transition application (Phase 4)
# ────────────────────────────────────────────────────────────────────

from datetime import datetime  # noqa: E402
from uuid import UUID  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.models.discharge_summary import DischargeSummary  # noqa: E402
from app.models.referral import Referral  # noqa: E402
from app.models.referral_task import ReferralTask, TaskStatus  # noqa: E402
from app.services.workflow.sla import business_days_for_urgency, calculate_due_at  # noqa: E402
from app.services.workflow.templates import (  # noqa: E402
    TaskSpec,
    discharge_task_specs,
    referral_task_specs,
)


async def apply_referral_transition(
    session: AsyncSession,
    *,
    referral: Referral,
    target: ReferralStatus,
) -> Referral:
    """Validate and apply a transition. Idempotently emits tasks on entry
    to `ready_to_schedule`. Caller commits."""
    validate_referral_transition(referral.status, target)
    referral.status = target
    if target == ReferralStatus.ready_to_schedule:
        await _generate_tasks_for_referral(session, referral)
        # Late import: state_machine is imported by workflow startup;
        # outreach orchestrator imports state_machine indirectly via
        # security helpers. Local import keeps the module-init graph acyclic.
        from app.services.outreach.orchestrator import schedule_outreach_sequence

        await schedule_outreach_sequence(session, referral=referral)
    return referral


async def apply_discharge_transition(
    session: AsyncSession,
    *,
    discharge: DischargeSummary,
    target: DischargeStatus,
) -> DischargeSummary:
    validate_discharge_transition(discharge.status, target)
    discharge.status = target
    if target == DischargeStatus.patient_contacted:
        await _generate_tasks_for_discharge(session, discharge)
        from app.services.outreach.orchestrator import schedule_outreach_sequence

        await schedule_outreach_sequence(session, discharge=discharge)
    return discharge


async def _existing_task_count_for_referral(
    session: AsyncSession, referral_id: UUID
) -> int:
    rows = (
        (
            await session.execute(
                select(ReferralTask.id).where(
                    ReferralTask.referral_id == referral_id,
                    ReferralTask.status != TaskStatus.cancelled,
                )
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


async def _existing_task_count_for_discharge(
    session: AsyncSession, discharge_id: UUID
) -> int:
    rows = (
        (
            await session.execute(
                select(ReferralTask.id).where(
                    ReferralTask.discharge_summary_id == discharge_id,
                    ReferralTask.status != TaskStatus.cancelled,
                )
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


async def _generate_tasks_for_referral(
    session: AsyncSession, referral: Referral
) -> None:
    if await _existing_task_count_for_referral(session, referral.id) > 0:
        return
    due_at = calculate_due_at(referral.urgency)
    sla_hours = business_days_for_urgency(referral.urgency) * 24
    for spec in referral_task_specs(referral):
        session.add(
            _spec_to_task(spec, referral=referral, due_at=due_at, sla_hours=sla_hours)
        )


async def _generate_tasks_for_discharge(
    session: AsyncSession, discharge: DischargeSummary
) -> None:
    if await _existing_task_count_for_discharge(session, discharge.id) > 0:
        return
    due_at = calculate_due_at(discharge.urgency_tier)
    sla_hours = business_days_for_urgency(discharge.urgency_tier) * 24
    for spec in discharge_task_specs(discharge):
        session.add(
            _spec_to_task(spec, discharge=discharge, due_at=due_at, sla_hours=sla_hours)
        )


def _spec_to_task(
    spec: TaskSpec,
    *,
    referral: Referral | None = None,
    discharge: DischargeSummary | None = None,
    due_at: datetime,
    sla_hours: int,
) -> ReferralTask:
    if (referral is None) == (discharge is None):
        raise ValueError("exactly one of referral / discharge must be provided")
    parent: Referral | DischargeSummary = referral if referral is not None else discharge  # type: ignore[assignment]
    return ReferralTask(
        clinic_id=parent.clinic_id,
        patient_id=parent.patient_id,
        referral_id=referral.id if referral else None,
        discharge_summary_id=discharge.id if discharge else None,
        task_type=spec.task_type,
        title=spec.title,
        description=spec.description,
        status=TaskStatus.pending,
        priority=spec.priority,
        due_at=due_at,
        sla_hours=sla_hours,
    )
