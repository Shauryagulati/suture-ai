"""Pydantic schemas for the eval-run dashboard API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.eval_run import EvalType


class EvalRunListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    eval_type: EvalType
    test_set_version: str
    num_samples: int
    run_duration_seconds: int
    prompt_version: str | None
    model: str | None
    created_at: datetime
    exact_match_rate: float
    f1_macro: float


class EvalRunListResponse(BaseModel):
    items: list[EvalRunListItem]
    total: int


class EvalRunDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    eval_type: EvalType
    test_set_version: str
    num_samples: int
    run_duration_seconds: int
    prompt_version: str | None
    model: str | None
    notes: str | None
    run_by: str | None
    created_at: datetime
    metrics: dict[str, Any]


class EvalFieldComparison(BaseModel):
    field: str
    run_a: dict[str, float] | None
    run_b: dict[str, float] | None
    delta: float


class EvalCompareResponse(BaseModel):
    run_a_id: UUID
    run_b_id: UUID
    fields: list[EvalFieldComparison]
    aggregate_delta: float
