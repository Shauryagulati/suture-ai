"""WorkflowRun — Celery task tracking."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class WorkflowStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"


class WorkflowRun(ClinicScopedBase):
    __tablename__ = "workflow_runs"

    task_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, name="workflow_status"),
        nullable=False,
        default=WorkflowStatus.pending,
    )
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    output_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
