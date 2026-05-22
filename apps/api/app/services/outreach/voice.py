"""Voice initiation service.

Builds the script context, inserts the Call placeholder row (so its
`call_id` can ride along in the provider metadata for LiveKit dispatch),
hands the OutreachMessage to the configured provider, and folds the
provider's result back onto the OutreachAttempt + Call.

The stub provider ignores metadata; the LiveKit provider (Module 6 /
Ember) uses `call_id`, `clinic_id`, `patient_id`, and the script
context to mint tokens + dispatch the agent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call import Call, CallStatus, CallType
from app.models.discharge_summary import UrgencyTier
from app.models.document import UrgencyLevel
from app.models.outreach_attempt import OutreachAttempt, OutreachChannel, OutreachStatus
from app.models.patient import Patient
from app.services.outreach.base import OutreachMessage, OutreachResult
from app.services.outreach.factory import get_outreach_provider
from app.services.outreach.templates import render_voice_script_context


async def initiate_voice_call(
    session: AsyncSession,
    *,
    attempt: OutreachAttempt,
    patient: Patient,
    urgency: UrgencyTier | UrgencyLevel,
    clinic_name: str,
) -> OutreachResult:
    """Initiate a voice call for the given attempt.

    Inserts a Call row (status=initiated) tied to the attempt BEFORE the
    provider is invoked so `call_id` is available in the provider's
    metadata. The stub provider ignores it; the LiveKit provider uses
    it to name the room and tag the Ember dispatch.
    """
    if attempt.channel != OutreachChannel.voice:
        raise ValueError(
            f"initiate_voice_call expected channel=voice, got channel={attempt.channel.value!r}"
        )

    started = datetime.now(UTC)
    script_context = render_voice_script_context(
        patient_first_name=patient.first_name,
        urgency=urgency,
        clinic_name=clinic_name,
    )

    call = Call(
        patient_id=patient.id,
        outreach_attempt_id=attempt.id,
        call_type=CallType.outbound_scheduling,
        status=CallStatus.initiated,
        started_at=started,
        outcome={
            "placeholder": True,
            "module": "outreach_v1",
            "script_context": script_context,
        },
    )
    session.add(call)
    await session.flush()

    provider = get_outreach_provider()
    result = await provider.send(
        OutreachMessage(
            channel=OutreachChannel.voice,
            to=patient.phone,
            body=script_context["greeting"],
            metadata={
                **script_context,
                "attempt_id": str(attempt.id),
                "patient_id": str(patient.id),
                "clinic_id": str(patient.clinic_id),
                "call_id": str(call.id),
            },
        )
    )

    attempt.status = OutreachStatus.sent if result.delivered else OutreachStatus.failed
    attempt.sent_at = started
    attempt.outcome = {
        **(attempt.outcome or {}),
        "delivered": result.delivered,
        "call_id": str(call.id),
        "provider_message_id": result.provider_message_id,
        "error": result.error,
    }
    if result.raw:
        # LiveKit returns {room_name, agent_token, patient_token}; the
        # browser caller fetches the patient_token via the API later,
        # but persisting it here lets the test-caller page open without
        # an extra round-trip.
        attempt.outcome["provider_raw"] = result.raw
    return result
