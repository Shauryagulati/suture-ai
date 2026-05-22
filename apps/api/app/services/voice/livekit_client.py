"""Thin wrapper around the LiveKit server SDK.

Responsibilities:

- Mint access-token JWTs for the patient (browser caller) + the agent.
- Create LiveKit rooms with attached metadata (clinic_id, call_id,
  patient_id, script_context).
- Dispatch the Ember worker to a room via the agent-dispatch API.
- Delete rooms idempotently when calls end.

All HTTP work goes through `livekit.api.LiveKitAPI`. The API owns its
own aiohttp session — call `aclose()` when shutting down.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from livekit import api


def room_name_for_call(call_id: UUID) -> str:
    """Stable room name for a Call row. LiveKit allows [A-Za-z0-9_-]."""
    return f"call-{call_id}"


@dataclass(frozen=True)
class DispatchedCall:
    """Result bundle returned to LiveKitOutreachProvider."""

    room_name: str
    agent_token: str
    patient_token: str


class LiveKitClient:
    """Wrapper for token mint + room/agent dispatch."""

    DEFAULT_TOKEN_TTL_SECONDS = 600  # 10 minutes — generous for a single call
    DEFAULT_ROOM_TIMEOUT_SECONDS = 300  # close empty rooms after 5 min
    AGENT_NAME = "ember"

    def __init__(self, *, url: str, api_key: str, api_secret: str) -> None:
        if not (url and api_key and api_secret):
            raise ValueError(
                "LiveKitClient requires url, api_key, api_secret — "
                "run `make gen-livekit-keys`."
            )
        self.url = url
        self.api_key = api_key
        self.api_secret = api_secret
        self._api: api.LiveKitAPI | None = None

    @property
    def http(self) -> api.LiveKitAPI:
        if self._api is None:
            self._api = api.LiveKitAPI(self.url, self.api_key, self.api_secret)
        return self._api

    async def aclose(self) -> None:
        if self._api is not None:
            await self._api.aclose()  # type: ignore[no-untyped-call]
            self._api = None

    # ── Tokens ───────────────────────────────────────────────────

    def mint_access_token(
        self,
        *,
        identity: str,
        room: str,
        ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
        can_publish: bool = True,
        can_subscribe: bool = True,
        is_agent: bool = False,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Mint a JWT for joining `room` as `identity`."""
        grants = api.VideoGrants(
            room=room,
            room_join=True,
            can_publish=can_publish,
            can_subscribe=can_subscribe,
            agent=is_agent,
        )
        token = (
            api.AccessToken(self.api_key, self.api_secret)
            .with_identity(identity)
            .with_grants(grants)
            .with_ttl(timedelta(seconds=ttl_seconds))
        )
        if name is not None:
            token = token.with_name(name)
        if metadata is not None:
            token = token.with_metadata(json.dumps(metadata, default=str))
        return token.to_jwt()

    # ── Rooms ────────────────────────────────────────────────────

    async def create_room(
        self,
        *,
        name: str,
        metadata: dict[str, Any],
        empty_timeout_seconds: int = DEFAULT_ROOM_TIMEOUT_SECONDS,
    ) -> None:
        """Create a LiveKit room with attached JSON metadata.

        The voice-agent worker reads `metadata` at join time to pick up
        `clinic_id`, `call_id`, `patient_id`, and `script_context`. No
        PHI here — only IDs + script_context (already redacted greeting
        text, no SSN / DOB / phone).
        """
        await self.http.room.create_room(
            api.CreateRoomRequest(
                name=name,
                metadata=json.dumps(metadata, default=str),
                empty_timeout=empty_timeout_seconds,
            )
        )

    async def delete_room(self, name: str) -> None:
        """Delete a room. Swallows 'not found' / 'not_found' so retries are idempotent."""
        try:
            await self.http.room.delete_room(api.DeleteRoomRequest(room=name))
        except Exception as e:
            msg = str(e).lower().replace("_", " ")
            if "not found" in msg or "notfound" in msg:
                return
            raise

    # ── Agent dispatch ───────────────────────────────────────────

    async def dispatch_agent(
        self,
        *,
        room: str,
        metadata: dict[str, Any],
    ) -> None:
        """Tell the Ember worker pool to join `room` for this call."""
        await self.http.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=self.AGENT_NAME,
                room=room,
                metadata=json.dumps(metadata, default=str),
            )
        )

    # ── High-level orchestration ─────────────────────────────────

    async def start_call(
        self,
        *,
        call_id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        script_context: dict[str, Any],
    ) -> DispatchedCall:
        """Mint tokens, create the room, dispatch the agent. Returns the
        room name + both tokens so the API process can hand them back to
        the browser caller and persist them on OutreachAttempt.outcome."""
        room = room_name_for_call(call_id)
        metadata: dict[str, Any] = {
            "call_id": str(call_id),
            "clinic_id": str(clinic_id),
            "patient_id": str(patient_id),
            "script_context": script_context,
        }
        await self.create_room(name=room, metadata=metadata)
        await self.dispatch_agent(room=room, metadata=metadata)
        agent_token = self.mint_access_token(
            identity=f"agent:ember:{call_id}",
            room=room,
            is_agent=True,
            name="Ember",
        )
        patient_token = self.mint_access_token(
            identity=f"patient:{patient_id}",
            room=room,
            name=script_context.get("first_name") or "Patient",
        )
        return DispatchedCall(
            room_name=room,
            agent_token=agent_token,
            patient_token=patient_token,
        )
