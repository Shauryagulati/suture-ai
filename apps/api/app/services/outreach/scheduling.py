"""Scheduling-link URL builder + mock slot availability.

v1 returns deterministic mock slots (next 6 weekday slots across the
next few days). Real provider-availability comes in Module 6 when we
wire actual provider calendars.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config import get_settings


def build_scheduling_link_url(token: str) -> str:
    """Return the patient-facing URL the outreach message links to."""
    base = get_settings().web_base_url.rstrip("/")
    return f"{base}/schedule/{token}"


# Working-hour slots offered each weekday. Local clinic operates 9-5 with
# a midday block; three slots per day is enough for the v1 mock.
_SLOT_HOURS_LOCAL: tuple[int, ...] = (9, 11, 14)


def mock_available_slots(
    *,
    appointment_type: str | None = None,
    count: int = 6,
    now: datetime | None = None,
) -> list[datetime]:
    """Return `count` upcoming weekday slots. UTC timestamps.

    Skips weekends. Starts the day after `now` so we never offer a slot
    that has already passed today. Deterministic given `now` so tests
    can pin behavior.
    """
    _ = appointment_type  # Reserved for future per-type availability.
    if count <= 0:
        return []
    cursor = (now or datetime.now(UTC)) + timedelta(days=1)
    cursor = cursor.replace(hour=0, minute=0, second=0, microsecond=0)
    slots: list[datetime] = []
    while len(slots) < count:
        if cursor.weekday() < 5:
            for hour in _SLOT_HOURS_LOCAL:
                slots.append(cursor.replace(hour=hour))
                if len(slots) == count:
                    break
        cursor += timedelta(days=1)
    return slots
