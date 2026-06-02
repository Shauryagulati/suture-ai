"""Phase 2 — Referral and discharge task templates."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from app.models.discharge_summary import UrgencyTier
from app.models.document import UrgencyLevel
from app.models.referral_task import TaskPriority, TaskType
from app.services.workflow.templates import (
    TaskSpec,
    discharge_task_specs,
    referral_task_specs,
)


def _stub_referral(urgency=UrgencyLevel.urgent):
    class _R:
        id = uuid4()
        patient_id = uuid4()
        clinic_id = uuid4()

    r = _R()
    r.urgency = urgency
    return r


def _stub_discharge(urgency=UrgencyTier.high):
    class _D:
        id = uuid4()
        patient_id = uuid4()
        clinic_id = uuid4()

    d = _D()
    d.urgency_tier = urgency
    return d


def test_referral_yields_four_task_specs():
    specs = referral_task_specs(_stub_referral())
    assert len(specs) == 4
    types = [s.task_type for s in specs]
    assert types == [
        TaskType.call_patient,
        TaskType.verify_eligibility,
        TaskType.submit_prior_auth,
        TaskType.schedule_appointment,
    ]


def test_referral_prior_auth_task_has_explicit_title():
    specs = referral_task_specs(_stub_referral())
    auth_spec = next(s for s in specs if s.task_type == TaskType.submit_prior_auth)
    assert "prior auth" in auth_spec.title.lower()


def test_discharge_yields_four_task_specs():
    specs = discharge_task_specs(_stub_discharge())
    assert len(specs) == 4
    types = [s.task_type for s in specs]
    assert types == [
        TaskType.call_patient,
        TaskType.verify_eligibility,
        TaskType.schedule_appointment,
        TaskType.send_confirmation,
    ]


def test_discharge_critical_urgency_yields_critical_priority():
    specs = discharge_task_specs(_stub_discharge(urgency=UrgencyTier.critical))
    assert all(s.priority == TaskPriority.critical for s in specs)


def test_referral_stat_urgency_yields_critical_priority():
    specs = referral_task_specs(_stub_referral(urgency=UrgencyLevel.stat))
    assert all(s.priority == TaskPriority.critical for s in specs)


def test_referral_routine_urgency_yields_medium_priority():
    specs = referral_task_specs(_stub_referral(urgency=UrgencyLevel.routine))
    assert all(s.priority == TaskPriority.medium for s in specs)


def test_task_spec_is_immutable():
    spec = TaskSpec(
        task_type=TaskType.call_patient,
        title="x",
        description="y",
        priority=TaskPriority.medium,
    )
    with pytest.raises(FrozenInstanceError):
        spec.title = "z"  # frozen dataclass
