"""Phase 1 — SLA business-day calculator."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.discharge_summary import UrgencyTier
from app.models.document import UrgencyLevel
from app.services.workflow.sla import (
    business_days_for_urgency,
    calculate_due_at,
)


@pytest.mark.parametrize(
    "urgency, expected_days",
    [
        (UrgencyTier.critical, 2),
        (UrgencyTier.high, 5),
        (UrgencyTier.medium, 10),
        (UrgencyTier.routine, 20),
        (UrgencyLevel.stat, 2),
        (UrgencyLevel.urgent, 5),
        (UrgencyLevel.routine, 20),
        (UrgencyLevel.unclassified, 10),
    ],
)
def test_business_days_for_urgency(urgency, expected_days):
    assert business_days_for_urgency(urgency) == expected_days


def test_calculate_due_at_skips_weekends():
    # 2026-05-22 is a Friday. 2 business days -> Tuesday 2026-05-26.
    friday = datetime(2026, 5, 22, 9, 0, tzinfo=UTC)
    due = calculate_due_at(UrgencyTier.critical, now=friday)
    assert due.weekday() < 5  # not a weekend
    assert due.date().isoformat() == "2026-05-26"


def test_calculate_due_at_handles_monday_start():
    # 2026-05-18 is a Monday. 5 business days -> next Monday 2026-05-25.
    monday = datetime(2026, 5, 18, 9, 0, tzinfo=UTC)
    due = calculate_due_at(UrgencyTier.high, now=monday)
    assert due.date().isoformat() == "2026-05-25"


def test_calculate_due_at_preserves_tz():
    now = datetime(2026, 5, 21, 14, 30, tzinfo=UTC)
    due = calculate_due_at(UrgencyTier.high, now=now)
    assert due.tzinfo is not None


def test_calculate_due_at_rejects_naive_datetime():
    naive = datetime(2026, 5, 21, 14, 30)
    with pytest.raises(ValueError):
        calculate_due_at(UrgencyTier.high, now=naive)


def test_calculate_due_at_defaults_to_now():
    # When now is None, the function uses the current UTC time. We only
    # verify it returns *something* tz-aware in the future.
    due = calculate_due_at(UrgencyLevel.urgent)
    assert due.tzinfo is not None
    assert due > datetime.now(UTC)
