"""SMS send service — renders the template, calls the provider, updates
the OutreachAttempt row in place. Caller commits the session."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.discharge_summary import UrgencyTier
from app.models.document import UrgencyLevel
from app.models.outreach_attempt import OutreachAttempt, OutreachChannel, OutreachStatus
from app.models.patient import Patient
from app.services.outreach.base import OutreachMessage, OutreachResult
from app.services.outreach.factory import get_outreach_provider
from app.services.outreach.templates import render_sms


async def send_sms(
    *,
    attempt: OutreachAttempt,
    patient: Patient,
    urgency: UrgencyTier | UrgencyLevel,
    scheduling_link_url: str,
) -> OutreachResult:
    """Send an SMS for the given attempt. Mutates `attempt` (status,
    sent_at, outcome) in place; caller commits."""
    if attempt.channel != OutreachChannel.sms:
        raise ValueError(
            f"send_sms expected channel=sms, got channel={attempt.channel.value!r}"
        )
    provider = get_outreach_provider()
    rendered = render_sms(
        patient_first_name=patient.first_name,
        scheduling_link_url=scheduling_link_url,
        urgency=urgency,
    )
    result = await provider.send(
        OutreachMessage(
            channel=OutreachChannel.sms,
            to=patient.phone,
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
