"""Ephemeral, call-scoped stream token for the transcript WebSocket.

The transcript WS used to authenticate with the full FastAPI access bearer
passed in the URL (`?token=<access jwt>`), which leaked a 1h, full-clinic
credential into the browser, history, and any URL log. It now uses a
short-lived token scoped to a single call, minted server-side.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call import Call, CallStatus, CallType
from app.models.patient import Patient
from app.utils.security import (
    JwtError,
    decode_stream_token,
    encode_access_token,
    encode_stream_token,
)

# ── token unit tests (sync) ──


def test_stream_token_roundtrip() -> None:
    call_id = uuid4()
    clinic_id = uuid4()
    token, expires = encode_stream_token(call_id=call_id, clinic_id=clinic_id)
    decoded = decode_stream_token(token)
    assert decoded["call_id"] == str(call_id)
    assert decoded["clinic_id"] == str(clinic_id)
    assert decoded["type"] == "stream"
    assert expires > datetime.now(UTC)


def test_decode_stream_token_rejects_access_token() -> None:
    # An access bearer must NOT be accepted as a stream token.
    access, _ = encode_access_token(user_id=uuid4(), clinic_id=uuid4(), role="admin")
    with pytest.raises(JwtError):
        decode_stream_token(access)


# ── endpoint tests (async) ──


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
    await db.commit()
    return call


@pytest.mark.asyncio
async def test_stream_token_endpoint_returns_scoped_token(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, headers_a, user_id_a = await authed_client_factory("a")
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        call = await _seed_call(db_session, clinic_a)

    resp = await client.get(f"/api/voice/calls/{call.id}/stream-token", headers=headers_a)
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    decoded = decode_stream_token(token)
    assert decoded["call_id"] == str(call.id)
    assert decoded["clinic_id"] == str(clinic_a)


@pytest.mark.asyncio
async def test_stream_token_endpoint_404_for_foreign_call(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, headers_a, _user_id_a = await authed_client_factory("a")
    _, _, user_id_b = await authed_client_factory("b")
    _clinic_a, clinic_b = two_clinics
    with set_clinic_context(clinic_id=clinic_b, user_id=user_id_b):
        call_b = await _seed_call(db_session, clinic_b)

    resp = await client.get(f"/api/voice/calls/{call_b.id}/stream-token", headers=headers_a)
    assert resp.status_code == 404
