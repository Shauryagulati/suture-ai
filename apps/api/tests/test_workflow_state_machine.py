"""Phase 3 — Status state machine validation."""
from __future__ import annotations

import pytest

from app.models.discharge_summary import DischargeStatus
from app.models.referral import ReferralStatus
from app.services.workflow.state_machine import (
    DISCHARGE_TRANSITIONS,
    REFERRAL_TRANSITIONS,
    InvalidTransitionError,
    validate_discharge_transition,
    validate_referral_transition,
)

_VALID_REFERRAL_MOVES = [
    (ReferralStatus.new, ReferralStatus.needs_review),
    (ReferralStatus.needs_review, ReferralStatus.missing_info),
    (ReferralStatus.needs_review, ReferralStatus.ready_to_schedule),
    (ReferralStatus.missing_info, ReferralStatus.needs_review),
    (ReferralStatus.missing_info, ReferralStatus.ready_to_schedule),
    (ReferralStatus.ready_to_schedule, ReferralStatus.auth_needed),
    (ReferralStatus.ready_to_schedule, ReferralStatus.scheduled),
    (ReferralStatus.auth_needed, ReferralStatus.ready_to_schedule),
    (ReferralStatus.auth_needed, ReferralStatus.scheduled),
    (ReferralStatus.scheduled, ReferralStatus.completed),
    (ReferralStatus.scheduled, ReferralStatus.at_risk),
    (ReferralStatus.at_risk, ReferralStatus.scheduled),
    (ReferralStatus.at_risk, ReferralStatus.cancelled),
    (ReferralStatus.new, ReferralStatus.cancelled),
    (ReferralStatus.needs_review, ReferralStatus.cancelled),
]


@pytest.mark.parametrize("from_s,to_s", _VALID_REFERRAL_MOVES)
def test_valid_referral_transitions_pass(from_s, to_s):
    validate_referral_transition(from_s, to_s)


@pytest.mark.parametrize(
    "from_s,to_s",
    [
        (ReferralStatus.completed, ReferralStatus.new),
        (ReferralStatus.new, ReferralStatus.scheduled),
        (ReferralStatus.new, ReferralStatus.completed),
        (ReferralStatus.cancelled, ReferralStatus.scheduled),
        (ReferralStatus.completed, ReferralStatus.at_risk),
        (ReferralStatus.scheduled, ReferralStatus.needs_review),
    ],
)
def test_invalid_referral_transitions_raise(from_s, to_s):
    with pytest.raises(InvalidTransitionError):
        validate_referral_transition(from_s, to_s)


def test_referral_no_op_transition_raises():
    with pytest.raises(InvalidTransitionError):
        validate_referral_transition(ReferralStatus.new, ReferralStatus.new)


_VALID_DISCHARGE_MOVES = [
    (DischargeStatus.new, DischargeStatus.patient_contacted),
    (DischargeStatus.patient_contacted, DischargeStatus.scheduled),
    (DischargeStatus.scheduled, DischargeStatus.seen),
    (DischargeStatus.seen, DischargeStatus.confirmation_sent),
    (DischargeStatus.patient_contacted, DischargeStatus.at_risk),
    (DischargeStatus.scheduled, DischargeStatus.at_risk),
    (DischargeStatus.at_risk, DischargeStatus.scheduled),
]


@pytest.mark.parametrize("from_s,to_s", _VALID_DISCHARGE_MOVES)
def test_valid_discharge_transitions_pass(from_s, to_s):
    validate_discharge_transition(from_s, to_s)


@pytest.mark.parametrize(
    "from_s,to_s",
    [
        (DischargeStatus.confirmation_sent, DischargeStatus.new),
        (DischargeStatus.new, DischargeStatus.seen),
        (DischargeStatus.new, DischargeStatus.confirmation_sent),
    ],
)
def test_invalid_discharge_transitions_raise(from_s, to_s):
    with pytest.raises(InvalidTransitionError):
        validate_discharge_transition(from_s, to_s)


def test_transition_tables_export_for_introspection():
    assert isinstance(REFERRAL_TRANSITIONS, dict)
    assert isinstance(DISCHARGE_TRANSITIONS, dict)
    assert ReferralStatus.new in REFERRAL_TRANSITIONS
    assert DischargeStatus.new in DISCHARGE_TRANSITIONS
