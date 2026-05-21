"""Phase 8 — check_overdue_tasks flips past-due tasks and escalates parents."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.document import UrgencyLevel
from app.models.patient import Patient
from app.models.referral import Referral, ReferralStatus
from app.models.referral_task import (
    ReferralTask,
    TaskPriority,
    TaskStatus,
    TaskType,
)


@pytest.mark.asyncio
async def test_check_overdue_flags_referral_task_and_escalates_to_at_risk(
    db_session, two_clinics, test_user, set_clinic_context
):
    clinic_a_id, _ = two_clinics
    patient_id = uuid4()
    referral_id = uuid4()
    past_due = datetime.now(UTC) - timedelta(days=3)

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        db_session.add_all([
            Patient(
                id=patient_id, clinic_id=clinic_a_id,
                mrn=f"MRN-{uuid4().hex[:6]}",
                first_name="A", last_name="B",
                dob="1970-01-01", phone="412-555-0000",
            ),
            Referral(
                id=referral_id, clinic_id=clinic_a_id, patient_id=patient_id,
                status=ReferralStatus.scheduled,
                urgency=UrgencyLevel.urgent,
                diagnosis_codes=[], procedure_codes=[],
            ),
            ReferralTask(
                clinic_id=clinic_a_id, patient_id=patient_id,
                referral_id=referral_id,
                task_type=TaskType.call_patient, title="late",
                status=TaskStatus.pending, priority=TaskPriority.high,
                due_at=past_due,
            ),
        ])
        await db_session.commit()

    from services.workers.app import celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    from services.workers.tasks import check_overdue_tasks

    result = check_overdue_tasks.apply().get()
    assert result["flipped"] >= 1

    with set_clinic_context(clinic_id=clinic_a_id):
        task = (
            await db_session.execute(
                select(ReferralTask).where(ReferralTask.referral_id == referral_id)
            )
        ).scalar_one()
        assert task.status == TaskStatus.overdue

        ref = (
            await db_session.execute(select(Referral).where(Referral.id == referral_id))
        ).scalar_one()
        assert ref.status == ReferralStatus.at_risk


@pytest.mark.asyncio
async def test_check_overdue_skips_tasks_not_past_due(
    db_session, two_clinics, test_user, set_clinic_context
):
    clinic_a_id, _ = two_clinics
    patient_id = uuid4()
    referral_id = uuid4()
    future_due = datetime.now(UTC) + timedelta(days=5)

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        db_session.add_all([
            Patient(
                id=patient_id, clinic_id=clinic_a_id,
                mrn=f"MRN-{uuid4().hex[:6]}",
                first_name="A", last_name="B",
                dob="1970-01-01", phone="412-555-0000",
            ),
            Referral(
                id=referral_id, clinic_id=clinic_a_id, patient_id=patient_id,
                status=ReferralStatus.scheduled,
                urgency=UrgencyLevel.urgent,
                diagnosis_codes=[], procedure_codes=[],
            ),
            ReferralTask(
                clinic_id=clinic_a_id, patient_id=patient_id,
                referral_id=referral_id,
                task_type=TaskType.call_patient, title="not late",
                status=TaskStatus.pending, priority=TaskPriority.medium,
                due_at=future_due,
            ),
        ])
        await db_session.commit()

    from services.workers.app import celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    from services.workers.tasks import check_overdue_tasks

    check_overdue_tasks.apply().get()

    with set_clinic_context(clinic_id=clinic_a_id):
        task = (
            await db_session.execute(
                select(ReferralTask).where(ReferralTask.referral_id == referral_id)
            )
        ).scalar_one()
        assert task.status == TaskStatus.pending
        ref = (
            await db_session.execute(select(Referral).where(Referral.id == referral_id))
        ).scalar_one()
        assert ref.status == ReferralStatus.scheduled
