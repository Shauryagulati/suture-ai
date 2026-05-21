"""SLA / business-day math for workflow tasks.

Maps the two urgency enums in the system onto a business-day count, then
adds that many business days to a datetime to produce the task `due_at`.

Holidays are not modelled in v1 — the practice operates US business days
and a holiday-aware calendar belongs in a later module.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.discharge_summary import UrgencyTier
from app.models.document import UrgencyLevel

_DAYS_BY_URGENCY: dict[object, int] = {
    UrgencyTier.critical: 2,
    UrgencyTier.high: 5,
    UrgencyTier.medium: 10,
    UrgencyTier.routine: 20,
    UrgencyLevel.stat: 2,
    UrgencyLevel.urgent: 5,
    UrgencyLevel.routine: 20,
    UrgencyLevel.unclassified: 10,
}


def business_days_for_urgency(urgency: UrgencyTier | UrgencyLevel) -> int:
    if urgency not in _DAYS_BY_URGENCY:
        raise ValueError(f"unknown urgency: {urgency!r}")
    return _DAYS_BY_URGENCY[urgency]


def calculate_due_at(
    urgency: UrgencyTier | UrgencyLevel,
    *,
    now: datetime | None = None,
) -> datetime:
    if now is None:
        now = datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    days_left = business_days_for_urgency(urgency)
    cursor = now
    while days_left > 0:
        cursor = cursor + timedelta(days=1)
        if cursor.weekday() < 5:
            days_left -= 1
    return cursor
