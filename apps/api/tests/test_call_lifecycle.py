"""Lifecycle tests for the Ember worker pipeline.

Drives `run_call_pipeline` + `persist_call_end` directly with mocked
audio I/O, stub LLM, and a fake TranscriptPublisher. The tests don't
boot a real LiveKit server or a real Redis. They assert the DB
side-effects on the Call / CallTranscript / OutreachAttempt rows that
the production worker would emit.
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Make the ember worker package importable for these tests.
_VOICE_AGENT_ROOT = Path(__file__).resolve().parents[3] / "services" / "voice-agent"
if str(_VOICE_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_VOICE_AGENT_ROOT))

from ember.worker import (  # noqa: E402  — late import after sys.path setup
    CallMetadata,
    CallOutcome,
    persist_call_end,
    run_call_pipeline,
)

from app.models.call import Call, CallStatus, CallTranscript, CallType  # noqa: E402
from app.models.outreach_attempt import (  # noqa: E402
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient  # noqa: E402
from app.services.llm.base import LLMProvider  # noqa: E402
from app.services.voice.agent import EmberAgent  # noqa: E402
from app.utils.context import current_clinic_id, current_user_id  # noqa: E402

pytestmark = pytest.mark.asyncio


# ── Stubs ──────────────────────────────────────────────────────────


@dataclass
class _StubLLM(LLMProvider):
    responses: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, str]] = field(default_factory=list)
    model: str = "stub"

    async def generate(self, *, system: str, prompt: str, max_tokens: int = 1500) -> str:
        self.calls.append({"system": system, "prompt": prompt})
        if not self.responses:
            raise AssertionError("stub LLM exhausted")
        return json.dumps(self.responses.pop(0))

    async def stream(
        self, *, system: str, prompt: str, max_tokens: int = 500
    ) -> AsyncIterator[str]:
        yield await self.generate(system=system, prompt=prompt, max_tokens=max_tokens)


@dataclass
class _StubSTT:
    """Yields scripted transcriptions in order — one per `transcribe_pcm16` call."""

    transcripts: list[str] = field(default_factory=list)

    async def transcribe_pcm16(self, _pcm: bytes) -> str:
        return self.transcripts.pop(0) if self.transcripts else ""


@dataclass
class _StubTTS:
    sample_rate: int = 22050
    spoken: list[str] = field(default_factory=list)

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        self.spoken.append(text)
        # One chunk per call, contents irrelevant to the audio_out mock.
        yield b"\x00\x00"


class _StubAudioOut:
    def __init__(self) -> None:
        self.bytes_sent = 0

    async def speak(self, pcm16: bytes, *, sample_rate: int) -> None:
        self.bytes_sent += len(pcm16)


class _ScriptedAudioIn:
    """Yields one bytes payload per scripted patient turn, then signals
    disconnect via a `_PatientDisconnected` exception (the worker handles
    that)."""

    def __init__(self, payloads: list[bytes], *, disconnect_after: bool = True) -> None:
        self._payloads = list(payloads)
        self._disconnect_after = disconnect_after

    def __aiter__(self) -> _ScriptedAudioIn:
        return self

    async def __anext__(self) -> bytes:
        if self._payloads:
            return self._payloads.pop(0)
        if self._disconnect_after:
            from ember.worker import _PatientDisconnected

            raise _PatientDisconnected()
        raise StopAsyncIteration


@dataclass
class _StubPublisher:
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def publish_turn(self, call_id: UUID, *, role: str, text: str) -> None:
        self.events.append(("turn", {"call_id": call_id, "role": role, "text": text}))

    async def publish_state(self, call_id: UUID, *, state: str) -> None:
        self.events.append(("state", {"call_id": call_id, "state": state}))

    async def publish_end(self, call_id: UUID, *, outcome: dict[str, Any]) -> None:
        self.events.append(("end", {"call_id": call_id, "outcome": outcome}))

    async def aclose(self) -> None:
        pass


# ── Seed helpers ─────────────────────────────────────────────────────


async def _seed_call_with_attempt(
    db: AsyncSession, clinic_id: UUID
) -> tuple[Patient, OutreachAttempt, Call]:
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
    attempt = OutreachAttempt(
        clinic_id=clinic_id,
        patient_id=p.id,
        channel=OutreachChannel.voice,
        status=OutreachStatus.sent,
        scheduled_at=datetime.now(UTC),
        outcome={},
        attempt_number=3,
    )
    db.add(attempt)
    await db.flush()
    call = Call(
        clinic_id=clinic_id,
        patient_id=p.id,
        outreach_attempt_id=attempt.id,
        call_type=CallType.outbound_scheduling,
        status=CallStatus.initiated,
        started_at=datetime.now(UTC),
        outcome={"script_context": {"first_name": "Sarah", "clinic_name": "Allegheny"}},
    )
    db.add(call)
    await db.flush()
    await db.commit()
    return p, attempt, call


# ── Tests ─────────────────────────────────────────────────────────────


async def test_pipeline_greeting_then_immediate_disconnect_publishes_minimal_events() -> None:
    """Patient picks up but says nothing — the agent greets, then disconnect
    triggers the no-turn fallback."""
    agent = EmberAgent(llm=_StubLLM(), script_context={"first_name": "Sarah", "clinic_name": "X"})
    publisher = _StubPublisher()
    outcome = await run_call_pipeline(
        CallMetadata(
            call_id=uuid4(), clinic_id=uuid4(), patient_id=uuid4(), script_context={}
        ),
        agent=agent,
        stt=_StubSTT(),
        tts=_StubTTS(),
        audio_in=_ScriptedAudioIn([]),  # no patient utterances
        audio_out=_StubAudioOut(),
        publisher=publisher,
        available_slots_fn=lambda: [],
    )
    # Greeting published once.
    assert any(e[0] == "turn" and e[1]["role"] == "agent" for e in publisher.events)
    assert outcome.booked_slot is None
    assert outcome.needs_human is False  # disconnected before any state transition


async def test_pipeline_completed_call_publishes_state_and_booked_slot() -> None:
    """Two-turn flow → booked slot → FAREWELL."""
    booked_iso = "2026-05-26T15:00:00+00:00"
    llm = _StubLLM(
        responses=[
            # Turn 1: greeting → scheduling
            {"intent": "ask_clarification", "reply": "Here are some times."},
            # Turn 2: patient picks slot 0 → confirmation
            {"intent": "pick_slot", "slot_index": 0, "reply": "Confirming Tuesday at 3 — yes?"},
            # Turn 3: patient confirms → farewell
            {"intent": "confirm_yes", "reply": "Booked! Bye."},
        ]
    )
    agent = EmberAgent(llm=llm, script_context={"first_name": "Sarah", "clinic_name": "X"})
    publisher = _StubPublisher()
    stt = _StubSTT(transcripts=["yes go ahead", "Tuesday three works", "Yes confirm"])

    outcome = await run_call_pipeline(
        CallMetadata(call_id=uuid4(), clinic_id=uuid4(), patient_id=uuid4(), script_context={}),
        agent=agent,
        stt=stt,
        tts=_StubTTS(),
        audio_in=_ScriptedAudioIn([b"a", b"b", b"c"]),
        audio_out=_StubAudioOut(),
        publisher=publisher,
        available_slots_fn=lambda: [datetime.fromisoformat(booked_iso)],
    )
    assert outcome.booked_slot == booked_iso
    assert outcome.needs_human is False
    # Three state transitions emitted (scheduling, confirmation, farewell).
    state_events = [e[1]["state"] for e in publisher.events if e[0] == "state"]
    assert "scheduling" in state_events
    assert "confirmation" in state_events
    assert "farewell" in state_events


async def test_pipeline_emergency_keyword_escalates_without_llm_call() -> None:
    llm = _StubLLM()  # no scripted responses — LLM must not be called
    agent = EmberAgent(llm=llm, script_context={"first_name": "Sarah", "clinic_name": "X"})
    stt = _StubSTT(transcripts=["I'm having chest pain"])
    publisher = _StubPublisher()

    outcome = await run_call_pipeline(
        CallMetadata(call_id=uuid4(), clinic_id=uuid4(), patient_id=uuid4(), script_context={}),
        agent=agent,
        stt=stt,
        tts=_StubTTS(),
        audio_in=_ScriptedAudioIn([b"audio"]),
        audio_out=_StubAudioOut(),
        publisher=publisher,
        available_slots_fn=lambda: [],
    )
    assert outcome.needs_human is True
    assert outcome.escalation_reason == "emergency"
    assert llm.calls == []


async def test_persist_call_end_writes_encrypted_transcript_and_updates_call(
    db_session: AsyncSession, two_clinics: tuple[UUID, UUID], test_user: UUID
) -> None:
    """In production the agent user is a seeded row keyed by AGENT_USER_ID;
    tests stand in a real users row so the audit FK is satisfied."""
    clinic_a, _ = two_clinics
    current_clinic_id.set(clinic_a)
    current_user_id.set(test_user)

    _patient, _attempt, call = await _seed_call_with_attempt(db_session, clinic_a)
    started = call.started_at

    outcome = CallOutcome(
        booked_slot="2026-05-26T15:00:00+00:00",
        turns=[
            {"role": "agent", "text": "Hi Sarah, this is Ember."},
            {"role": "patient", "text": "Tuesday at three works."},
            {"role": "agent", "text": "Booked!"},
        ],
    )
    await persist_call_end(call.id, outcome=outcome, started_at=started, status=CallStatus.completed)

    # persist_call_end committed in its own session; open a fresh one to
    # avoid identity-map staleness on the test's session.
    from app.database import async_session_maker

    async with async_session_maker() as verify:
        reloaded = await verify.get(Call, call.id)
        assert reloaded is not None
        assert reloaded.status == CallStatus.completed
        assert reloaded.ended_at is not None
        assert reloaded.duration_seconds is not None
        assert reloaded.outcome["booked_slot"] == "2026-05-26T15:00:00+00:00"
        assert reloaded.outcome["turn_count"] == 3

        transcript = (
            await verify.execute(select(CallTranscript).where(CallTranscript.call_id == call.id))
        ).scalar_one()
        assert "Sarah" in transcript.full_transcript  # ORM decryption works
        raw_ciphertext = (
            await verify.execute(
                text("SELECT full_transcript FROM call_transcripts WHERE id = :i").bindparams(
                    i=transcript.id
                )
            )
        ).scalar_one()
        assert "Sarah" not in raw_ciphertext
        assert raw_ciphertext.startswith("gAAAAA")
        structured_blob = json.dumps(transcript.structured_data)
        assert "Sarah" not in structured_blob
        assert "Tuesday" not in structured_blob

        attempt = (
            await verify.execute(
                select(OutreachAttempt).where(
                    OutreachAttempt.id == call.outreach_attempt_id
                )
            )
        ).scalar_one()
        assert attempt.status == OutreachStatus.responded
        assert attempt.outcome["booked_slot"] == "2026-05-26T15:00:00+00:00"


async def test_persist_call_end_no_slot_leaves_attempt_as_sent(
    db_session: AsyncSession, two_clinics: tuple[UUID, UUID], test_user: UUID
) -> None:
    """If the call escalated without booking, OutreachAttempt stays `sent`."""
    clinic_a, _ = two_clinics
    current_clinic_id.set(clinic_a)
    current_user_id.set(test_user)
    _patient, attempt, call = await _seed_call_with_attempt(db_session, clinic_a)

    outcome = CallOutcome(
        needs_human=True,
        escalation_reason="emergency",
        turns=[{"role": "agent", "text": "Hi"}, {"role": "patient", "text": "chest pain"}],
    )
    await persist_call_end(
        call.id, outcome=outcome, started_at=call.started_at, status=CallStatus.completed
    )
    from app.database import async_session_maker

    async with async_session_maker() as verify:
        reloaded_attempt = (
            await verify.execute(
                select(OutreachAttempt).where(OutreachAttempt.id == attempt.id)
            )
        ).scalar_one()
        assert reloaded_attempt.status == OutreachStatus.sent
        assert "booked_slot" not in reloaded_attempt.outcome


async def test_persist_call_end_writes_under_correct_clinic(
    db_session: AsyncSession, two_clinics: tuple[UUID, UUID], test_user: UUID
) -> None:
    """The transcript's clinic_id matches the call's — tenant guard
    fires correctly through the worker."""
    clinic_a, _clinic_b = two_clinics
    current_clinic_id.set(clinic_a)
    current_user_id.set(test_user)
    _, _, call = await _seed_call_with_attempt(db_session, clinic_a)

    await persist_call_end(
        call.id,
        outcome=CallOutcome(turns=[{"role": "agent", "text": "hi"}]),
        started_at=call.started_at,
        status=CallStatus.completed,
    )
    from app.database import async_session_maker

    async with async_session_maker() as verify:
        transcript = (
            await verify.execute(
                select(CallTranscript).where(CallTranscript.call_id == call.id)
            )
        ).scalar_one()
        assert transcript.clinic_id == clinic_a
