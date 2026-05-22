"""send_email service tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import UrgencyLevel
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.services.outreach.email import send_email
from app.services.outreach.factory import (
    get_outreach_provider,
    reset_outreach_provider_cache,
)
from app.services.outreach.stub import StubOutreachProvider

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_provider_cache() -> None:
    reset_outreach_provider_cache()
    yield
    reset_outreach_provider_cache()


async def _seed_patient_and_pending_email(
    db: AsyncSession,
    clinic_id: UUID,
    *,
    email: str | None = "pat@example.com",
) -> tuple[Patient, OutreachAttempt]:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Pat",
        last_name="Email",
        dob="1970-01-01",
        phone="412-555-0150",
        email=email,
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    attempt = OutreachAttempt(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient.id,
        channel=OutreachChannel.email,
        status=OutreachStatus.pending,
        scheduled_at=datetime.now(UTC),
        outcome={},
        attempt_number=1,
    )
    db.add(patient)
    await db.flush()
    db.add(attempt)
    await db.commit()
    return patient, attempt


async def test_send_email_marks_attempt_sent(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, attempt = await _seed_patient_and_pending_email(db_session, clinic_a_id)
        result = await send_email(
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.routine,
            scheduling_link_url="https://app/schedule/xyz",
            clinic_name="Steel City Cardiology",
        )
        await db_session.commit()

    assert result.delivered is True
    assert attempt.status == OutreachStatus.sent
    assert attempt.outcome["delivered"] is True


async def test_send_email_uses_plaintext_email(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, attempt = await _seed_patient_and_pending_email(
            db_session, clinic_a_id, email="pat@example.com"
        )
        await send_email(
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.routine,
            scheduling_link_url="https://app/schedule/xyz",
            clinic_name="Steel City Cardiology",
        )

    provider = get_outreach_provider()
    assert isinstance(provider, StubOutreachProvider)
    assert provider.sent[0].to == "pat@example.com"
    assert provider.sent[0].subject is not None
    assert "Steel City Cardiology" in provider.sent[0].subject
    assert "https://app/schedule/xyz" in provider.sent[0].body


async def test_send_email_no_email_on_file_skips_provider_and_marks_failed(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, attempt = await _seed_patient_and_pending_email(
            db_session, clinic_a_id, email=None
        )
        result = await send_email(
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.routine,
            scheduling_link_url="https://app/schedule/xyz",
            clinic_name="Steel City Cardiology",
        )
        await db_session.commit()

    assert result.delivered is False
    assert result.error == "no email on file"
    assert attempt.status == OutreachStatus.failed
    assert attempt.outcome["error"] == "no email on file"

    provider = get_outreach_provider()
    assert isinstance(provider, StubOutreachProvider)
    assert provider.sent == []  # provider never called


async def test_send_email_rejects_non_email_attempt() -> None:
    attempt = OutreachAttempt(
        patient_id=uuid4(),
        channel=OutreachChannel.sms,
        status=OutreachStatus.pending,
        scheduled_at=datetime.now(UTC),
        outcome={},
    )
    patient = Patient(
        first_name="Pat", last_name="X", dob="1970-01-01", phone="412-555-0000"
    )
    with pytest.raises(ValueError, match="channel=email"):
        await send_email(
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.routine,
            scheduling_link_url="https://x",
            clinic_name="Anywhere",
        )
