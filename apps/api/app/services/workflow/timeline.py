"""Aggregate audit_logs rows for a workflow item (referral or discharge)
and its child tasks into a chronological event list."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
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


async def build_referral_timeline(
    session: AsyncSession, *, referral_id: UUID
) -> list[TimelineEvent]:
    return await _events_for_resource(
        session,
        parent_resource_type="referrals",
        parent_resource_id=referral_id,
        child_task_field=ReferralTask.referral_id,
    )


async def build_discharge_timeline(
    session: AsyncSession, *, discharge_id: UUID
) -> list[TimelineEvent]:
    return await _events_for_resource(
        session,
        parent_resource_type="discharge_summaries",
        parent_resource_id=discharge_id,
        child_task_field=ReferralTask.discharge_summary_id,
    )
