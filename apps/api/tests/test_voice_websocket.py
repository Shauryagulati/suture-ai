"""WebSocket /api/voice/calls/{call_id}/stream tests.

Auth: a short-lived, call-scoped *stream* token passed as `?token=…`
(minted by GET /calls/{id}/stream-token). The full access bearer is NOT
accepted here — that was the leak the stream token replaces. The stream
subscribes to Redis pub/sub for the call's transcript channel; we stub
`TranscriptBus.subscribe` with a scripted async generator so tests don't
require a running Redis.

These are HIPAA-class hard stops: missing/invalid token → 4401, access
bearer rejected → 4401, wrong call/clinic → 4404, success path passes
through every published chunk in order and closes on the terminal `end`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.models.call import Call, CallStatus, CallType
from app.models.patient import Patient
from app.services.voice import transcript_bus as bus_module
from app.utils.security import encode_stream_token

pytestmark = pytest.mark.asyncio


# ── Fake TranscriptBus ───────────────────────────────────────────────


_TEST_SCRIPT: dict[UUID, list[dict[str, Any]]] = {}


class _FakeTranscriptBus:
    def __init__(self, *, redis_url: str) -> None:
        pass

    async def subscribe(self, call_id: UUID) -> AsyncIterator[dict[str, Any]]:
        for msg in _TEST_SCRIPT.get(call_id, []):
            yield msg
            if msg.get("type") == "end":
                return


@pytest.fixture(autouse=True)
def _stub_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap TranscriptBus for a fake that yields from _TEST_SCRIPT."""
    from app.routers import voice as voice_router

    monkeypatch.setattr(voice_router, "TranscriptBus", _FakeTranscriptBus)
    monkeypatch.setattr(bus_module, "TranscriptBus", _FakeTranscriptBus)
    _TEST_SCRIPT.clear()
    yield
    _TEST_SCRIPT.clear()


# ── Seed helpers ─────────────────────────────────────────────────────


async def _seed_call(db: AsyncSession, clinic_id: UUID) -> Call:
    p = Patient(
        clinic_id=clinic_id,
        first_name="Sarah",
        last_name="Test",
        dob="1965-01-15",
        phone="412-555-0100",
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    db.add(p)
    await db.flush()
    call = Call(
        clinic_id=clinic_id,
        patient_id=p.id,
        call_type=CallType.outbound_scheduling,
        status=CallStatus.in_progress,
        started_at=datetime.now(UTC),
        outcome={},
    )
    db.add(call)
    await db.flush()
    return call


# ── Tests ─────────────────────────────────────────────────────────────


async def test_ws_rejects_missing_token() -> None:
    """No ?token= → close with 4401 BEFORE any data is sent."""
    fake_call_id = uuid4()
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as exc:
            with tc.websocket_connect(f"/api/voice/calls/{fake_call_id}/stream") as ws:
                ws.receive_json()
        assert exc.value.code == 4401


async def test_ws_rejects_bogus_token() -> None:
    fake_call_id = uuid4()
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as exc:
            with tc.websocket_connect(
                f"/api/voice/calls/{fake_call_id}/stream?token=garbage"
            ) as ws:
                ws.receive_json()
        assert exc.value.code == 4401


async def test_ws_rejects_access_token(
    authed_client_factory: Any,
) -> None:
    """The full FastAPI access bearer must NOT be accepted by the WS — only
    a call-scoped stream token. This is the leak the stream token closed."""
    _client, headers_a, _user_id_a = await authed_client_factory("a")
    access_token = headers_a["Authorization"].split(" ", 1)[1]
    fake_call_id = uuid4()
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as exc:
            with tc.websocket_connect(
                f"/api/voice/calls/{fake_call_id}/stream?token={access_token}"
            ) as ws:
                ws.receive_json()
        assert exc.value.code == 4401


async def test_ws_rejects_stream_token_for_other_call(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    """A stream token authorizes exactly one call; using it on another → 4404."""
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a):
        call = await _seed_call(db_session, clinic_a)
        await db_session.commit()

    token, _ = encode_stream_token(call_id=call.id, clinic_id=clinic_a)
    other_call_id = uuid4()
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as exc:
            with tc.websocket_connect(
                f"/api/voice/calls/{other_call_id}/stream?token={token}"
            ) as ws:
                ws.receive_json()
        assert exc.value.code == 4404


async def test_ws_rejects_stream_token_with_wrong_clinic(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    """A (signed) stream token whose clinic_id doesn't own the call → 4404.
    Defense-in-depth: the WS scopes the lookup to the token's clinic."""
    clinic_a, clinic_b = two_clinics
    with set_clinic_context(clinic_id=clinic_a):
        call = await _seed_call(db_session, clinic_a)
        await db_session.commit()

    # Token claims clinic_b but the call is in clinic_a.
    token, _ = encode_stream_token(call_id=call.id, clinic_id=clinic_b)
    with TestClient(app) as tc:
        with pytest.raises(WebSocketDisconnect) as exc:
            with tc.websocket_connect(f"/api/voice/calls/{call.id}/stream?token={token}") as ws:
                ws.receive_json()
        assert exc.value.code == 4404


async def test_ws_streams_transcript_chunks_in_order(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    """Happy path — chunks emitted by the bus arrive at the client in order
    and the WS closes after the terminal `end` message."""
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a):
        call = await _seed_call(db_session, clinic_a)
        await db_session.commit()

    _TEST_SCRIPT[call.id] = [
        {"type": "turn", "role": "agent", "text": "Hi Sarah", "ts": "2026-05-22T15:00Z"},
        {"type": "turn", "role": "patient", "text": "Tuesday 3pm", "ts": "2026-05-22T15:00:05Z"},
        {"type": "state", "state": "confirmation"},
        {"type": "end", "outcome": {"booked_slot": "2026-05-26T15:00Z"}},
    ]

    token, _ = encode_stream_token(call_id=call.id, clinic_id=clinic_a)
    received: list[dict[str, Any]] = []
    with TestClient(app) as tc:
        with tc.websocket_connect(f"/api/voice/calls/{call.id}/stream?token={token}") as ws:
            # Drain until disconnect.
            try:
                while True:
                    received.append(ws.receive_json())
            except WebSocketDisconnect:
                pass

    assert [m["type"] for m in received] == ["turn", "turn", "state", "end"]
    assert received[0]["text"] == "Hi Sarah"
    assert received[3]["outcome"]["booked_slot"] == "2026-05-26T15:00Z"
