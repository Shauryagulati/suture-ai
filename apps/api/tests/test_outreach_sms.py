"""send_sms service tests — provider invocation + attempt mutation."""

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
from app.services.outreach.base import OutreachMessage, OutreachResult
from app.services.outreach.factory import reset_outreach_provider_cache
from app.services.outreach.sms import send_sms
from app.services.outreach.stub import StubOutreachProvider

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_provider_cache() -> None:
    reset_outreach_provider_cache()
    yield
    reset_outreach_provider_cache()


async def _seed_patient_and_pending_sms(
    db: AsyncSession, clinic_id: UUID, *, phone: str = "412-555-0150"
) -> tuple[Patient, OutreachAttempt]:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Pat",
        last_name="Sms",
        dob="1970-01-01",
        phone=phone,
        email="pat@example.com",
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    attempt = OutreachAttempt(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient.id,
        channel=OutreachChannel.sms,
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


async def test_send_sms_marks_attempt_sent_and_records_outcome(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, attempt = await _seed_patient_and_pending_sms(db_session, clinic_a_id)

        result = await send_sms(
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.routine,
            scheduling_link_url="https://app/schedule/xyz",
        )
        await db_session.commit()

    assert result.delivered is True
    assert result.provider_message_id is not None
    assert attempt.status == OutreachStatus.sent
    assert attempt.sent_at is not None
    assert attempt.outcome["delivered"] is True
    assert attempt.outcome["provider_message_id"] == result.provider_message_id
    assert attempt.outcome["error"] is None


async def test_send_sms_uses_decrypted_phone(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    """The provider must receive the plaintext phone, not the Fernet
    ciphertext — the ORM TypeDecorator handles decryption on read."""
    from app.services.outreach.factory import get_outreach_provider

    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, attempt = await _seed_patient_and_pending_sms(
            db_session, clinic_a_id, phone="412-555-0150"
        )
        await send_sms(
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.routine,
            scheduling_link_url="https://app/schedule/xyz",
        )

    provider = get_outreach_provider()
    assert isinstance(provider, StubOutreachProvider)
    assert len(provider.sent) == 1
    assert provider.sent[0].to == "412-555-0150"
    assert provider.sent[0].channel == OutreachChannel.sms
    assert "https://app/schedule/xyz" in provider.sent[0].body


async def test_send_sms_rejects_non_sms_attempt() -> None:
    attempt = OutreachAttempt(
        patient_id=uuid4(),
        channel=OutreachChannel.email,
        status=OutreachStatus.pending,
        scheduled_at=datetime.now(UTC),
        outcome={},
    )
    patient = Patient(
        first_name="Pat",
        last_name="X",
        dob="1970-01-01",
        phone="412-555-0000",
    )
    with pytest.raises(ValueError, match="channel=sms"):
        await send_sms(
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.routine,
            scheduling_link_url="https://x",
        )


async def test_send_sms_failed_delivery_marks_attempt_failed(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Install a provider that fails, verify attempt.status flips to failed."""
    clinic_a_id, _ = two_clinics

    class FailingProvider(StubOutreachProvider):
        async def send(self, message: OutreachMessage) -> OutreachResult:
            self.sent.append(message)
            return OutreachResult(delivered=False, error="carrier rejected")

    from app.services.outreach import sms as sms_module

    monkeypatch.setattr(sms_module, "get_outreach_provider", lambda: FailingProvider())

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, attempt = await _seed_patient_and_pending_sms(db_session, clinic_a_id)
        result = await send_sms(
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.routine,
            scheduling_link_url="https://app/schedule/xyz",
        )
        await db_session.commit()

    assert result.delivered is False
    assert attempt.status == OutreachStatus.failed
    assert attempt.outcome["delivered"] is False
    assert attempt.outcome["error"] == "carrier rejected"
