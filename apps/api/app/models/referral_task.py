"""ReferralTask — workflow item (call patient, request info, etc.)."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class TaskType(enum.StrEnum):
    call_patient = "call_patient"
    request_missing_info = "request_missing_info"
    verify_eligibility = "verify_eligibility"
    submit_prior_auth = "submit_prior_auth"
    schedule_appointment = "schedule_appointment"
    send_confirmation = "send_confirmation"
    follow_up = "follow_up"
    other = "other"


class TaskStatus(enum.StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    overdue = "overdue"


class TaskPriority(enum.StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class ReferralTask(ClinicScopedBase):
    __tablename__ = "referral_tasks"

    referral_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=True,
    )
    discharge_summary_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("discharge_summaries.id", ondelete="CASCADE"),
        nullable=True,
    )
    patient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_type: Mapped[TaskType] = mapped_column(Enum(TaskType, name="task_type"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        nullable=False,
        default=TaskStatus.pending,
        index=True,
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Renamed from due_date — instant, not calendar date. ADR 004.
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, name="task_priority"),
        nullable=False,
        default=TaskPriority.medium,
    )
    sla_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
