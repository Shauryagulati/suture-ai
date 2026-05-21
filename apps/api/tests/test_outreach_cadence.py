"""Cadence config tests — per-urgency tempo + bad-input handling."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

from app.models.discharge_summary import UrgencyTier  # noqa: E402
from app.models.document import UrgencyLevel  # noqa: E402
from app.models.outreach_attempt import OutreachChannel  # noqa: E402
from app.services.outreach.cadence import cadence_for_urgency  # noqa: E402


async def test_cadence_critical_compresses_into_first_day() -> None:
    steps = cadence_for_urgency(UrgencyTier.critical)
    assert steps == [
        (OutreachChannel.sms, 0),
        (OutreachChannel.email, 4),
        (OutreachChannel.voice, 8),
    ]


async def test_cadence_stat_matches_critical() -> None:
    assert cadence_for_urgency(UrgencyLevel.stat) == cadence_for_urgency(UrgencyTier.critical)


async def test_cadence_high_uses_twelve_then_twentyfour() -> None:
    steps = cadence_for_urgency(UrgencyTier.high)
    assert steps == [
        (OutreachChannel.sms, 0),
        (OutreachChannel.email, 12),
        (OutreachChannel.voice, 24),
    ]


async def test_cadence_urgent_matches_high() -> None:
    assert cadence_for_urgency(UrgencyLevel.urgent) == cadence_for_urgency(UrgencyTier.high)


async def test_cadence_routine_spreads_over_two_days() -> None:
    steps = cadence_for_urgency(UrgencyLevel.routine)
    assert steps == [
        (OutreachChannel.sms, 0),
        (OutreachChannel.email, 24),
        (OutreachChannel.voice, 48),
    ]


async def test_cadence_unclassified_uses_routine_tempo() -> None:
    assert cadence_for_urgency(UrgencyLevel.unclassified) == cadence_for_urgency(
        UrgencyLevel.routine
    )


async def test_cadence_medium_tier_uses_routine_tempo() -> None:
    assert cadence_for_urgency(UrgencyTier.medium) == cadence_for_urgency(UrgencyTier.routine)


async def test_cadence_returns_fresh_list_each_call() -> None:
    first = cadence_for_urgency(UrgencyTier.critical)
    first.clear()
    second = cadence_for_urgency(UrgencyTier.critical)
    assert len(second) == 3  # mutation of first must not affect future calls


async def test_cadence_unknown_value_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown urgency"):
        cadence_for_urgency("garbage")  # type: ignore[arg-type]


async def test_cadence_all_steps_start_with_sms_at_zero() -> None:
    for urgency in (
        UrgencyTier.critical,
        UrgencyTier.high,
        UrgencyTier.medium,
        UrgencyTier.routine,
        UrgencyLevel.stat,
        UrgencyLevel.urgent,
        UrgencyLevel.routine,
        UrgencyLevel.unclassified,
    ):
        first_channel, first_offset = cadence_for_urgency(urgency)[0]
        assert first_channel == OutreachChannel.sms
        assert first_offset == 0


async def test_cadence_steps_are_monotonically_increasing() -> None:
    for urgency in (
        UrgencyTier.critical,
        UrgencyTier.high,
        UrgencyTier.routine,
    ):
        offsets = [offset for _, offset in cadence_for_urgency(urgency)]
        assert offsets == sorted(offsets), f"{urgency} offsets not monotonic: {offsets}"
