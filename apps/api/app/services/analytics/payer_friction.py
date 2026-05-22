"""Per-payer prior-auth friction metrics.

Pure Python aggregation — pulls all current-clinic prior_auths +
denial events in two queries, then reduces in memory. The
denormalized payer_name on prior_auths means there is no payer table
to join against."""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriorAuth, PriorAuthEvent, PriorAuthEventType, PriorAuthStatus
from app.schemas.analytics import PayerFrictionRow, PayerFrictionSummary

_PENDING_STATES = {
    PriorAuthStatus.checking,
    PriorAuthStatus.required,
    PriorAuthStatus.submitted,
    PriorAuthStatus.appealing,
}
_DENIED_STATES = {PriorAuthStatus.denied, PriorAuthStatus.appeal_denied}
_APPROVED_STATES = {PriorAuthStatus.approved, PriorAuthStatus.appeal_approved}


async def compute_payer_friction(db: AsyncSession) -> PayerFrictionSummary:
    auths = (await db.execute(select(PriorAuth))).scalars().all()
    if not auths:
        return PayerFrictionSummary(rows=[])

    denial_events = (
        (
            await db.execute(
                select(PriorAuthEvent).where(
                    PriorAuthEvent.event_type.in_(
                        {PriorAuthEventType.denied, PriorAuthEventType.appeal_denied}
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    reasons_by_auth: dict[UUID, list[str]] = {}
    for ev in denial_events:
        reason = (ev.details or {}).get("reason")
        if isinstance(reason, str) and reason.strip():
            reasons_by_auth.setdefault(ev.prior_auth_id, []).append(reason.strip())

    buckets: dict[str, list[PriorAuth]] = {}
    for a in auths:
        buckets.setdefault(a.payer_name, []).append(a)

    rows: list[PayerFrictionRow] = []
    for payer, group in buckets.items():
        approved = sum(1 for a in group if a.status in _APPROVED_STATES)
        denied = sum(1 for a in group if a.status in _DENIED_STATES)
        pending = sum(1 for a in group if a.status in _PENDING_STATES)
        decided = approved + denied

        turnarounds: list[float] = []
        for a in group:
            if a.submitted_at is None:
                continue
            decided_at = a.approved_at or a.denied_at
            if decided_at is None:
                continue
            turnarounds.append((decided_at - a.submitted_at).total_seconds() / 86400.0)
        avg_turnaround = sum(turnarounds) / len(turnarounds) if turnarounds else None

        reason_counter: Counter[str] = Counter()
        for a in group:
            for reason in reasons_by_auth.get(a.id, []):
                reason_counter[reason] += 1
        top_reasons = [r for r, _ in reason_counter.most_common(3)]

        rows.append(
            PayerFrictionRow(
                payer_name=payer,
                total_auths=len(group),
                approved=approved,
                denied=denied,
                pending=pending,
                approval_rate=(approved / decided) if decided > 0 else 0.0,
                avg_turnaround_days=avg_turnaround,
                top_denial_reasons=top_reasons,
            )
        )
    rows.sort(key=lambda r: r.total_auths, reverse=True)
    return PayerFrictionSummary(rows=rows)
