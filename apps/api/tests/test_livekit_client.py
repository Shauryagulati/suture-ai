"""LiveKitClient tests.

Token minting is a pure-Python pipeline that produces a JWT — we decode
the payload (no signature check) and assert the grants. Room CRUD and
agent dispatch hit aiohttp; we replace the internal `LiveKitAPI` with a
fake whose `room` / `agent_dispatch` attributes record the requests.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.services.voice.livekit_client import (
    DispatchedCall,
    LiveKitClient,
    room_name_for_call,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode the JWT payload without verifying the signature."""
    _, payload_b64, _ = token.split(".")
    payload_b64 += "=" * (-len(payload_b64) % 4)
    decoded: dict[str, Any] = json.loads(base64.urlsafe_b64decode(payload_b64))
    return decoded


class _RoomRecorder:
    """Captures create_room / delete_room calls without hitting LiveKit."""

    def __init__(self) -> None:
        self.created: list[Any] = []
        self.deleted: list[Any] = []
        self.delete_raises: Exception | None = None

    async def create_room(self, req: Any) -> Any:
        self.created.append(req)
        return req

    async def delete_room(self, req: Any) -> Any:
        if self.delete_raises is not None:
            exc = self.delete_raises
            self.delete_raises = None
            raise exc
        self.deleted.append(req)
        return req


class _DispatchRecorder:
    def __init__(self) -> None:
        self.dispatched: list[Any] = []

    async def create_dispatch(self, req: Any) -> Any:
        self.dispatched.append(req)
        return req


class _FakeLiveKitAPI:
    def __init__(self) -> None:
        self.room = _RoomRecorder()
        self.agent_dispatch = _DispatchRecorder()
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


def _client_with_fakes() -> tuple[LiveKitClient, _FakeLiveKitAPI]:
    c = LiveKitClient(url="ws://mock", api_key="testkey", api_secret="testsecret")
    fake = _FakeLiveKitAPI()
    c._api = fake  # type: ignore[assignment]
    return c, fake


# ── Construction ──────────────────────────────────────────────────────


def test_constructor_rejects_missing_credentials() -> None:
    with pytest.raises(ValueError, match="api_key"):
        LiveKitClient(url="ws://x", api_key="", api_secret="s")


# ── Room name ─────────────────────────────────────────────────────────


def test_room_name_includes_call_uuid() -> None:
    cid = UUID("11111111-2222-3333-4444-555555555555")
    assert room_name_for_call(cid) == "call-11111111-2222-3333-4444-555555555555"


# ── Tokens ────────────────────────────────────────────────────────────


def test_mint_token_payload_includes_identity_and_room() -> None:
    c, _ = _client_with_fakes()
    token = c.mint_access_token(identity="patient:abc", room="call-xyz")
    payload = _decode_jwt_payload(token)
    assert payload["sub"] == "patient:abc"
    # AccessTokens carry the grants under "video"
    assert payload["video"]["room"] == "call-xyz"
    assert payload["video"]["roomJoin"] is True


def test_mint_token_carries_name_and_metadata() -> None:
    c, _ = _client_with_fakes()
    token = c.mint_access_token(
        identity="patient:abc",
        room="call-xyz",
        name="Sarah",
        metadata={"clinic_id": "c-1"},
    )
    payload = _decode_jwt_payload(token)
    assert payload.get("name") == "Sarah"
    assert json.loads(payload["metadata"]) == {"clinic_id": "c-1"}


def test_mint_agent_token_sets_agent_flag() -> None:
    c, _ = _client_with_fakes()
    token = c.mint_access_token(identity="agent:ember", room="call-xyz", is_agent=True)
    payload = _decode_jwt_payload(token)
    assert payload["video"]["agent"] is True


# ── Rooms ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_room_serializes_metadata_as_json() -> None:
    c, fake = _client_with_fakes()
    cid = uuid4()
    await c.create_room(
        name="call-test",
        metadata={"call_id": str(cid), "script_context": {"first_name": "Sarah"}},
    )
    assert len(fake.room.created) == 1
    req = fake.room.created[0]
    decoded = json.loads(req.metadata)
    assert decoded["call_id"] == str(cid)
    assert decoded["script_context"]["first_name"] == "Sarah"
    assert req.name == "call-test"


@pytest.mark.asyncio
async def test_delete_room_swallows_not_found() -> None:
    c, fake = _client_with_fakes()
    fake.room.delete_raises = RuntimeError("twirp: not_found: no such room")
    await c.delete_room("call-vanished")  # must not raise
    # No further raise; deleted not recorded because we raised, but that's fine.


@pytest.mark.asyncio
async def test_delete_room_propagates_other_errors() -> None:
    c, fake = _client_with_fakes()
    fake.room.delete_raises = RuntimeError("twirp: internal: kaboom")
    with pytest.raises(RuntimeError, match="kaboom"):
        await c.delete_room("call-x")


# ── Agent dispatch ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_agent_targets_ember_with_metadata() -> None:
    c, fake = _client_with_fakes()
    await c.dispatch_agent(room="call-test", metadata={"call_id": "c-1"})
    assert len(fake.agent_dispatch.dispatched) == 1
    req = fake.agent_dispatch.dispatched[0]
    assert req.agent_name == "ember"
    assert req.room == "call-test"
    assert json.loads(req.metadata) == {"call_id": "c-1"}


# ── start_call orchestration ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_call_returns_both_tokens_and_room_name() -> None:
    c, fake = _client_with_fakes()
    call_id = uuid4()
    clinic_id = uuid4()
    patient_id = uuid4()

    result = await c.start_call(
        call_id=call_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        script_context={"first_name": "Sarah", "greeting": "Hi Sarah"},
    )
    assert isinstance(result, DispatchedCall)
    assert result.room_name == f"call-{call_id}"
    # Both tokens are non-empty JWTs.
    assert result.agent_token.count(".") == 2
    assert result.patient_token.count(".") == 2
    # Room created + agent dispatched exactly once each.
    assert len(fake.room.created) == 1
    assert len(fake.agent_dispatch.dispatched) == 1
    # Patient token identifies as patient; agent token identifies as ember.
    assert _decode_jwt_payload(result.patient_token)["sub"] == f"patient:{patient_id}"
    assert _decode_jwt_payload(result.agent_token)["sub"] == f"agent:ember:{call_id}"
    assert _decode_jwt_payload(result.agent_token)["video"]["agent"] is True
