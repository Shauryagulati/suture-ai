"""Read-only analytics endpoints. All tenant-scoped via the SQLAlchemy
event listener — no manual clinic_id plumbing.

Mounted at /api/analytics:
  GET /dashboard            — composite payload for the dashboard page
  GET /leakage              — per-patient risk scores, sorted desc
  GET /payer-friction       — per-payer turnaround / approval / denials
  GET /referral-quality     — per-provider scorecard
  GET /roi                  — ?from=YYYY-MM-DD&to=YYYY-MM-DD (defaults last 30 days)
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.schemas.analytics import (
    DashboardPayload,
    LeakageSummary,
    PayerFrictionSummary,
    ReferralQualitySummary,
    RoiReport,
)
from app.services.analytics.leakage import compute_leakage_summary
from app.services.analytics.payer_friction import compute_payer_friction
from app.services.analytics.referral_quality import compute_referral_quality
from app.services.analytics.roi import compute_roi_report

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _default_window() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=30), today


@router.get("/leakage", response_model=LeakageSummary)
async def leakage(
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeakageSummary:
    return await compute_leakage_summary(db)


@router.get("/payer-friction", response_model=PayerFrictionSummary)
async def payer_friction(
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PayerFrictionSummary:
    return await compute_payer_friction(db)


@router.get("/referral-quality", response_model=ReferralQualitySummary)
async def referral_quality(
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReferralQualitySummary:
    return await compute_referral_quality(db)


@router.get("/roi", response_model=RoiReport)
async def roi(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoiReport:
    default_from, default_to = _default_window()
    return await compute_roi_report(
        db,
        from_date=from_date or default_from,
        to_date=to_date or default_to,
    )


@router.get("/dashboard", response_model=DashboardPayload)
async def dashboard(
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardPayload:
    default_from, default_to = _default_window()
    return DashboardPayload(
        leakage=await compute_leakage_summary(db),
        payer_friction=await compute_payer_friction(db),
        referral_quality=await compute_referral_quality(db),
        roi=await compute_roi_report(db, from_date=default_from, to_date=default_to),
    )
