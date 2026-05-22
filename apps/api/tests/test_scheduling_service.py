"""Tests for build_scheduling_link_url + mock_available_slots."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.asyncio

from app.services.outreach.scheduling import (  # noqa: E402
    build_scheduling_link_url,
    mock_available_slots,
)


async def test_build_scheduling_link_url_uses_web_base_from_settings() -> None:
    url = build_scheduling_link_url("abc.def.ghi")
    assert url == "http://localhost:3000/schedule/abc.def.ghi"


async def test_build_scheduling_link_url_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "web_base_url", "https://app.example.com/", raising=False)
    assert build_scheduling_link_url("xyz") == "https://app.example.com/schedule/xyz"


async def test_mock_slots_returns_six_by_default() -> None:
    # Pin to a Monday 2026-05-18 UTC noon so we get a deterministic span.
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    slots = mock_available_slots(now=now)
    assert len(slots) == 6


async def test_mock_slots_skips_weekends() -> None:
    # Pin to Friday 2026-05-22 noon — the next 6 slots span Mon/Tue, not Sat/Sun.
    now = datetime(2026, 5, 22, 12, 0, 0, tzinfo=UTC)
    slots = mock_available_slots(now=now)
    for slot in slots:
        assert slot.weekday() < 5, f"weekend slot leaked: {slot}"


async def test_mock_slots_all_after_now() -> None:
    now = datetime(2026, 5, 18, 23, 59, 0, tzinfo=UTC)
    slots = mock_available_slots(now=now)
    assert all(slot > now for slot in slots)


async def test_mock_slots_uses_three_hours_per_day() -> None:
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    slots = mock_available_slots(now=now, count=3)
    # First three slots should all be on the same weekday at 09/11/14.
    assert {s.hour for s in slots} == {9, 11, 14}
    assert {s.date() for s in slots} == {slots[0].date()}


async def test_mock_slots_count_zero_returns_empty() -> None:
    assert mock_available_slots(count=0) == []


async def test_mock_slots_offered_in_chronological_order() -> None:
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    slots = mock_available_slots(now=now, count=9)
    assert slots == sorted(slots)


async def test_mock_slots_appointment_type_currently_ignored() -> None:
    """appointment_type is reserved for future per-type availability — for
    v1 it must not change the mock output."""
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    a = mock_available_slots(appointment_type=None, now=now)
    b = mock_available_slots(appointment_type="echo", now=now)
    assert a == b
