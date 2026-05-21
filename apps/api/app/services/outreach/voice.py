"""Voice initiation service.

v1 records a placeholder Call row + records the script context the
LiveKit/Ember agent (Module 6) will pick up. The stub provider just logs
the attempt; real voice delivery comes when Ember ships.
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
    """Initiate a voice call for the given attempt. Inserts a Call
    placeholder row tied to the attempt and mutates `attempt` in place.

    The real LiveKit dial-out + Claude Haiku dialogue arrives in Module 6
    (Ember). For v1 the call row records the script context and stays
    in `initiated` status."""
    if attempt.channel != OutreachChannel.voice:
        raise ValueError(
            f"initiate_voice_call expected channel=voice, got channel={attempt.channel.value!r}"
        )
    provider = get_outreach_provider()
    script_context = render_voice_script_context(
        patient_first_name=patient.first_name,
        urgency=urgency,
        clinic_name=clinic_name,
    )
    result = await provider.send(
        OutreachMessage(
            channel=OutreachChannel.voice,
            to=patient.phone,
            body=script_context["greeting"],
            metadata={
                **script_context,
                "attempt_id": str(attempt.id),
                "patient_id": str(patient.id),
            },
        )
    )
    started = datetime.now(UTC)
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
    attempt.status = OutreachStatus.sent if result.delivered else OutreachStatus.failed
    attempt.sent_at = started
    attempt.outcome = {
        **(attempt.outcome or {}),
        "delivered": result.delivered,
        "call_id": str(call.id),
        "provider_message_id": result.provider_message_id,
        "error": result.error,
    }
    return result
