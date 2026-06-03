"""CallTranscript.full_transcript must be Fernet-encrypted at rest.

The voice agent (Ember) writes verbatim patient + agent dialogue here;
PHI in the body is the norm, not the exception. The TypeDecorator swap
landed in migration 0006 — these tests are the regression net.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patient
from app.models.call import Call, CallStatus, CallTranscript, CallType

pytestmark = pytest.mark.asyncio


async def _make_patient(db_session: AsyncSession, clinic_id: UUID) -> Patient:
    p = Patient(
        clinic_id=clinic_id,
        first_name="Sarah",
        last_name="Test",
        dob="1965-01-15",
        phone="555-555-0100",
    )
    db_session.add(p)
    await db_session.flush()
    return p


async def _make_call(db_session: AsyncSession, clinic_id: UUID, patient_id: UUID) -> Call:
    call = Call(
        clinic_id=clinic_id,
        patient_id=patient_id,
        call_type=CallType.outbound_scheduling,
        status=CallStatus.completed,
        started_at=datetime.now(UTC),
    )
    db_session.add(call)
    await db_session.flush()
    return call


async def test_full_transcript_stored_encrypted(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    clinic_a, _ = two_clinics
    phi_blob = (
        "agent: Hello Sarah, this is calling from Allegheny Cardiology.\n"
        "patient: Hi. My SSN is 123-45-6789 if you need to verify.\n"
        "agent: I don't need that — let's get you scheduled for Tuesday at 3.\n"
    )
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        patient = await _make_patient(db_session, clinic_a)
        call = await _make_call(db_session, clinic_a, patient.id)
        transcript = CallTranscript(
            clinic_id=clinic_a,
            call_id=call.id,
            full_transcript=phi_blob,
        )
        db_session.add(transcript)
        await db_session.commit()

        raw = await db_session.execute(
            text("SELECT full_transcript FROM call_transcripts WHERE id = :tid").bindparams(
                tid=transcript.id
            )
        )
        ciphertext = raw.scalar_one()

    assert "123-45-6789" not in ciphertext, "raw column must not contain plaintext SSN"
    assert "Sarah" not in ciphertext, "raw column must not contain plaintext patient name"
    assert "Tuesday" not in ciphertext, "raw column must not contain plaintext scheduling content"
    assert ciphertext.startswith("gAAAAA"), (
        f"expected Fernet ciphertext prefix, got: {ciphertext[:20]!r}"
    )


async def test_full_transcript_read_decrypted(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    clinic_a, _ = two_clinics
    payload = "agent: bye\npatient: thanks\n"
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        patient = await _make_patient(db_session, clinic_a)
        call = await _make_call(db_session, clinic_a, patient.id)
        db_session.add(CallTranscript(clinic_id=clinic_a, call_id=call.id, full_transcript=payload))
        await db_session.commit()

        result = await db_session.execute(select(CallTranscript))
        transcript = result.scalars().one()

    assert transcript.full_transcript == payload


async def test_ciphertext_differs_for_same_transcript(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    """Fernet uses a random IV — two identical transcripts must produce different ciphertexts."""
    clinic_a, _ = two_clinics
    payload = "agent: identical transcript body"
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        patient = await _make_patient(db_session, clinic_a)
        call_one = await _make_call(db_session, clinic_a, patient.id)
        call_two = await _make_call(db_session, clinic_a, patient.id)
        t1 = CallTranscript(clinic_id=clinic_a, call_id=call_one.id, full_transcript=payload)
        t2 = CallTranscript(clinic_id=clinic_a, call_id=call_two.id, full_transcript=payload)
        db_session.add_all([t1, t2])
        await db_session.commit()

        raw = await db_session.execute(
            text(
                "SELECT id, full_transcript FROM call_transcripts WHERE id IN (:a, :b)"
            ).bindparams(a=t1.id, b=t2.id)
        )
        ciphertexts = {row.id: row.full_transcript for row in raw}

    assert ciphertexts[t1.id] != ciphertexts[t2.id], (
        "identical transcripts produced identical ciphertext (IV randomness broken)"
    )
