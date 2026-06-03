"""Phase 4 — apply_discharge_transition with SLA-driven priorities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.discharge_summary import DischargeStatus
from app.models.referral_task import ReferralTask, TaskPriority, TaskType
from app.services.workflow.state_machine import apply_discharge_transition


@pytest.mark.asyncio
async def test_critical_discharge_yields_critical_priority_and_short_sla(
    db_session, seeded_discharge_a, two_clinics, test_user, set_clinic_context
):
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await apply_discharge_transition(
            db_session, discharge=seeded_discharge_a, target=DischargeStatus.patient_contacted
        )
        await db_session.commit()

        tasks = (
            (
                await db_session.execute(
                    select(ReferralTask).where(
                        ReferralTask.discharge_summary_id == seeded_discharge_a.id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(tasks) == 4
    assert {t.task_type for t in tasks} == {
        TaskType.call_patient,
        TaskType.verify_eligibility,
        TaskType.schedule_appointment,
        TaskType.send_confirmation,
    }
    assert all(t.priority == TaskPriority.critical for t in tasks)
    now = datetime.now(UTC)
    for t in tasks:
        delta = t.due_at - now
        # critical = 2 business days; allow 1..6 calendar days due to weekends
        assert timedelta(days=1) < delta < timedelta(days=6)
