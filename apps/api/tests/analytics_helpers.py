"""Seed builders for analytics tests. All helpers assume the
current_clinic_id ContextVar is already set (via set_clinic_context).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from app.models import (
    Appointment,
    AppointmentStatus,
    DischargeStatus,
    DischargeSummary,
    Document,
    DocumentClassification,
    DocumentExtraction,
    DocumentStatus,
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
    Patient,
    PriorAuth,
    PriorAuthStatus,
    Provider,
    ProviderType,
    Referral,
    ReferralStatus,
    UrgencyLevel,
    UrgencyTier,
)


def make_patient(
    *,
    clinic_id: UUID,
    first: str = "Pat",
    last: str = "Test",
    phone: str = "412-555-0100",
    email: str | None = "pat@example.com",
) -> Patient:
    """phone defaults to a valid value because the column is NOT NULL;
    pass `phone=""` to represent a missing phone for risk-scoring tests."""
    return Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        mrn=f"MRN-{uuid4().hex[:6]}",
        first_name=first,
        last_name=last,
        dob="1970-01-01",
        phone=phone,
        email=email,
    )


def make_referral(
    *,
    clinic_id: UUID,
    patient_id: UUID,
    referring_provider_id: UUID | None = None,
    urgency: UrgencyLevel = UrgencyLevel.routine,
    status: ReferralStatus = ReferralStatus.needs_review,
    document_id: UUID | None = None,
) -> Referral:
    return Referral(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        document_id=document_id,
        referring_provider_id=referring_provider_id,
        urgency=urgency,
        status=status,
        diagnosis_codes=["I25.10"],
        procedure_codes=["93306"],
    )


def make_discharge(
    *,
    clinic_id: UUID,
    patient_id: UUID,
    tier: UrgencyTier = UrgencyTier.medium,
    status: DischargeStatus = DischargeStatus.new,
    discharge_days_ago: int = 7,
) -> DischargeSummary:
    return DischargeSummary(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        urgency_tier=tier,
        status=status,
        discharge_date=date.today() - timedelta(days=discharge_days_ago),
        diagnosis_codes=["I21.4"],
        urgent_flags=[],
        follow_up_window_days=7,
    )


def make_outreach(
    *,
    clinic_id: UUID,
    patient_id: UUID,
    referral_id: UUID | None = None,
    status: OutreachStatus = OutreachStatus.no_response,
    attempt_number: int = 1,
    channel: OutreachChannel = OutreachChannel.sms,
    scheduled_at: datetime | None = None,
) -> OutreachAttempt:
    return OutreachAttempt(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        referral_id=referral_id,
        channel=channel,
        status=status,
        attempt_number=attempt_number,
        scheduled_at=scheduled_at or datetime.now(UTC),
    )


def make_appointment(
    *,
    clinic_id: UUID,
    patient_id: UUID,
    provider_id: UUID,
    referral_id: UUID | None = None,
    discharge_summary_id: UUID | None = None,
    days_from_now: int = 7,
    status: AppointmentStatus = AppointmentStatus.scheduled,
) -> Appointment:
    return Appointment(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        provider_id=provider_id,
        referral_id=referral_id,
        discharge_summary_id=discharge_summary_id,
        appointment_at=datetime.now(UTC) + timedelta(days=days_from_now),
        appointment_type="follow_up",
        status=status,
    )


def make_provider(
    *,
    clinic_id: UUID,
    first: str = "Ref",
    last: str = "Doc",
    practice: str | None = "Test Cardio",
    ptype: ProviderType = ProviderType.referring,
) -> Provider:
    return Provider(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name=first,
        last_name=last,
        npi=f"{uuid4().int % 10**10:010d}",
        practice_name=practice,
        provider_type=ptype,
    )


def make_prior_auth(
    *,
    clinic_id: UUID,
    patient_id: UUID,
    payer_name: str = "UPMC Health Plan",
    status: PriorAuthStatus = PriorAuthStatus.submitted,
    submitted_at: datetime | None = None,
    approved_at: datetime | None = None,
    denied_at: datetime | None = None,
) -> PriorAuth:
    return PriorAuth(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        payer_name=payer_name,
        procedure_codes=["93458"],
        diagnosis_codes=["I25.10"],
        status=status,
        submitted_at=submitted_at,
        approved_at=approved_at,
        denied_at=denied_at,
    )


def make_extraction(
    *,
    clinic_id: UUID,
    document_id: UUID,
    missing_fields: list[str],
) -> DocumentExtraction:
    return DocumentExtraction(
        id=uuid4(),
        clinic_id=clinic_id,
        document_id=document_id,
        extraction_data={},
        field_confidences={},
        missing_fields=missing_fields,
    )


def make_document(
    *,
    clinic_id: UUID,
    patient_id: UUID | None = None,
    classification: DocumentClassification = DocumentClassification.referral,
    status: DocumentStatus = DocumentStatus.extracted,
) -> Document:
    return Document(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        file_path=f"/tmp/{uuid4()}.pdf",
        file_name="ref.pdf",
        file_size=1024,
        mime_type="application/pdf",
        classification=classification,
        status=status,
    )
