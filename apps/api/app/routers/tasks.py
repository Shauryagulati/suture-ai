"""Task management endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.referral_task import ReferralTask, TaskPriority, TaskStatus
from app.schemas.tasks import TaskListResponse, TaskOut, TaskPatch
from app.utils.audit import track_view

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status: TaskStatus | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    assignee: UUID | None = Query(default=None),
    overdue: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TaskListResponse:
    stmt = select(ReferralTask)
    if status is not None:
        stmt = stmt.where(ReferralTask.status == status)
    if priority is not None:
        stmt = stmt.where(ReferralTask.priority == priority)
    if assignee is not None:
        stmt = stmt.where(ReferralTask.assigned_to == assignee)
    if overdue is True:
        now = datetime.now(UTC)
        stmt = stmt.where(
            ReferralTask.due_at.is_not(None),
            ReferralTask.due_at < now,
            ReferralTask.status.in_(
                [TaskStatus.pending, TaskStatus.in_progress, TaskStatus.overdue]
            ),
        )

    # Count using an ORM-tracked select so do_orm_execute / with_loader_criteria
    # applies the clinic_id filter to the count just as it does to the fetch.
    count_stmt = select(func.count(ReferralTask.id))
    if status is not None:
        count_stmt = count_stmt.where(ReferralTask.status == status)
    if priority is not None:
        count_stmt = count_stmt.where(ReferralTask.priority == priority)
    if assignee is not None:
        count_stmt = count_stmt.where(ReferralTask.assigned_to == assignee)
    if overdue is True:
        count_stmt = count_stmt.where(
            ReferralTask.due_at.is_not(None),
            ReferralTask.due_at < now,
            ReferralTask.status.in_(
                [TaskStatus.pending, TaskStatus.in_progress, TaskStatus.overdue]
            ),
        )
    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar_one())
    stmt = (
        stmt.order_by(
            ReferralTask.due_at.asc().nulls_last(),
            ReferralTask.created_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    rows = (await db.execute(stmt)).scalars().all()
    return TaskListResponse(
        items=[TaskOut.model_validate(t) for t in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    task = (
        await db.execute(select(ReferralTask).where(ReferralTask.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="task not found")
    await db.run_sync(
        lambda sync_session: track_view(
            sync_session.connection(),
            resource_type="referral_tasks",
            resource_id=task.id,
        )
    )
    return TaskOut.model_validate(task)


@router.patch("/{task_id}", response_model=TaskOut)
async def patch_task(
    task_id: UUID,
    body: TaskPatch,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    task = (
        await db.execute(select(ReferralTask).where(ReferralTask.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="task not found")

    if body.status is not None:
        task.status = body.status
        if body.status == TaskStatus.completed and task.completed_at is None:
            task.completed_at = datetime.now(UTC)
            task.completed_by = user.user_id
    if body.assigned_to is not None:
        task.assigned_to = body.assigned_to
    if body.priority is not None:
        task.priority = body.priority
    if body.description is not None:
        task.description = body.description

    await db.commit()
    await db.refresh(task)
    return TaskOut.model_validate(task)
