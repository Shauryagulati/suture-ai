"""Status state machine for workflow items.

Two transition tables — REFERRAL_TRANSITIONS and DISCHARGE_TRANSITIONS —
map a current status to the set of statuses it may move to. The
`validate_*` functions raise InvalidTransitionError on illegal moves.

The DB-coupled `apply_*_transition` functions live alongside these in a
later phase; this file only owns validation today.
"""
from __future__ import annotations

from app.models.discharge_summary import DischargeStatus
from app.models.referral import ReferralStatus


class InvalidTransitionError(ValueError):
    """Raised when a status transition is not allowed."""


REFERRAL_TRANSITIONS: dict[ReferralStatus, frozenset[ReferralStatus]] = {
    ReferralStatus.new: frozenset(
        {ReferralStatus.needs_review, ReferralStatus.cancelled}
    ),
    ReferralStatus.needs_review: frozenset(
        {
            ReferralStatus.missing_info,
            ReferralStatus.ready_to_schedule,
            ReferralStatus.cancelled,
        }
    ),
    ReferralStatus.missing_info: frozenset(
        {
            ReferralStatus.needs_review,
            ReferralStatus.ready_to_schedule,
            ReferralStatus.cancelled,
        }
    ),
    ReferralStatus.ready_to_schedule: frozenset(
        {
            ReferralStatus.auth_needed,
            ReferralStatus.scheduled,
            ReferralStatus.cancelled,
        }
    ),
    ReferralStatus.auth_needed: frozenset(
        {
            ReferralStatus.ready_to_schedule,
            ReferralStatus.scheduled,
            ReferralStatus.cancelled,
        }
    ),
    ReferralStatus.scheduled: frozenset(
        {
            ReferralStatus.completed,
            ReferralStatus.at_risk,
            ReferralStatus.cancelled,
        }
    ),
    ReferralStatus.at_risk: frozenset(
        {ReferralStatus.scheduled, ReferralStatus.cancelled}
    ),
    ReferralStatus.completed: frozenset(),
    ReferralStatus.cancelled: frozenset(),
}


DISCHARGE_TRANSITIONS: dict[DischargeStatus, frozenset[DischargeStatus]] = {
    DischargeStatus.new: frozenset(
        {DischargeStatus.patient_contacted, DischargeStatus.at_risk}
    ),
    DischargeStatus.patient_contacted: frozenset(
        {DischargeStatus.scheduled, DischargeStatus.at_risk}
    ),
    DischargeStatus.scheduled: frozenset(
        {DischargeStatus.seen, DischargeStatus.at_risk}
    ),
    DischargeStatus.seen: frozenset({DischargeStatus.confirmation_sent}),
    DischargeStatus.at_risk: frozenset({DischargeStatus.scheduled}),
    DischargeStatus.confirmation_sent: frozenset(),
}


def validate_referral_transition(
    current: ReferralStatus, target: ReferralStatus
) -> None:
    allowed = REFERRAL_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(
            f"ReferralStatus.{current.value} -> {target.value} is not allowed"
        )


def validate_discharge_transition(
    current: DischargeStatus, target: DischargeStatus
) -> None:
    allowed = DISCHARGE_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(
            f"DischargeStatus.{current.value} -> {target.value} is not allowed"
        )
