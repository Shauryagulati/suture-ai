"""Outreach cadence — when to send SMS, email, voice for a given urgency.

The cadence is a list of (channel, offset_hours) steps. Step 0 fires
immediately; subsequent steps fire at the listed offsets. Critical and
stat urgency tiers compress the cadence into the first day; routine
tiers spread over 48 hours.

`UrgencyTier` (discharge summaries) and `UrgencyLevel` (referrals) are
different enums but the cadence maps both onto the same tempos.
"""

from __future__ import annotations

from app.models.discharge_summary import UrgencyTier
from app.models.document import UrgencyLevel
from app.models.outreach_attempt import OutreachChannel

CadenceStep = tuple[OutreachChannel, int]

_CRITICAL: list[CadenceStep] = [
    (OutreachChannel.sms, 0),
    (OutreachChannel.email, 4),
    (OutreachChannel.voice, 8),
]
_HIGH: list[CadenceStep] = [
    (OutreachChannel.sms, 0),
    (OutreachChannel.email, 12),
    (OutreachChannel.voice, 24),
]
_ROUTINE: list[CadenceStep] = [
    (OutreachChannel.sms, 0),
    (OutreachChannel.email, 24),
    (OutreachChannel.voice, 48),
]

_CADENCE: dict[UrgencyTier | UrgencyLevel, list[CadenceStep]] = {
    UrgencyTier.critical: _CRITICAL,
    UrgencyLevel.stat: _CRITICAL,
    UrgencyTier.high: _HIGH,
    UrgencyLevel.urgent: _HIGH,
    UrgencyTier.medium: _ROUTINE,
    UrgencyTier.routine: _ROUTINE,
    UrgencyLevel.routine: _ROUTINE,
    UrgencyLevel.unclassified: _ROUTINE,
}


def cadence_for_urgency(urgency: UrgencyTier | UrgencyLevel) -> list[CadenceStep]:
    """Return the (channel, offset_hours) sequence for the given urgency.

    Raises ValueError for unknown values so unmapped enum members surface
    immediately rather than silently degrading to the routine cadence.
    """
    if urgency not in _CADENCE:
        raise ValueError(f"unknown urgency: {urgency!r}")
    return list(_CADENCE[urgency])
