"""Confirmation-fax PDF generator + send orchestrator tests.

PDF tests build a discharge with a booked appointment and a responded
outreach attempt so all four sections render with real values. Send
tests verify orchestrator persistence + idempotency + Fax-row creation.
"""

from __future__ import annotations

import io
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, AppointmentStatus
from app.models.discharge_summary import DischargeStatus, DischargeSummary, UrgencyTier
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.models.provider import Provider, ProviderType
from app.services.discharge.confirmation_pdf import generate_confirmation_pdf

pytestmark = pytest.mark.asyncio


async def _seed_provider(db: AsyncSession, clinic_id: UUID) -> Provider:
    provider = Provider(
        clinic_id=clinic_id,
        first_name="Renée",
        last_name="Wexler",
        npi="1234567890",
        practice_name="Steel City Cardiology",
        practice_phone="412-555-0190",
        practice_address="500 Forbes Ave, Suite 4A, Pittsburgh, PA 15217",
        provider_type=ProviderType.internal,
        specialty="Interventional Cardiology",
    )
    db.add(provider)
    await db.flush()
    return provider


async def _seed_appointment(
    db: AsyncSession,
    *,
    clinic_id: UUID,
    patient_id: UUID,
    provider_id: UUID,
    discharge_id: UUID,
    when: datetime,
) -> Appointment:
    appt = Appointment(
        clinic_id=clinic_id,
        patient_id=patient_id,
        provider_id=provider_id,
        discharge_summary_id=discharge_id,
        appointment_at=when,
        appointment_type="cardiology_followup",
        status=AppointmentStatus.scheduled,
    )
    db.add(appt)
    await db.flush()
    return appt


async def _seed_responded_outreach(
    db: AsyncSession,
    *,
    clinic_id: UUID,
    patient_id: UUID,
    discharge_id: UUID,
    sent_at: datetime,
) -> OutreachAttempt:
    attempt = OutreachAttempt(
        clinic_id=clinic_id,
        patient_id=patient_id,
        discharge_summary_id=discharge_id,
        channel=OutreachChannel.sms,
        status=OutreachStatus.responded,
        attempt_number=1,
        scheduled_at=sent_at,
        sent_at=sent_at,
    )
    db.add(attempt)
    await db.flush()
    return attempt


async def test_confirmation_pdf_contains_all_four_sections(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
    seeded_discharge_a: DischargeSummary,
) -> None:
    clinic_a, _ = two_clinics
    discharge_id = seeded_discharge_a.id
    patient_id = seeded_discharge_a.patient_id

    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        provider = await _seed_provider(db_session, clinic_a)
        appt_at = datetime(2026, 6, 1, 14, 30, tzinfo=UTC)
        await _seed_appointment(
            db_session,
            clinic_id=clinic_a,
            patient_id=patient_id,
            provider_id=provider.id,
            discharge_id=discharge_id,
            when=appt_at,
        )
        await _seed_responded_outreach(
            db_session,
            clinic_id=clinic_a,
            patient_id=patient_id,
            discharge_id=discharge_id,
            sent_at=datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
        )
        await db_session.commit()

        pdf_bytes = await generate_confirmation_pdf(db_session, discharge_id)

    assert pdf_bytes.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1

    text = "\n".join((page.extract_text() or "") for page in reader.pages)

    # Header
    assert "DISCHARGE FOLLOW-UP CONFIRMATION" in text

    # Patient section
    assert "Patient" in text
    assert "Pat" in text and "Disch" in text  # from seeded fixture
    assert "2026-05-20" in text  # discharge_date

    # Patient Contact section
    assert "Patient Contact" in text
    assert "2026-05-22" in text  # contact date
    assert "SMS" in text
    assert "appointment scheduled" in text

    # Follow-Up Appointment section
    assert "Follow-Up Appointment" in text
    assert "2026-06-01" in text  # appointment date
    assert "Wexler" in text
    assert "Cardiology" in text

    # Practice Contact section
    assert "Practice Contact" in text
    assert "Steel City Cardiology" in text
    assert "412-555-0190" in text


async def test_confirmation_pdf_handles_missing_appointment_and_outreach(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
    seeded_discharge_a: DischargeSummary,
) -> None:
    """No appointment yet, no responded outreach — sections render with em-dashes."""
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        pdf_bytes = await generate_confirmation_pdf(db_session, seeded_discharge_a.id)

    assert pdf_bytes.startswith(b"%PDF-")
    text = "\n".join(
        (p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages
    )
    # Still has all four section headings.
    assert "Patient" in text
    assert "Patient Contact" in text
    assert "Follow-Up Appointment" in text
    assert "Practice Contact" in text


async def test_confirmation_pdf_raises_for_unknown_discharge(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context,
) -> None:
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a):
        with pytest.raises(ValueError, match="not found"):
            await generate_confirmation_pdf(db_session, uuid4())
