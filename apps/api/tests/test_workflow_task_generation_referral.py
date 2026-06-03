"""Phase 4 — apply_referral_transition with idempotent task generation."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.referral import ReferralStatus
from app.models.referral_task import ReferralTask, TaskStatus, TaskType
from app.services.workflow.state_machine import (
    InvalidTransitionError,
    apply_referral_transition,
)


@pytest.mark.asyncio
async def test_transition_to_ready_to_schedule_creates_four_tasks(
    db_session, seeded_referral_a, two_clinics, test_user, set_clinic_context
):
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await apply_referral_transition(
            db_session, referral=seeded_referral_a, target=ReferralStatus.ready_to_schedule
        )
        await db_session.commit()

        tasks = (
            (
                await db_session.execute(
                    select(ReferralTask).where(ReferralTask.referral_id == seeded_referral_a.id)
                )
            )
            .scalars()
            .all()
        )

    assert len(tasks) == 4
    assert {t.task_type for t in tasks} == {
        TaskType.call_patient,
        TaskType.verify_eligibility,
        TaskType.submit_prior_auth,
        TaskType.schedule_appointment,
    }
    assert all(t.clinic_id == clinic_a_id for t in tasks)
    assert all(t.due_at is not None for t in tasks)
    assert all(t.status == TaskStatus.pending for t in tasks)
    assert seeded_referral_a.status == ReferralStatus.ready_to_schedule


@pytest.mark.asyncio
async def test_double_transition_is_idempotent(
    db_session, seeded_referral_a, two_clinics, test_user, set_clinic_context
):
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await apply_referral_transition(
            db_session, referral=seeded_referral_a, target=ReferralStatus.ready_to_schedule
        )
        await db_session.commit()
        # cycle: ready -> auth_needed -> ready again
        await apply_referral_transition(
            db_session, referral=seeded_referral_a, target=ReferralStatus.auth_needed
        )
        await apply_referral_transition(
            db_session, referral=seeded_referral_a, target=ReferralStatus.ready_to_schedule
        )
        await db_session.commit()

        tasks = (
            (
                await db_session.execute(
                    select(ReferralTask).where(ReferralTask.referral_id == seeded_referral_a.id)
                )
            )
            .scalars()
            .all()
        )

    assert len(tasks) == 4


@pytest.mark.asyncio
async def test_invalid_transition_raises_and_writes_nothing(
    db_session, seeded_referral_a, two_clinics, test_user, set_clinic_context
):
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        with pytest.raises(InvalidTransitionError):
            await apply_referral_transition(
                db_session, referral=seeded_referral_a, target=ReferralStatus.completed
            )
        # status unchanged
        assert seeded_referral_a.status == ReferralStatus.needs_review

        tasks = (
            (
                await db_session.execute(
                    select(ReferralTask).where(ReferralTask.referral_id == seeded_referral_a.id)
                )
            )
            .scalars()
            .all()
        )
    assert tasks == []
