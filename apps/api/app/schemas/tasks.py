"""Pydantic schemas for /api/tasks."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.referral_task import TaskPriority, TaskStatus, TaskType


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    clinic_id: UUID
    patient_id: UUID
    referral_id: UUID | None
    discharge_summary_id: UUID | None
    task_type: TaskType
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assigned_to: UUID | None
    completed_by: UUID | None
    due_at: datetime | None
    completed_at: datetime | None
    sla_hours: int | None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskOut]
    total: int
    limit: int
    offset: int


class TaskPatch(BaseModel):
    status: TaskStatus | None = None
    assigned_to: UUID | None = None
    priority: TaskPriority | None = None
    description: str | None = None
