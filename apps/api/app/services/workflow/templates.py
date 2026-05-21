"""Static task templates per workflow-item type.

Pure functions — no DB writes. The state-machine layer is responsible for
persisting `ReferralTask` rows from these specs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models.discharge_summary import UrgencyTier
from app.models.document import UrgencyLevel
from app.models.referral_task import TaskPriority, TaskType


@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_type: TaskType
    title: str
    description: str
    priority: TaskPriority


class _HasUrgencyLevel(Protocol):
    urgency: UrgencyLevel


class _HasUrgencyTier(Protocol):
    urgency_tier: UrgencyTier


_REFERRAL_PRIORITY_MAP: dict[UrgencyLevel, TaskPriority] = {
    UrgencyLevel.stat: TaskPriority.critical,
    UrgencyLevel.urgent: TaskPriority.high,
    UrgencyLevel.routine: TaskPriority.medium,
    UrgencyLevel.unclassified: TaskPriority.medium,
}

_DISCHARGE_PRIORITY_MAP: dict[UrgencyTier, TaskPriority] = {
    UrgencyTier.critical: TaskPriority.critical,
    UrgencyTier.high: TaskPriority.high,
    UrgencyTier.medium: TaskPriority.medium,
    UrgencyTier.routine: TaskPriority.low,
}


def referral_task_specs(referral: _HasUrgencyLevel) -> list[TaskSpec]:
    priority = _REFERRAL_PRIORITY_MAP[referral.urgency]
    return [
        TaskSpec(
            task_type=TaskType.call_patient,
            title="Call patient to confirm contact info",
            description="Confirm phone, address, preferred contact channel, and best callback window.",
            priority=priority,
        ),
        TaskSpec(
            task_type=TaskType.verify_eligibility,
            title="Verify insurance eligibility",
            description="Run eligibility check against the payer for the referral's procedure codes.",
            priority=priority,
        ),
        TaskSpec(
            task_type=TaskType.submit_prior_auth,
            title="Check if prior auth is needed",
            description="Compare procedure codes against payer rules. Submit a PA packet if required.",
            priority=priority,
        ),
        TaskSpec(
            task_type=TaskType.schedule_appointment,
            title="Schedule appointment",
            description="Coordinate with the assigned cardiologist's calendar and book the visit.",
            priority=priority,
        ),
    ]


def discharge_task_specs(discharge: _HasUrgencyTier) -> list[TaskSpec]:
    priority = _DISCHARGE_PRIORITY_MAP[discharge.urgency_tier]
    return [
        TaskSpec(
            task_type=TaskType.call_patient,
            title="Contact patient for follow-up scheduling",
            description="Reach out per cadence rules; SMS first, voice fallback.",
            priority=priority,
        ),
        TaskSpec(
            task_type=TaskType.verify_eligibility,
            title="Verify insurance eligibility",
            description="Confirm coverage for the recommended follow-up visit.",
            priority=priority,
        ),
        TaskSpec(
            task_type=TaskType.schedule_appointment,
            title="Schedule follow-up appointment",
            description="Book within the SLA window from the discharge_date.",
            priority=priority,
        ),
        TaskSpec(
            task_type=TaskType.send_confirmation,
            title="Send confirmation fax to discharging hospital",
            description="Generate a one-page PDF confirming receipt + scheduled appointment.",
            priority=priority,
        ),
    ]
