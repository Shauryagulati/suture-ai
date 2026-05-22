"""Ember worker — LiveKit Agents entrypoint + the audio-loop orchestration.

The framework hands us a `JobContext` per dispatched room. We:

1. Decode `clinic_id`, `call_id`, `patient_id`, `script_context` from
   `ctx.room.metadata` (set by LiveKitOutreachProvider).
2. Set the tenant ContextVars so DB writes are clinic-scoped — failure
   here would mean our DB writes get rejected by the tenant guard,
   which is the correct fail-closed behaviour.
3. Mark the Call as in_progress.
4. Run the call pipeline: greet → listen → transcribe → reply →
   loop, publishing each turn to Redis pub/sub.
5. On terminal state or patient disconnect, persist the encrypted
   CallTranscript and finalize the Call row.

The audio plumbing is deliberately separated from `run_call_pipeline`
so the lifecycle test can drive the loop with mocked STT / TTS / room
and assert the DB side-effects.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from livekit import rtc

from app.config import get_settings
from app.database import async_session_maker
from app.models.call import Call, CallStatus, CallTranscript
from app.models.outreach_attempt import OutreachAttempt, OutreachStatus
from app.services.llm.factory import get_llm_provider
from app.services.voice.agent import (
    ConversationState,
    EmberAgent,
    TurnInput,
)
from app.services.voice.stt import WhisperSTT
from app.services.voice.tts import PiperTTS
from app.utils.context import current_clinic_id, current_user_id

from ember.transcript_bus import TranscriptPublisher

log = structlog.get_logger(__name__)

# Sentinel "automated agent" user-id for audit log attribution.
AGENT_USER_ID = UUID(int=0)


# ── Protocols (mocked in tests) ──────────────────────────────────────


class AudioOutput(Protocol):
    """Whatever we use to push synthesized audio bytes out to the room."""

    async def speak(self, pcm16: bytes, *, sample_rate: int) -> None: ...


class AudioInput(Protocol):
    """Whatever yields the next patient utterance as PCM16 bytes."""

    def __aiter__(self) -> Any: ...
    async def __anext__(self) -> bytes: ...


# ── Pipeline orchestration ───────────────────────────────────────────


@dataclass
class CallMetadata:
    call_id: UUID
    clinic_id: UUID
    patient_id: UUID
    script_context: dict[str, Any]


@dataclass
class CallOutcome:
    booked_slot: str | None = None
    needs_human: bool = False
    escalation_reason: str | None = None
    turns: list[dict[str, str]] = field(default_factory=list)


async def run_call_pipeline(
    metadata: CallMetadata,
    *,
    agent: EmberAgent,
    stt: WhisperSTT,
    tts: PiperTTS,
    audio_in: AudioInput,
    audio_out: AudioOutput,
    publisher: TranscriptPublisher,
    available_slots_fn: Any,
    max_turns: int = 12,
) -> CallOutcome:
    """Drive one patient call end-to-end. Returns the outcome bundle to
    persist; does not touch the DB itself (the caller owns commit
    boundaries)."""
    outcome = CallOutcome()

    # 1. Greeting.
    greeting = agent.open()
    await _speak(greeting, tts=tts, audio_out=audio_out)
    await publisher.publish_turn(metadata.call_id, role="agent", text=greeting)
    outcome.turns.append({"role": "agent", "text": greeting})

    # 2. Listen → respond loop.
    turns_taken = 0
    try:
        async for utterance_pcm in audio_in:
            turns_taken += 1
            if turns_taken > max_turns:
                log.warning(
                    "voice.call.turn_cap",
                    call_id=str(metadata.call_id),
                    max_turns=max_turns,
                )
                outcome.needs_human = True
                outcome.escalation_reason = "turn_cap_exceeded"
                break

            text = await stt.transcribe_pcm16(utterance_pcm)
            if not text:
                continue  # silence — wait for the next utterance
            await publisher.publish_turn(metadata.call_id, role="patient", text=text)
            outcome.turns.append({"role": "patient", "text": text})

            turn_out = await agent.turn(
                TurnInput(
                    patient_utterance=text,
                    available_slots=available_slots_fn(),
                )
            )
            await _speak(turn_out.agent_utterance, tts=tts, audio_out=audio_out)
            await publisher.publish_turn(
                metadata.call_id, role="agent", text=turn_out.agent_utterance
            )
            await publisher.publish_state(metadata.call_id, state=turn_out.next_state.value)
            outcome.turns.append({"role": "agent", "text": turn_out.agent_utterance})

            if turn_out.next_state == ConversationState.FAREWELL:
                outcome.booked_slot = (
                    turn_out.booked_slot.isoformat() if turn_out.booked_slot else None
                )
                break
            if turn_out.next_state == ConversationState.ESCALATED:
                outcome.needs_human = True
                outcome.escalation_reason = turn_out.escalation_reason
                break
    except _PatientDisconnected:
        log.info("voice.call.patient_disconnected", call_id=str(metadata.call_id))
        # If the call was never advanced past GREETING, treat as no_answer
        if agent.state == ConversationState.GREETING:
            outcome.needs_human = False
        else:
            outcome.needs_human = True
            outcome.escalation_reason = "patient_disconnected"

    return outcome


async def _speak(text: str, *, tts: PiperTTS, audio_out: AudioOutput) -> None:
    """Synthesize + push chunks to the audio output."""
    async for chunk in tts.stream(text):
        await audio_out.speak(chunk, sample_rate=tts.sample_rate)


class _PatientDisconnected(Exception):  # noqa: N818 — sentinel, not an error condition
    pass


# ── DB persistence ───────────────────────────────────────────────────


async def mark_in_progress(call_id: UUID) -> None:
    async with async_session_maker() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        call.status = CallStatus.in_progress
        await session.commit()


async def persist_call_end(
    call_id: UUID,
    *,
    outcome: CallOutcome,
    started_at: datetime,
    status: CallStatus,
) -> None:
    """Update the Call row, write the encrypted CallTranscript, and
    flip the OutreachAttempt if a slot was booked. Runs inside a
    fresh session with the tenant ContextVar already set by the
    entrypoint."""
    ended = datetime.now(UTC)
    async with async_session_maker() as session:
        call = await session.get(Call, call_id)
        if call is None:
            log.warning("voice.call.persist.missing_call", call_id=str(call_id))
            return
        call.status = status
        call.ended_at = ended
        call.duration_seconds = max(int((ended - started_at).total_seconds()), 0)
        call.outcome = {
            **(call.outcome or {}),
            "booked_slot": outcome.booked_slot,
            "needs_human": outcome.needs_human,
            "escalation_reason": outcome.escalation_reason,
            "turn_count": len(outcome.turns),
        }

        # Persist transcript: encrypted full text + redacted structured turns.
        transcript_text = "\n".join(f"{t['role']}: {t['text']}" for t in outcome.turns)
        structured = {
            "turns": [
                {"role": t["role"], "char_count": len(t["text"])} for t in outcome.turns
            ],
            "outcome": {
                "booked_slot": outcome.booked_slot,
                "needs_human": outcome.needs_human,
                "escalation_reason": outcome.escalation_reason,
            },
        }
        session.add(
            CallTranscript(
                clinic_id=call.clinic_id,
                call_id=call.id,
                full_transcript=transcript_text,
                structured_data=structured,
            )
        )

        # Update the linked OutreachAttempt — `responded` iff a slot was booked.
        if call.outreach_attempt_id is not None and outcome.booked_slot is not None:
            attempt = (
                await session.execute(
                    select(OutreachAttempt).where(
                        OutreachAttempt.id == call.outreach_attempt_id
                    )
                )
            ).scalar_one_or_none()
            if attempt is not None:
                attempt.status = OutreachStatus.responded
                attempt.outcome = {
                    **(attempt.outcome or {}),
                    "booked_slot": outcome.booked_slot,
                }

        await session.commit()


# ── LiveKit Agents entrypoint ────────────────────────────────────────


def _no_slots() -> list[datetime]:
    """Stub slot supplier. Module 7 wires up the real scheduling lookup."""
    return []


async def entrypoint(ctx: Any) -> None:
    """LiveKit Agents job handler — one invocation per dispatched call.

    `ctx` is an `agents.JobContext`; typed as Any so this module
    imports cleanly in environments that don't have `livekit-agents`
    installed (e.g. the API test venv)."""
    from livekit import rtc  # local import — keeps `livekit-agents` out of the API venv

    metadata = _decode_room_metadata(ctx.room.metadata)

    # Tenant guard — every DB write below is clinic-scoped.
    current_clinic_id.set(metadata.clinic_id)
    current_user_id.set(AGENT_USER_ID)

    settings = get_settings()
    publisher = TranscriptPublisher(redis_url=settings.redis_url)
    agent_obj = EmberAgent(
        llm=get_llm_provider(),
        script_context=metadata.script_context,
    )
    stt = WhisperSTT()
    tts = PiperTTS()

    started = datetime.now(UTC)
    await mark_in_progress(metadata.call_id)
    await ctx.connect()

    audio_source = rtc.AudioSource(tts.sample_rate, 1)
    track = rtc.LocalAudioTrack.create_audio_track("ember-agent", audio_source)
    await ctx.room.local_participant.publish_track(track)

    audio_out = _LiveKitAudioOutput(audio_source)
    audio_in = _LiveKitAudioInput(ctx.room)

    status: CallStatus = CallStatus.completed
    try:
        outcome = await run_call_pipeline(
            metadata,
            agent=agent_obj,
            stt=stt,
            tts=tts,
            audio_in=audio_in,
            audio_out=audio_out,
            publisher=publisher,
            available_slots_fn=_no_slots,
        )
    except Exception as e:
        log.exception("voice.call.pipeline_failed", call_id=str(metadata.call_id), error=str(e))
        outcome = CallOutcome(needs_human=True, escalation_reason="pipeline_error")
        status = CallStatus.failed

    await persist_call_end(metadata.call_id, outcome=outcome, started_at=started, status=status)
    await publisher.publish_end(
        metadata.call_id,
        outcome={
            "booked_slot": outcome.booked_slot,
            "needs_human": outcome.needs_human,
            "escalation_reason": outcome.escalation_reason,
        },
    )
    await publisher.aclose()


def _decode_room_metadata(raw: str | None) -> CallMetadata:
    import json

    if not raw:
        raise ValueError("ember worker requires room.metadata; nothing was attached")
    data = json.loads(raw)
    return CallMetadata(
        call_id=UUID(str(data["call_id"])),
        clinic_id=UUID(str(data["clinic_id"])),
        patient_id=UUID(str(data["patient_id"])),
        script_context=dict(data.get("script_context") or {}),
    )


# ── LiveKit-specific I/O adapters ────────────────────────────────────


class _LiveKitAudioOutput:
    """Push synthesized int16 PCM to a LiveKit AudioSource."""

    def __init__(self, source: rtc.AudioSource) -> None:
        self._source = source

    async def speak(self, pcm16: bytes, *, sample_rate: int) -> None:
        from livekit import rtc

        # Wrap each chunk in an AudioFrame and capture. The LiveKit
        # AudioSource handles buffering + pacing internally.
        frame = rtc.AudioFrame(
            data=pcm16,
            sample_rate=sample_rate,
            num_channels=1,
            samples_per_channel=len(pcm16) // 2,
        )
        await self._source.capture_frame(frame)


class _LiveKitAudioInput:
    """Subscribe to remote participant audio. Yields one bytes payload per
    detected utterance (silence-bracketed). For v1 we use a coarse
    energy-threshold + minimum-duration heuristic; a future iteration
    can swap in Silero VAD."""

    def __init__(
        self,
        room: rtc.Room,
        *,
        silence_threshold: float = 0.01,
        min_utterance_ms: int = 400,
        max_silence_ms: int = 800,
    ) -> None:
        self._room = room
        self._silence_threshold = silence_threshold
        self._min_utterance_ms = min_utterance_ms
        self._max_silence_ms = max_silence_ms
        self._utterance_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._disconnect_event = asyncio.Event()
        self._reader_task: asyncio.Task[None] | None = None
        self._stop = False

        room.on("track_subscribed", self._on_track_subscribed)
        room.on("participant_disconnected", lambda *_a: self._disconnect_event.set())

    def __aiter__(self) -> _LiveKitAudioInput:
        return self

    async def __anext__(self) -> bytes:
        disconnect_task = asyncio.create_task(self._disconnect_event.wait())
        get_task = asyncio.create_task(self._utterance_queue.get())
        done, _pending = await asyncio.wait(
            {disconnect_task, get_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if disconnect_task in done:
            raise _PatientDisconnected()
        # Only get_task can be left in done at this point.
        return get_task.result()

    def _on_track_subscribed(
        self,
        track: rtc.Track,
        _pub: rtc.RemoteTrackPublication,
        _participant: rtc.RemoteParticipant,
    ) -> None:
        from livekit import rtc

        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._read_loop(track))

    async def _read_loop(self, track: rtc.Track) -> None:
        import numpy as np
        from livekit import rtc

        stream = rtc.AudioStream(track)
        buf = bytearray()
        silent_ms = 0
        speaking_ms = 0
        async for evt in stream:
            frame = evt.frame
            samples = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
            ms = int(1000 * frame.samples_per_channel / frame.sample_rate)
            if rms >= self._silence_threshold:
                buf.extend(bytes(frame.data))
                speaking_ms += ms
                silent_ms = 0
            elif speaking_ms > 0:
                buf.extend(bytes(frame.data))
                silent_ms += ms
                if silent_ms >= self._max_silence_ms and speaking_ms >= self._min_utterance_ms:
                    await self._utterance_queue.put(bytes(buf))
                    buf = bytearray()
                    silent_ms = 0
                    speaking_ms = 0
