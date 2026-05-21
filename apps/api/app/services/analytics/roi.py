"""Date-range ROI report.

Constants are deliberately conservative and hard-coded; per-clinic
overrides are deferred to v2."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    Document,
    DocumentStatus,
    PriorAuth,
    PriorAuthStatus,
    Referral,
)
from app.schemas.analytics import RoiReport
from app.services.analytics.leakage import compute_leakage_summary

MANUAL_MINUTES_PER_DOC = 15
AVG_VISIT_VALUE_CENTS = 25_000  # $250.00

_APPROVED = {PriorAuthStatus.approved, PriorAuthStatus.appeal_approved}
_DENIED = {PriorAuthStatus.denied, PriorAuthStatus.appeal_denied}


async def compute_roi_report(
    db: AsyncSession, *, from_date: date, to_date: date
) -> RoiReport:
    from_dt = datetime.combine(from_date, time.min, tzinfo=UTC)
    to_dt = datetime.combine(to_date, time.max, tzinfo=UTC)

    docs_processed = (
        await db.execute(
            select(func.count(Document.id)).where(
                Document.status == DocumentStatus.processed,
                Document.created_at >= from_dt,
                Document.created_at <= to_dt,
            )
        )
    ).scalar_one()

    leakage = await compute_leakage_summary(db)

    decided_window = (
        await db.execute(
            select(PriorAuth.status, PriorAuth.approved_at, PriorAuth.denied_at).where(
                PriorAuth.status.in_(_APPROVED | _DENIED),
            )
        )
    ).all()
    in_window: list[bool] = []
    for status, approved_at, denied_at in decided_window:
        decided = approved_at or denied_at
        if decided is None:
            continue
        if from_dt <= decided <= to_dt:
            in_window.append(status in _APPROVED)
    approval_rate: float | None
    if in_window:
        approval_rate = sum(1 for x in in_window if x) / len(in_window)
    else:
        approval_rate = None

    pairs = (
        await db.execute(
            select(Referral.created_at, Appointment.appointment_at)
            .join(Appointment, Appointment.referral_id == Referral.id)
            .where(
                Referral.created_at >= from_dt,
                Referral.created_at <= to_dt,
            )
        )
    ).all()
    avg_days: float | None
    if pairs:
        avg_days = sum((a - r).total_seconds() / 86400.0 for r, a in pairs) / len(
            pairs
        )
    else:
        avg_days = None

    return RoiReport(
        from_date=from_date,
        to_date=to_date,
        documents_processed=int(docs_processed),
        hours_saved=round(int(docs_processed) * MANUAL_MINUTES_PER_DOC / 60.0, 2),
        referrals_at_risk=leakage.at_risk_count,
        projected_revenue_recovered_cents=leakage.at_risk_count * AVG_VISIT_VALUE_CENTS,
        prior_auth_approval_rate=approval_rate,
        avg_days_referral_to_appointment=avg_days,
    )
