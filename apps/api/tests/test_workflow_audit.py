"""Phase 0 — ReferralTask must be in AUDITED_MODELS and emit audit rows."""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditAction, AuditLog
from app.models.clinic_membership import ClinicMembership, MembershipRole
from app.models.patient import Patient
from app.models.referral_task import ReferralTask, TaskPriority, TaskStatus, TaskType
from app.utils.audit import AUDITED_MODELS, register_audited_models


def test_referral_task_is_audited():
    register_audited_models()  # ensure list is built
    assert ReferralTask in AUDITED_MODELS


@pytest.mark.asyncio
async def test_referral_task_insert_emits_audit_row(
    db_session, two_clinics, test_user, set_clinic_context
):
    register_audited_models()
    clinic_a_id, _ = two_clinics

    # Bind the user to the clinic (so audit context is coherent), then
    # set ContextVars and insert a Patient + ReferralTask inside that scope.
    db_session.add(
        ClinicMembership(
            user_id=test_user,
            clinic_id=clinic_a_id,
            role=MembershipRole.admin,
            is_default=True,
        )
    )
    await db_session.commit()

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient = Patient(
            clinic_id=clinic_a_id,
            mrn=f"MRN-{uuid4().hex[:6]}",
            first_name="Jane",
            last_name="Doe",
            dob="1990-01-15",
            phone="412-555-0100",
        )
        db_session.add(patient)
        await db_session.commit()
        await db_session.refresh(patient)

        task = ReferralTask(
            clinic_id=clinic_a_id,
            patient_id=patient.id,
            task_type=TaskType.call_patient,
            title="audit-probe",
            status=TaskStatus.pending,
            priority=TaskPriority.medium,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        rows = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.resource_type == "referral_tasks",
                    AuditLog.resource_id == task.id,
                    AuditLog.action == AuditAction.create,
                )
            )
        ).scalars().all()

        assert len(rows) == 1
        # Audit row must NOT carry the task title or other PHI-adjacent values.
        details = rows[0].details or {}
        body_str = repr(details)
        assert "audit-probe" not in body_str  # title is not in details
