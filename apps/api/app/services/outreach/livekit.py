"""LiveKitOutreachProvider — voice delivery via the LiveKit SFU.

Implements the OutreachProvider ABC so the cadence engine can swap in
LiveKit as the voice channel without touching `initiate_voice_call`.

This provider only DISPATCHES. The actual call is driven by the
voice-agent worker (`services/voice-agent/`) which subscribes to the
dispatched room. SMS / email channels are not supported and return
delivered=False per the ABC contract.
"""

from __future__ import annotations

from uuid import UUID

from app.config import get_settings
from app.models.outreach_attempt import OutreachChannel
from app.services.outreach.base import OutreachMessage, OutreachProvider, OutreachResult
from app.services.voice.livekit_client import LiveKitClient


class LiveKitOutreachProvider(OutreachProvider):
    """Outbound voice dispatch via LiveKit. Voice channel only."""

    def __init__(self, *, client: LiveKitClient | None = None) -> None:
        if client is None:
            settings = get_settings()
            client = LiveKitClient(
                url=settings.livekit_url,
                api_key=settings.livekit_api_key,
                api_secret=settings.livekit_api_secret,
            )
        self._client = client

    async def send(self, message: OutreachMessage) -> OutreachResult:
        if message.channel != OutreachChannel.voice:
            return OutreachResult(
                delivered=False,
                error=(
                    f"LiveKitOutreachProvider supports voice only; "
                    f"got channel={message.channel.value!r}"
                ),
            )

        try:
            call_id = UUID(str(message.metadata["call_id"]))
            clinic_id = UUID(str(message.metadata["clinic_id"]))
            patient_id = UUID(str(message.metadata["patient_id"]))
        except (KeyError, ValueError, TypeError) as e:
            return OutreachResult(
                delivered=False,
                error=f"missing or invalid call metadata: {e!r}",
            )

        # script_context = everything in metadata except the routing keys
        # we already pulled out above.
        _routing_keys = {"call_id", "clinic_id", "patient_id", "attempt_id"}
        script_context = {k: v for k, v in message.metadata.items() if k not in _routing_keys}

        try:
            dispatched = await self._client.start_call(
                call_id=call_id,
                clinic_id=clinic_id,
                patient_id=patient_id,
                script_context=script_context,
            )
        except Exception as e:
            return OutreachResult(delivered=False, error=f"livekit dispatch failed: {e!r}")

        return OutreachResult(
            delivered=True,
            provider_message_id=dispatched.room_name,
            raw={
                "room_name": dispatched.room_name,
                "agent_token": dispatched.agent_token,
                "patient_token": dispatched.patient_token,
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()
