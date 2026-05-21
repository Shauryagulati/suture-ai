"""Email send service — mirrors sms.send_sms but uses email channel."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.discharge_summary import UrgencyTier
from app.models.document import UrgencyLevel
from app.models.outreach_attempt import OutreachAttempt, OutreachChannel, OutreachStatus
from app.models.patient import Patient
from app.services.outreach.base import OutreachMessage, OutreachResult
from app.services.outreach.factory import get_outreach_provider
from app.services.outreach.templates import render_email


async def send_email(
    *,
    attempt: OutreachAttempt,
    patient: Patient,
    urgency: UrgencyTier | UrgencyLevel,
    scheduling_link_url: str,
    clinic_name: str,
) -> OutreachResult:
    """Send an email for the given attempt. Mutates `attempt` in place.

    Returns `OutreachResult(delivered=False, error="no email on file")`
    without touching the provider if `patient.email` is unset, and marks
    the attempt failed so the cadence can skip it."""
    if attempt.channel != OutreachChannel.email:
        raise ValueError(
            f"send_email expected channel=email, got channel={attempt.channel.value!r}"
        )
    if not patient.email:
        attempt.status = OutreachStatus.failed
        attempt.sent_at = datetime.now(UTC)
        attempt.outcome = {
            **(attempt.outcome or {}),
            "delivered": False,
            "error": "no email on file",
        }
        return OutreachResult(delivered=False, error="no email on file")

    provider = get_outreach_provider()
    rendered = render_email(
        patient_first_name=patient.first_name,
        scheduling_link_url=scheduling_link_url,
        urgency=urgency,
        clinic_name=clinic_name,
    )
    result = await provider.send(
        OutreachMessage(
            channel=OutreachChannel.email,
            to=patient.email,
            subject=rendered.subject,
            body=rendered.body,
            metadata={"attempt_id": str(attempt.id), "patient_id": str(patient.id)},
        )
    )
    attempt.status = OutreachStatus.sent if result.delivered else OutreachStatus.failed
    attempt.sent_at = datetime.now(UTC)
    attempt.outcome = {
        **(attempt.outcome or {}),
        "delivered": result.delivered,
        "provider_message_id": result.provider_message_id,
        "error": result.error,
    }
    return result
