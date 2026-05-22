"""Pydantic response models for /api/analytics/*."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _Cfg(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─── Leakage ───────────────────────────────────────────────────────────


class LeakageRow(_Cfg):
    patient_id: UUID
    patient_name: str
    score: int
    days_since_referral: int | None
    failed_outreach_count: int
    has_phone: bool
    has_email: bool
    urgency: str
    prior_auth_denied: bool
    referral_id: UUID | None
    discharge_summary_id: UUID | None


class LeakageSummary(_Cfg):
    at_risk_count: int
    threshold: int
    rows: list[LeakageRow]


# ─── Payer friction ────────────────────────────────────────────────────


class PayerFrictionRow(_Cfg):
    payer_name: str
    total_auths: int
    approved: int
    denied: int
    pending: int
    approval_rate: float
    avg_turnaround_days: float | None
    top_denial_reasons: list[str]


class PayerFrictionSummary(_Cfg):
    rows: list[PayerFrictionRow]


# ─── Referral source quality ───────────────────────────────────────────


class ReferralQualityRow(_Cfg):
    provider_id: UUID
    provider_name: str
    practice_name: str | None
    referral_volume: int
    avg_missing_fields: float
    completeness_pct: float
    top_missing_fields: list[str]


class ReferralQualitySummary(_Cfg):
    rows: list[ReferralQualityRow]


# ─── ROI ───────────────────────────────────────────────────────────────


class RoiReport(_Cfg):
    from_date: date
    to_date: date
    documents_processed: int
    hours_saved: float
    referrals_at_risk: int
    projected_revenue_recovered_cents: int
    prior_auth_approval_rate: float | None
    avg_days_referral_to_appointment: float | None


# ─── Dashboard composite ───────────────────────────────────────────────


class DashboardPayload(_Cfg):
    leakage: LeakageSummary
    payer_friction: PayerFrictionSummary
    referral_quality: ReferralQualitySummary
    roi: RoiReport
