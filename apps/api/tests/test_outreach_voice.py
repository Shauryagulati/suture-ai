"""initiate_voice_call service tests — Call placeholder + script context."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call import Call, CallStatus, CallType
from app.models.document import UrgencyLevel
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.services.outreach.factory import (
    get_outreach_provider,
    reset_outreach_provider_cache,
)
from app.services.outreach.stub import StubOutreachProvider
from app.services.outreach.voice import initiate_voice_call

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_provider_cache() -> None:
    reset_outreach_provider_cache()
    yield
    reset_outreach_provider_cache()


async def _seed_patient_and_pending_voice(
    db: AsyncSession, clinic_id: UUID
) -> tuple[Patient, OutreachAttempt]:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Pat",
        last_name="Voice",
        dob="1970-01-01",
        phone="412-555-0150",
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    attempt = OutreachAttempt(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient.id,
        channel=OutreachChannel.voice,
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


async def test_initiate_voice_creates_call_placeholder(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, attempt = await _seed_patient_and_pending_voice(db_session, clinic_a_id)
        result = await initiate_voice_call(
            db_session,
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.urgent,
            clinic_name="Steel City Cardiology",
        )
        await db_session.commit()

        call = (
            await db_session.execute(
                select(Call).where(Call.outreach_attempt_id == attempt.id)
            )
        ).scalar_one()

    assert result.delivered is True
    assert call.call_type == CallType.outbound_scheduling
    assert call.status == CallStatus.initiated
    assert call.outcome["placeholder"] is True
    assert call.outcome["module"] == "outreach_v1"
    assert call.outcome["script_context"]["first_name"] == "Pat"
    assert attempt.status == OutreachStatus.sent
    assert attempt.outcome["call_id"] == str(call.id)


async def test_initiate_voice_uses_decrypted_phone(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        patient, attempt = await _seed_patient_and_pending_voice(db_session, clinic_a_id)
        await initiate_voice_call(
            db_session,
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.urgent,
            clinic_name="Steel City Cardiology",
        )

    provider = get_outreach_provider()
    assert isinstance(provider, StubOutreachProvider)
    assert provider.sent[0].to == "412-555-0150"
    assert provider.sent[0].channel == OutreachChannel.voice
    assert "Steel City Cardiology" in provider.sent[0].body
    assert "Pat" in provider.sent[0].body


async def test_initiate_voice_rejects_non_voice_attempt(
    db_session: AsyncSession,
) -> None:
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
    with pytest.raises(ValueError, match="channel=voice"):
        await initiate_voice_call(
            db_session,
            attempt=attempt,
            patient=patient,
            urgency=UrgencyLevel.routine,
            clinic_name="Anywhere",
        )
