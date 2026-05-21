"""Phase 5 — tasks REST endpoints + tenant isolation."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.patient import Patient
from app.models.referral_task import ReferralTask, TaskPriority, TaskStatus, TaskType


async def _insert_task(db_session, clinic_id, *, title="t", status=TaskStatus.pending,
                       priority=TaskPriority.medium):
    patient_id = uuid4()
    task_id = uuid4()
    db_session.add_all([
        Patient(
            id=patient_id, clinic_id=clinic_id,
            mrn=f"MRN-{uuid4().hex[:6]}",
            first_name="X", last_name="Y",
            dob="1980-01-01", phone="412-555-0000",
        ),
        ReferralTask(
            id=task_id, clinic_id=clinic_id, patient_id=patient_id,
            task_type=TaskType.call_patient, title=title,
            status=status, priority=priority,
        ),
    ])
    await db_session.commit()
    return task_id


@pytest.mark.asyncio
async def test_list_tasks_returns_only_current_clinic(
    authed_client_factory, db_session, two_clinics, set_clinic_context
):
    clinic_a_id, clinic_b_id = two_clinics
    client_a, headers_a, _ = await authed_client_factory("a")

    with set_clinic_context(clinic_id=clinic_a_id):
        await _insert_task(db_session, clinic_a_id, title="A-task")
    with set_clinic_context(clinic_id=clinic_b_id):
        await _insert_task(db_session, clinic_b_id, title="B-task")

    resp = await client_a.get("/api/tasks/", headers=headers_a)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [t["title"] for t in body["items"]] == ["A-task"]
    assert body["total"] == 1


@pytest.mark.asyncio
async def test_list_tasks_filters_by_status(
    authed_client_factory, db_session, two_clinics, set_clinic_context
):
    clinic_a_id, _ = two_clinics
    client_a, headers_a, _ = await authed_client_factory("a")
    with set_clinic_context(clinic_id=clinic_a_id):
        await _insert_task(db_session, clinic_a_id, title="pending-one", status=TaskStatus.pending)
        await _insert_task(db_session, clinic_a_id, title="done-one", status=TaskStatus.completed)

    resp = await client_a.get("/api/tasks/?status=pending", headers=headers_a)
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()["items"]]
    assert "pending-one" in titles and "done-one" not in titles


@pytest.mark.asyncio
async def test_patch_task_updates_status_and_stamps_completion(
    authed_client_factory, db_session, two_clinics, set_clinic_context
):
    clinic_a_id, _ = two_clinics
    client_a, headers_a, user_id = await authed_client_factory("a")
    with set_clinic_context(clinic_id=clinic_a_id):
        task_id = await _insert_task(db_session, clinic_a_id, title="patch-me")

    resp = await client_a.patch(
        f"/api/tasks/{task_id}", headers=headers_a,
        json={"status": "completed"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["completed_at"] is not None
    assert body["completed_by"] == str(user_id)


@pytest.mark.asyncio
async def test_get_task_other_clinic_returns_404(
    authed_client_factory, db_session, two_clinics, set_clinic_context
):
    _clinic_a_id, clinic_b_id = two_clinics
    client_a, headers_a, _ = await authed_client_factory("a")
    with set_clinic_context(clinic_id=clinic_b_id):
        b_task_id = await _insert_task(db_session, clinic_b_id, title="hidden")

    resp = await client_a.get(f"/api/tasks/{b_task_id}", headers=headers_a)
    assert resp.status_code == 404
