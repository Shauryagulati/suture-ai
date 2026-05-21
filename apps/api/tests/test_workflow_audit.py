"""Phase 0 — ReferralTask must be in AUDITED_MODELS and emit audit rows."""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditAction, AuditLog
from app.models.patient import Patient
from app.models.referral_task import ReferralTask, TaskPriority, TaskStatus, TaskType
from app.utils.audit import AUDITED_MODELS


def test_referral_task_is_audited():
    assert ReferralTask in AUDITED_MODELS


@pytest.mark.asyncio
async def test_referral_task_insert_emits_audit_row(
    db_session, two_clinics, test_user, set_clinic_context
):
    clinic_a_id, _ = two_clinics
    patient_id = uuid4()
    task_id = uuid4()
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        db_session.add_all(
            [
                Patient(
                    id=patient_id,
                    clinic_id=clinic_a_id,
                    mrn=f"MRN-{uuid4().hex[:6]}",
                    first_name="Jane",
                    last_name="Doe",
                    dob="1990-01-15",
                    phone="412-555-0100",
                ),
                ReferralTask(
                    id=task_id,
                    clinic_id=clinic_a_id,
                    patient_id=patient_id,
                    task_type=TaskType.call_patient,
                    title="audit-probe",
                    status=TaskStatus.pending,
                    priority=TaskPriority.medium,
                ),
            ]
        )
        await db_session.commit()
        rows = (
            (
                await db_session.execute(
                    select(AuditLog).where(
                        AuditLog.resource_type == "referral_tasks",
                        AuditLog.resource_id == task_id,
                        AuditLog.action == AuditAction.create,
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    # Audit details carry column names + IDs, never PHI-adjacent values.
    details = rows[0].details or {}
    assert "audit-probe" not in repr(details)
