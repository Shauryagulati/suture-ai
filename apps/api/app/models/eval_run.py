"""EvalRun — evaluation harness run results.

Inherits ClinicScopedBase but eval runs are not strictly tenant data —
they're system data. The tenant guard tolerates them being scoped to a
clinic for now (we run evals in dev with a fixed clinic context). The
seed script assigns them to clinic-0 if needed.
"""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class EvalType(enum.StrEnum):
    extraction = "extraction"
    retrieval = "retrieval"
    voice = "voice"
    workflow = "workflow"


class EvalRun(ClinicScopedBase):
    __tablename__ = "eval_runs"

    eval_type: Mapped[EvalType] = mapped_column(
        Enum(EvalType, name="eval_type"), nullable=False, index=True
    )
    test_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    num_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    run_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
