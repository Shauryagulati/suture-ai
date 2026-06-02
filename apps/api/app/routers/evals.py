"""Eval-run dashboard endpoints.

The harness writes EvalRun rows under a synthetic eval clinic. These
endpoints expose them to logged-in users; we keep the data
clinic-scoped (matching the model) so the existing tenant guard
applies. A user can only see eval runs from clinics they're a member of
— typically the eval clinic membership is granted in dev only.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.eval_run import EvalRun
from app.schemas.eval import (
    EvalCompareResponse,
    EvalFieldComparison,
    EvalRunDetail,
    EvalRunListItem,
    EvalRunListResponse,
)

router = APIRouter(prefix="/api/evals", tags=["evals"])


def _aggregate_metric(metrics: dict[str, Any] | None, key: str) -> float:
    if not isinstance(metrics, dict):
        return 0.0
    agg = metrics.get("aggregate")
    if not isinstance(agg, dict):
        return 0.0
    value = agg.get(key)
    return float(value) if isinstance(value, int | float) else 0.0


def _serialize_list_item(run: EvalRun) -> EvalRunListItem:
    return EvalRunListItem(
        id=run.id,
        eval_type=run.eval_type,
        test_set_version=run.test_set_version,
        num_samples=run.num_samples,
        run_duration_seconds=run.run_duration_seconds,
        prompt_version=run.prompt_version,
        model=run.model,
        created_at=run.created_at,
        exact_match_rate=_aggregate_metric(run.metrics, "exact_match_rate"),
        f1_macro=_aggregate_metric(run.metrics, "f1_macro"),
    )


@router.get("", response_model=EvalRunListResponse)
@router.get("/", response_model=EvalRunListResponse)
async def list_eval_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvalRunListResponse:
    stmt = select(EvalRun).order_by(desc(EvalRun.created_at)).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(select(func.count(EvalRun.id)))).scalar_one()
    return EvalRunListResponse(
        items=[_serialize_list_item(r) for r in rows],
        total=int(total),
    )


@router.get("/compare", response_model=EvalCompareResponse)
async def compare_eval_runs(
    run_a: UUID = Query(..., description="Baseline run id"),
    run_b: UUID = Query(..., description="Candidate run id"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvalCompareResponse:
    a = await db.get(EvalRun, run_a)
    b = await db.get(EvalRun, run_b)
    if a is None or b is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")

    a_per = (a.metrics or {}).get("per_field", {}) if isinstance(a.metrics, dict) else {}
    b_per = (b.metrics or {}).get("per_field", {}) if isinstance(b.metrics, dict) else {}
    if not isinstance(a_per, dict):
        a_per = {}
    if not isinstance(b_per, dict):
        b_per = {}

    fields: list[EvalFieldComparison] = []
    for key in sorted(set(a_per) | set(b_per)):
        ma = a_per.get(key) if isinstance(a_per.get(key), dict) else None
        mb = b_per.get(key) if isinstance(b_per.get(key), dict) else None
        acc_a = float(ma["accuracy"]) if ma and "accuracy" in ma else 0.0
        acc_b = float(mb["accuracy"]) if mb and "accuracy" in mb else 0.0
        fields.append(EvalFieldComparison(field=key, run_a=ma, run_b=mb, delta=acc_b - acc_a))

    agg_delta = _aggregate_metric(b.metrics, "exact_match_rate") - _aggregate_metric(
        a.metrics, "exact_match_rate"
    )
    return EvalCompareResponse(
        run_a_id=a.id, run_b_id=b.id, fields=fields, aggregate_delta=agg_delta
    )


@router.get("/{run_id}", response_model=EvalRunDetail)
async def get_eval_run(
    run_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvalRunDetail:
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="eval run not found")
    return EvalRunDetail.model_validate(run)
