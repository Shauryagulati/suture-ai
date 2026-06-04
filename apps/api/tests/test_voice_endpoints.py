"""Tests for the voice REST endpoints (active list, transcript, token,
start, end). Tenant isolation + audit hygiene are HIPAA-class hard
stops — these tests are the regression net.

WebSocket coverage lives in test_voice_websocket.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.call import Call, CallStatus, CallTranscript, CallType
from app.models.patient import Patient
from app.services.voice import livekit_client as lk_module

pytestmark = pytest.mark.asyncio


# ── Fake LiveKitClient (don't hit real LiveKit) ──────────────────────


class _FakeLiveKitClient:
    def __init__(self, *_args: Any, **_kw: Any) -> None:
        self.deleted: list[str] = []
        self.dispatched: list[dict[str, Any]] = []

    def mint_access_token(self, **kwargs: Any) -> str:
        return f"fake-jwt-{kwargs.get('identity', 'x')}"

    async def start_call(self, **kwargs: Any) -> Any:
        self.dispatched.append(kwargs)
        return lk_module.DispatchedCall(
            room_name=f"call-{kwargs['call_id']}",
            agent_token="agent-jwt",
            patient_token="patient-jwt",
        )

    async def delete_room(self, name: str) -> None:
        self.deleted.append(name)

    async def aclose(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _stub_livekit(monkeypatch: pytest.MonkeyPatch) -> _FakeLiveKitClient:
    fake = _FakeLiveKitClient()
    from app.routers import voice as voice_router

    monkeypatch.setattr(voice_router, "_livekit_client", lambda: fake)
    return fake


# ── Seed helpers ─────────────────────────────────────────────────────


async def _seed_patient(db: AsyncSession, clinic_id: UUID) -> Patient:
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
    return p


async def _seed_call(
    db: AsyncSession,
    clinic_id: UUID,
    patient_id: UUID,
    *,
    status: CallStatus = CallStatus.in_progress,
    started_at: datetime | None = None,
) -> Call:
    call = Call(
        clinic_id=clinic_id,
        patient_id=patient_id,
        call_type=CallType.outbound_scheduling,
        status=status,
        started_at=started_at or datetime.now(UTC),
        outcome={"script_context": {"first_name": "Sarah", "greeting": "Hi"}},
    )
    db.add(call)
    await db.flush()
    return call


# ── /calls/active ────────────────────────────────────────────────────


async def test_active_calls_only_returns_non_terminal_for_clinic(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, headers_a, user_id_a = await authed_client_factory("a")
    clinic_a, _ = two_clinics

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        await _seed_call(db_session, clinic_a, patient.id, status=CallStatus.in_progress)
        await _seed_call(db_session, clinic_a, patient.id, status=CallStatus.completed)
        await db_session.commit()

    resp = await client.get("/api/voice/calls/active", headers=headers_a)
    assert resp.status_code == 200
    items = resp.json()["items"]
    statuses = [c["status"] for c in items]
    assert "in_progress" in statuses
    assert "completed" not in statuses


async def test_active_calls_excludes_other_clinic(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, headers_a, _user_id_a = await authed_client_factory("a")
    _, _, user_id_b = await authed_client_factory("b")
    _clinic_a, clinic_b = two_clinics

    with set_clinic_context(clinic_id=clinic_b, user_id=user_id_b):
        patient_b = await _seed_patient(db_session, clinic_b)
        await _seed_call(db_session, clinic_b, patient_b.id, status=CallStatus.in_progress)
        await db_session.commit()

    resp = await client.get("/api/voice/calls/active", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ── /calls/{id}/transcript ──────────────────────────────────────────


async def test_get_transcript_404_while_call_in_progress(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, headers_a, user_id_a = await authed_client_factory("a")
    clinic_a, _ = two_clinics

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        call = await _seed_call(db_session, clinic_a, patient.id, status=CallStatus.in_progress)
        await db_session.commit()

    resp = await client.get(f"/api/voice/calls/{call.id}/transcript", headers=headers_a)
    assert resp.status_code == 404
    assert "in progress" in resp.text.lower()


async def test_get_transcript_decrypts_after_completion(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, headers_a, user_id_a = await authed_client_factory("a")
    clinic_a, _ = two_clinics

    transcript_body = "agent: Hi Sarah\npatient: Tuesday at 3 works.\nagent: Booked.\n"
    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        call = await _seed_call(db_session, clinic_a, patient.id, status=CallStatus.completed)
        db_session.add(
            CallTranscript(
                clinic_id=clinic_a,
                call_id=call.id,
                full_transcript=transcript_body,
                structured_data={"turns": [{"role": "agent", "ts": "2026-05-22T15:00Z"}]},
            )
        )
        await db_session.commit()

    resp = await client.get(f"/api/voice/calls/{call.id}/transcript", headers=headers_a)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["full_transcript"] == transcript_body
    assert payload["structured_data"]["turns"][0]["role"] == "agent"


async def test_get_transcript_404_for_other_clinic_call(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, _headers_a, user_id_a = await authed_client_factory("a")
    _, headers_b, _user_id_b = await authed_client_factory("b")
    clinic_a, _ = two_clinics

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        call = await _seed_call(db_session, clinic_a, patient.id, status=CallStatus.completed)
        db_session.add(CallTranscript(clinic_id=clinic_a, call_id=call.id, full_transcript="phi-x"))
        await db_session.commit()

    resp = await client.get(f"/api/voice/calls/{call.id}/transcript", headers=headers_b)
    assert resp.status_code == 404


async def test_get_transcript_audited_without_phi_in_details(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, headers_a, user_id_a = await authed_client_factory("a")
    clinic_a, _ = two_clinics
    phi = "patient SSN is 123-45-6789"

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        call = await _seed_call(db_session, clinic_a, patient.id, status=CallStatus.completed)
        db_session.add(CallTranscript(clinic_id=clinic_a, call_id=call.id, full_transcript=phi))
        await db_session.commit()

    resp = await client.get(f"/api/voice/calls/{call.id}/transcript", headers=headers_a)
    assert resp.status_code == 200

    audit = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.resource_type == "call_transcripts")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) >= 1
    for row in audit:
        details_blob = json.dumps(row.details, default=str)
        assert "123-45-6789" not in details_blob, "PHI leaked into audit details"
        assert phi not in details_blob


# ── /calls/{id}/token ────────────────────────────────────────────────


async def test_get_token_returns_jwt_and_room(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, headers_a, user_id_a = await authed_client_factory("a")
    clinic_a, _ = two_clinics

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        call = await _seed_call(db_session, clinic_a, patient.id, status=CallStatus.in_progress)
        await db_session.commit()

    resp = await client.get(f"/api/voice/calls/{call.id}/token", headers=headers_a)
    assert resp.status_code == 200
    body = resp.json()
    assert body["room_name"] == f"call-{call.id}"
    assert body["token"].startswith("fake-jwt-patient:")
    assert body["identity"] == f"patient:{patient.id}"


async def test_get_token_404_for_other_clinic(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, _headers_a, user_id_a = await authed_client_factory("a")
    _, headers_b, _user_id_b = await authed_client_factory("b")
    clinic_a, _ = two_clinics

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        call = await _seed_call(db_session, clinic_a, patient.id)
        await db_session.commit()

    resp = await client.get(f"/api/voice/calls/{call.id}/token", headers=headers_b)
    assert resp.status_code == 404


# ── /calls/{id}/start ────────────────────────────────────────────────


async def test_start_call_dispatches_and_returns_room(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
    _stub_livekit: _FakeLiveKitClient,
) -> None:
    client, headers_a, user_id_a = await authed_client_factory("a")
    clinic_a, _ = two_clinics

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        call = await _seed_call(db_session, clinic_a, patient.id, status=CallStatus.initiated)
        await db_session.commit()

    resp = await client.post(f"/api/voice/calls/{call.id}/start", headers=headers_a)
    assert resp.status_code == 200, resp.text
    assert resp.json()["room_name"] == f"call-{call.id}"
    assert len(_stub_livekit.dispatched) == 1


async def test_start_call_409_for_terminal_call(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, headers_a, user_id_a = await authed_client_factory("a")
    clinic_a, _ = two_clinics

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        call = await _seed_call(db_session, clinic_a, patient.id, status=CallStatus.completed)
        await db_session.commit()

    resp = await client.post(f"/api/voice/calls/{call.id}/start", headers=headers_a)
    assert resp.status_code == 409


# ── /calls/{id}/end ──────────────────────────────────────────────────


async def test_end_call_marks_failed_and_records_actor(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
    _stub_livekit: _FakeLiveKitClient,
) -> None:
    client, headers_a, user_id_a = await authed_client_factory("a")
    clinic_a, _ = two_clinics
    started = datetime.now(UTC)

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        call = await _seed_call(
            db_session, clinic_a, patient.id, status=CallStatus.in_progress, started_at=started
        )
        await db_session.commit()

    resp = await client.post(f"/api/voice/calls/{call.id}/end", headers=headers_a)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"

    raw = (
        await db_session.execute(
            text("SELECT outcome::text FROM calls WHERE id = :i").bindparams(i=call.id)
        )
    ).scalar_one()
    outcome = json.loads(raw)
    assert outcome["terminated_by_user"] is True
    assert outcome["terminated_by_user_id"] == str(user_id_a)
    assert _stub_livekit.deleted == [f"call-{call.id}"]


async def test_end_call_404_for_other_clinic(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
) -> None:
    client, _headers_a, user_id_a = await authed_client_factory("a")
    _, headers_b, _user_id_b = await authed_client_factory("b")
    clinic_a, _ = two_clinics

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        patient = await _seed_patient(db_session, clinic_a)
        call = await _seed_call(db_session, clinic_a, patient.id, status=CallStatus.in_progress)
        await db_session.commit()

    resp = await client.post(f"/api/voice/calls/{call.id}/end", headers=headers_b)
    assert resp.status_code == 404


# ── /test-call ───────────────────────────────────────────────────────


async def test_create_test_call_picks_patient_and_dispatches(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: Any,
    _stub_livekit: _FakeLiveKitClient,
) -> None:
    client, headers_a, user_id_a = await authed_client_factory("a")
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        await _seed_patient(db_session, clinic_a)
        await db_session.commit()

    resp = await client.post("/api/voice/test-call", headers=headers_a)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["room_name"] == f"call-{body['call_id']}"
    assert body["test_caller_url"].endswith(f"/voice/test-caller/{body['call_id']}")
    assert body["patient_name"] == "Sarah Test"
    assert len(_stub_livekit.dispatched) == 1

    with set_clinic_context(clinic_id=clinic_a, user_id=user_id_a):
        db_session.expire_all()
        call = await db_session.get(Call, UUID(body["call_id"]))
    assert call is not None and call.status == CallStatus.initiated


async def test_create_test_call_404_when_clinic_has_no_patients(
    authed_client_factory: Any,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    _stub_livekit: _FakeLiveKitClient,
) -> None:
    # Clinic B has no patients seeded in this test.
    client, headers_b, _ = await authed_client_factory("b")
    resp = await client.post("/api/voice/test-call", headers=headers_b)
    assert resp.status_code == 404
    assert len(_stub_livekit.dispatched) == 0
