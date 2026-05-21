"""Per-patient leakage risk scoring.

Score components (0-100, weighted sum, then clamped):
 +30 if no appointment scheduled and the referral/discharge is still open
 +20 if days since referral/discharge >= 7 with no appointment
 +20 if days since referral/discharge >= 14 with no appointment (additive)
 +10 per failed outreach attempt, capped at 30
 +10 if missing phone (empty string or None)
 +10 if missing email
 +20 if urgency is stat / critical
 +10 if urgency is urgent / high
 +10 if any prior_auth for this patient is currently denied
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    AppointmentStatus,
    DischargeStatus,
    DischargeSummary,
    OutreachAttempt,
    OutreachStatus,
    Patient,
    PriorAuth,
    PriorAuthStatus,
    Referral,
    ReferralStatus,
    UrgencyLevel,
    UrgencyTier,
)
from app.schemas.analytics import LeakageRow, LeakageSummary

LEAKAGE_THRESHOLD = 70

_REFERRAL_OPEN_STATUSES = {
    ReferralStatus.new,
    ReferralStatus.needs_review,
    ReferralStatus.missing_info,
    ReferralStatus.ready_to_schedule,
    ReferralStatus.auth_needed,
    ReferralStatus.at_risk,
}
_DISCHARGE_OPEN_STATUSES = {
    DischargeStatus.new,
    DischargeStatus.patient_contacted,
    DischargeStatus.at_risk,
}
_HIGH_URGENCY = {UrgencyLevel.stat, UrgencyTier.critical}
_MED_URGENCY = {UrgencyLevel.urgent, UrgencyTier.high}


async def compute_leakage_summary(db: AsyncSession) -> LeakageSummary:
    referrals = (
        (
            await db.execute(
                select(Referral).where(Referral.status.in_(_REFERRAL_OPEN_STATUSES))
            )
        )
        .scalars()
        .all()
    )
    discharges = (
        (
            await db.execute(
                select(DischargeSummary).where(
                    DischargeSummary.status.in_(_DISCHARGE_OPEN_STATUSES)
                )
            )
        )
        .scalars()
        .all()
    )

    patient_ids: set[UUID] = {r.patient_id for r in referrals} | {
        d.patient_id for d in discharges
    }
    if not patient_ids:
        return LeakageSummary(at_risk_count=0, threshold=LEAKAGE_THRESHOLD, rows=[])

    patients = (
        (await db.execute(select(Patient).where(Patient.id.in_(patient_ids))))
        .scalars()
        .all()
    )
    by_id = {p.id: p for p in patients}

    failed = (
        (
            await db.execute(
                select(OutreachAttempt).where(
                    OutreachAttempt.patient_id.in_(patient_ids),
                    OutreachAttempt.status.in_(
                        {OutreachStatus.failed, OutreachStatus.no_response}
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    failed_count: dict[UUID, int] = {}
    for o in failed:
        failed_count[o.patient_id] = failed_count.get(o.patient_id, 0) + 1

    scheduled_appts = (
        (
            await db.execute(
                select(Appointment.patient_id).where(
                    Appointment.patient_id.in_(patient_ids),
                    Appointment.status.in_(
                        {AppointmentStatus.scheduled, AppointmentStatus.confirmed}
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    has_appt: set[UUID] = set(scheduled_appts)

    denied_auths = (
        (
            await db.execute(
                select(PriorAuth.patient_id).where(
                    PriorAuth.patient_id.in_(patient_ids),
                    PriorAuth.status.in_(
                        {PriorAuthStatus.denied, PriorAuthStatus.appeal_denied}
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    has_denied: set[UUID] = set(denied_auths)

    referrals_by_patient: dict[UUID, Referral] = {}
    for r in referrals:
        prev = referrals_by_patient.get(r.patient_id)
        if prev is None or r.created_at > prev.created_at:
            referrals_by_patient[r.patient_id] = r
    discharges_by_patient: dict[UUID, DischargeSummary] = {}
    for d in discharges:
        prev = discharges_by_patient.get(d.patient_id)
        if prev is None or d.created_at > prev.created_at:
            discharges_by_patient[d.patient_id] = d

    now = datetime.now(UTC)
    rows: list[LeakageRow] = []
    for pid in patient_ids:
        p = by_id.get(pid)
        if p is None:
            continue
        ref = referrals_by_patient.get(pid)
        disch = discharges_by_patient.get(pid)
        urgency_label, urgency_score = _urgency_signal(ref, disch)
        days = _days_since(ref, disch, now)

        score = 0
        if pid not in has_appt:
            score += 30
            if days is not None and days >= 7:
                score += 20
            if days is not None and days >= 14:
                score += 20
        score += min(failed_count.get(pid, 0) * 10, 30)
        if not p.phone:
            score += 10
        if not p.email:
            score += 10
        score += urgency_score
        if pid in has_denied:
            score += 10
        score = min(score, 100)

        rows.append(
            LeakageRow(
                patient_id=p.id,
                patient_name=f"{p.first_name} {p.last_name}".strip(),
                score=score,
                days_since_referral=days,
                failed_outreach_count=failed_count.get(pid, 0),
                has_phone=bool(p.phone),
                has_email=bool(p.email),
                urgency=urgency_label,
                prior_auth_denied=pid in has_denied,
                referral_id=ref.id if ref else None,
                discharge_summary_id=disch.id if disch else None,
            )
        )

    rows.sort(key=lambda r: r.score, reverse=True)
    at_risk = sum(1 for r in rows if r.score >= LEAKAGE_THRESHOLD)
    return LeakageSummary(at_risk_count=at_risk, threshold=LEAKAGE_THRESHOLD, rows=rows)


def _urgency_signal(
    ref: Referral | None, disch: DischargeSummary | None
) -> tuple[str, int]:
    candidates: list[tuple[str, int]] = []
    if ref is not None:
        if ref.urgency in _HIGH_URGENCY:
            candidates.append((ref.urgency.value, 20))
        elif ref.urgency in _MED_URGENCY:
            candidates.append((ref.urgency.value, 10))
        else:
            candidates.append((ref.urgency.value, 0))
    if disch is not None:
        if disch.urgency_tier in _HIGH_URGENCY:
            candidates.append((disch.urgency_tier.value, 20))
        elif disch.urgency_tier in _MED_URGENCY:
            candidates.append((disch.urgency_tier.value, 10))
        else:
            candidates.append((disch.urgency_tier.value, 0))
    if not candidates:
        return ("unclassified", 0)
    return max(candidates, key=lambda c: c[1])


def _days_since(
    ref: Referral | None, disch: DischargeSummary | None, now: datetime
) -> int | None:
    instants: list[datetime] = []
    if ref is not None:
        instants.append(ref.created_at)
    if disch is not None:
        instants.append(disch.created_at)
    if not instants:
        return None
    earliest = min(instants)
    return max(0, (now - earliest).days)
