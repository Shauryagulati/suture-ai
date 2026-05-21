"""Aggregate audit_logs rows for a workflow item (referral or discharge)
and its child tasks into a chronological event list."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.outreach_attempt import OutreachAttempt
from app.models.referral_task import ReferralTask
from app.schemas.workflow import TimelineEvent


async def _events_for_resource(
    session: AsyncSession,
    *,
    parent_resource_type: str,
    parent_resource_id: UUID,
    child_task_field: Any,
) -> list[TimelineEvent]:
    task_ids = (
        (
            await session.execute(
                select(ReferralTask.id).where(child_task_field == parent_resource_id)
            )
        )
        .scalars()
        .all()
    )

    conditions = [
        (AuditLog.resource_type == parent_resource_type)
        & (AuditLog.resource_id == parent_resource_id)
    ]
    if task_ids:
        conditions.append(
            (AuditLog.resource_type == "referral_tasks")
            & (AuditLog.resource_id.in_(task_ids))
        )

    rows = (
        (
            await session.execute(
                select(AuditLog)
                .where(or_(*conditions))
                .order_by(AuditLog.timestamp.asc())
            )
        )
        .scalars()
        .all()
    )

    events: list[TimelineEvent] = []
    for row in rows:
        details = row.details or {}
        events.append(
            TimelineEvent(
                at=row.timestamp,
                actor_id=row.user_id,
                action=row.action.value if hasattr(row.action, "value") else str(row.action),
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                changed_columns=list(details.get("changed_columns", [])),
            )
        )
    return events


async def _outreach_events_for_parent(
    session: AsyncSession,
    *,
    referral_id: UUID | None = None,
    discharge_id: UUID | None = None,
) -> list[TimelineEvent]:
    """Render outreach attempts as timeline events. The event's `at` is
    `sent_at` if present (i.e., the attempt has fired), else the
    scheduled_at — so pending future attempts surface too."""
    q = select(OutreachAttempt)
    if referral_id is not None:
        q = q.where(OutreachAttempt.referral_id == referral_id)
    elif discharge_id is not None:
        q = q.where(OutreachAttempt.discharge_summary_id == discharge_id)
    else:
        return []
    rows = (await session.execute(q)).scalars().all()

    events: list[TimelineEvent] = []
    for r in rows:
        outcome = r.outcome or {}
        events.append(
            TimelineEvent(
                at=r.sent_at or r.scheduled_at,
                actor_id=None,
                action=f"outreach_{r.status.value}",
                resource_type="outreach_attempts",
                resource_id=r.id,
                changed_columns=[],
                metadata={
                    "channel": r.channel.value,
                    "attempt_number": r.attempt_number,
                    "scheduling_link_clicked": bool(
                        outcome.get("scheduling_link_clicked", False)
                    ),
                    "backfill_offered": bool(outcome.get("backfill_offered", False)),
                },
            )
        )
    return events


async def build_referral_timeline(
    session: AsyncSession, *, referral_id: UUID
) -> list[TimelineEvent]:
    audit = await _events_for_resource(
        session,
        parent_resource_type="referrals",
        parent_resource_id=referral_id,
        child_task_field=ReferralTask.referral_id,
    )
    outreach = await _outreach_events_for_parent(session, referral_id=referral_id)
    return sorted(audit + outreach, key=lambda e: e.at)


async def build_discharge_timeline(
    session: AsyncSession, *, discharge_id: UUID
) -> list[TimelineEvent]:
    audit = await _events_for_resource(
        session,
        parent_resource_type="discharge_summaries",
        parent_resource_id=discharge_id,
        child_task_field=ReferralTask.discharge_summary_id,
    )
    outreach = await _outreach_events_for_parent(session, discharge_id=discharge_id)
    return sorted(audit + outreach, key=lambda e: e.at)
