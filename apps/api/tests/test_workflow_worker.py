"""Phase 7 — Celery worker runs process_document_workflow in eager mode."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.referral_task import ReferralTask


@pytest.mark.asyncio
async def test_process_document_workflow_eagerly_runs_transition(
    db_session, seeded_referral_a, two_clinics, test_user, set_clinic_context
):
    from services.workers.app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    from services.workers.tasks import process_document_workflow

    clinic_a_id, _ = two_clinics
    result = process_document_workflow.apply(
        kwargs={
            "referral_id": str(seeded_referral_a.id),
            "clinic_id": str(clinic_a_id),
            "user_id": str(test_user),
            "target_status": "ready_to_schedule",
        }
    ).get()
    assert result["status"] == "ready_to_schedule"

    # The worker opens its own session and commits there; refresh ours.
    with set_clinic_context(clinic_id=clinic_a_id):
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
