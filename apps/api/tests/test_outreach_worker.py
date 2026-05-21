"""Celery beat task tests — process_pending_outreach + check_outreach_responses."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.services.outreach.factory import reset_outreach_provider_cache

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_provider_cache_and_eager_celery() -> None:
    reset_outreach_provider_cache()
    from services.workers.app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    reset_outreach_provider_cache()


async def _seed_attempt(
    db: AsyncSession,
    clinic_id: UUID,
    *,
    channel: OutreachChannel = OutreachChannel.sms,
    status: OutreachStatus = OutreachStatus.pending,
    scheduled_at: datetime | None = None,
    sent_at: datetime | None = None,
    scheduling_link_url: str | None = None,
) -> OutreachAttempt:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Pat",
        last_name="Worker",
        dob="1970-01-01",
        phone="412-555-0150",
        email="pat@example.com",
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    db.add(patient)
    await db.flush()
    attempt = OutreachAttempt(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient.id,
        channel=channel,
        status=status,
        scheduled_at=scheduled_at or datetime.now(UTC) - timedelta(minutes=1),
        sent_at=sent_at,
        outcome={},
        attempt_number=1,
        scheduling_link_url=scheduling_link_url
        or ("http://localhost:3000/schedule/fake" if channel == OutreachChannel.sms else None),
    )
    db.add(attempt)
    await db.commit()
    return attempt


async def test_process_pending_outreach_dispatches_due_rows(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    past = datetime.now(UTC) - timedelta(minutes=10)
    future = datetime.now(UTC) + timedelta(hours=2)

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        due_attempt = await _seed_attempt(
            db_session,
            clinic_a_id,
            channel=OutreachChannel.sms,
            scheduled_at=past,
        )
        not_due = await _seed_attempt(
            db_session,
            clinic_a_id,
            channel=OutreachChannel.email,
            scheduled_at=future,
        )

    from services.workers.outreach_tasks import process_pending_outreach

    result = process_pending_outreach.apply().get()
    assert result["sent"] == 1
    assert result["failed"] == 0

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await db_session.refresh(due_attempt)
        await db_session.refresh(not_due)
    assert due_attempt.status == OutreachStatus.sent
    assert due_attempt.sent_at is not None
    assert not_due.status == OutreachStatus.pending  # future row left alone


async def test_process_pending_outreach_clinic_scoped(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, clinic_b_id = two_clinics
    past = datetime.now(UTC) - timedelta(minutes=5)
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        attempt_a = await _seed_attempt(
            db_session, clinic_a_id, channel=OutreachChannel.sms, scheduled_at=past
        )
    with set_clinic_context(clinic_id=clinic_b_id, user_id=test_user):
        attempt_b = await _seed_attempt(
            db_session, clinic_b_id, channel=OutreachChannel.sms, scheduled_at=past
        )

    from services.workers.outreach_tasks import process_pending_outreach

    result = process_pending_outreach.apply().get()
    assert result["sent"] == 2

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await db_session.refresh(attempt_a)
    with set_clinic_context(clinic_id=clinic_b_id, user_id=test_user):
        await db_session.refresh(attempt_b)
    assert attempt_a.status == OutreachStatus.sent
    assert attempt_b.status == OutreachStatus.sent
    assert attempt_a.clinic_id != attempt_b.clinic_id


async def test_process_pending_outreach_skips_already_sent(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    past = datetime.now(UTC) - timedelta(minutes=5)
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        already_sent = await _seed_attempt(
            db_session,
            clinic_a_id,
            channel=OutreachChannel.sms,
            status=OutreachStatus.sent,
            scheduled_at=past,
            sent_at=past,
        )

    from services.workers.outreach_tasks import process_pending_outreach

    result = process_pending_outreach.apply().get()
    assert result["sent"] == 0
    assert result["failed"] == 0

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await db_session.refresh(already_sent)
    assert already_sent.status == OutreachStatus.sent  # unchanged


async def test_check_outreach_responses_flips_stale_sent_to_no_response(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    long_ago = datetime.now(UTC) - timedelta(days=4)
    recent = datetime.now(UTC) - timedelta(hours=2)

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        stale = await _seed_attempt(
            db_session,
            clinic_a_id,
            channel=OutreachChannel.sms,
            status=OutreachStatus.sent,
            scheduled_at=long_ago,
            sent_at=long_ago,
        )
        recent_attempt = await _seed_attempt(
            db_session,
            clinic_a_id,
            channel=OutreachChannel.email,
            status=OutreachStatus.sent,
            scheduled_at=recent,
            sent_at=recent,
        )

    from services.workers.outreach_tasks import check_outreach_responses

    result = check_outreach_responses.apply().get()
    assert result["flipped"] == 1

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await db_session.refresh(stale)
        await db_session.refresh(recent_attempt)
    assert stale.status == OutreachStatus.no_response
    assert recent_attempt.status == OutreachStatus.sent
