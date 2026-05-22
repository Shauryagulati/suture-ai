"""EmberAgent state-machine tests.

Pure unit — no LiveKit, no audio, no real LLM. A stub LLMProvider
returns scripted JSON so each transition can be exercised in isolation.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services.llm.base import LLMProvider
from app.services.voice.agent import (
    ConversationFinishedError,
    ConversationState,
    EmberAgent,
    TurnInput,
)

# ── Stub LLM ──────────────────────────────────────────────────────────


@dataclass
class _StubLLM(LLMProvider):
    """Pop scripted JSON responses; record what prompts were seen."""

    responses: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, str]] = field(default_factory=list)
    model: str = "stub"

    async def generate(self, *, system: str, prompt: str, max_tokens: int = 1500) -> str:
        self.calls.append({"system": system, "prompt": prompt})
        if not self.responses:
            raise AssertionError("stub LLM exhausted — test asked for more turns than scripted")
        return json.dumps(self.responses.pop(0))

    async def stream(
        self, *, system: str, prompt: str, max_tokens: int = 500
    ) -> AsyncIterator[str]:
        yield await self.generate(system=system, prompt=prompt, max_tokens=max_tokens)


def _slots() -> list[datetime]:
    base = datetime(2026, 5, 26, 15, 0, tzinfo=UTC)
    return [base, base + timedelta(days=1), base + timedelta(days=2)]


def _ctx() -> dict[str, Any]:
    return {
        "first_name": "Sarah",
        "clinic_name": "Allegheny Cardiology",
        "urgency_label": "routine",
    }


# ── Greeting ──────────────────────────────────────────────────────────


def test_open_uses_patient_name_and_clinic() -> None:
    agent = EmberAgent(llm=_StubLLM(), script_context=_ctx())
    greeting = agent.open()
    assert "Sarah" in greeting
    assert "Allegheny Cardiology" in greeting
    assert agent.state is ConversationState.GREETING


def test_open_falls_back_when_context_missing_name() -> None:
    agent = EmberAgent(llm=_StubLLM(), script_context={"clinic_name": "X Clinic"})
    greeting = agent.open()
    assert "there" in greeting
    assert "X Clinic" in greeting


# ── GREETING → SCHEDULING ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_turn_advances_to_scheduling() -> None:
    llm = _StubLLM(responses=[{"intent": "ask_clarification", "reply": "Sure! Here are some times."}])
    agent = EmberAgent(llm=llm, script_context=_ctx())
    agent.open()
    out = await agent.turn(TurnInput("Yes, go ahead.", _slots()))
    assert out.next_state is ConversationState.SCHEDULING
    assert agent.state is ConversationState.SCHEDULING


# ── SCHEDULING → CONFIRMATION via pick_slot ──────────────────────────


@pytest.mark.asyncio
async def test_pick_slot_advances_to_confirmation_and_records_pending() -> None:
    llm = _StubLLM(
        responses=[
            {"intent": "ask_clarification", "reply": "Here are some times."},
            {
                "intent": "pick_slot",
                "slot_index": 1,
                "reply": "Just to confirm — Wednesday May 27 at 3:00 PM. Does that work?",
            },
        ]
    )
    agent = EmberAgent(llm=llm, script_context=_ctx(), state=ConversationState.SCHEDULING)
    await agent.turn(TurnInput("What's open?", _slots()))  # stay SCHEDULING
    out = await agent.turn(TurnInput("Wednesday afternoon works.", _slots()))

    assert out.next_state is ConversationState.CONFIRMATION
    assert agent.pending_slot == _slots()[1]
    assert out.booked_slot is None  # not booked until confirmed


@pytest.mark.asyncio
async def test_pick_slot_with_bogus_index_stays_in_scheduling() -> None:
    llm = _StubLLM(
        responses=[
            {"intent": "pick_slot", "slot_index": 99, "reply": "Hmm let me try again."}
        ]
    )
    agent = EmberAgent(llm=llm, script_context=_ctx(), state=ConversationState.SCHEDULING)
    out = await agent.turn(TurnInput("uh, some time", _slots()))
    assert out.next_state is ConversationState.SCHEDULING
    assert agent.pending_slot is None


@pytest.mark.asyncio
async def test_ask_clarification_stays_in_scheduling() -> None:
    llm = _StubLLM(
        responses=[{"intent": "ask_clarification", "reply": "Any evenings open?"}]
    )
    agent = EmberAgent(llm=llm, script_context=_ctx(), state=ConversationState.SCHEDULING)
    out = await agent.turn(TurnInput("What about evenings?", _slots()))
    assert out.next_state is ConversationState.SCHEDULING


# ── CONFIRMATION transitions ────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_yes_advances_to_farewell_with_booked_slot() -> None:
    llm = _StubLLM(responses=[{"intent": "confirm_yes", "reply": "Booked. See you then!"}])
    agent = EmberAgent(
        llm=llm,
        script_context=_ctx(),
        state=ConversationState.CONFIRMATION,
        pending_slot=_slots()[0],
    )
    out = await agent.turn(TurnInput("Yes, perfect.", _slots()))
    assert out.next_state is ConversationState.FAREWELL
    assert out.booked_slot == _slots()[0]
    assert out.needs_human is False


@pytest.mark.asyncio
async def test_confirm_no_returns_to_scheduling_and_clears_pending() -> None:
    llm = _StubLLM(
        responses=[{"intent": "confirm_no", "reply": "No problem. Want a different time?"}]
    )
    agent = EmberAgent(
        llm=llm,
        script_context=_ctx(),
        state=ConversationState.CONFIRMATION,
        pending_slot=_slots()[0],
    )
    out = await agent.turn(TurnInput("Actually no.", _slots()))
    assert out.next_state is ConversationState.SCHEDULING
    assert agent.pending_slot is None
    assert out.booked_slot is None


# ── Guardrail short-circuits ────────────────────────────────────────


@pytest.mark.asyncio
async def test_medical_advice_question_escalates_without_calling_llm() -> None:
    llm = _StubLLM()  # no scripted responses — LLM must not be called
    agent = EmberAgent(llm=llm, script_context=_ctx(), state=ConversationState.SCHEDULING)
    out = await agent.turn(TurnInput("Should I stop my beta blocker?", _slots()))
    assert out.next_state is ConversationState.ESCALATED
    assert out.needs_human is True
    assert out.escalation_reason == "medical_advice"
    assert llm.calls == []


@pytest.mark.asyncio
async def test_emergency_keyword_escalates_with_911_script() -> None:
    llm = _StubLLM()
    agent = EmberAgent(llm=llm, script_context=_ctx(), state=ConversationState.SCHEDULING)
    out = await agent.turn(TurnInput("I'm having chest pain right now.", _slots()))
    assert out.next_state is ConversationState.ESCALATED
    assert "911" in out.agent_utterance
    assert llm.calls == []


@pytest.mark.asyncio
async def test_off_topic_in_scheduling_escalates() -> None:
    llm = _StubLLM(
        responses=[{"intent": "off_topic", "reply": "I can't help with that."}]
    )
    agent = EmberAgent(llm=llm, script_context=_ctx(), state=ConversationState.SCHEDULING)
    out = await agent.turn(TurnInput("Tell me about cardiology fellowships.", _slots()))
    assert out.next_state is ConversationState.ESCALATED
    assert out.needs_human is True


# ── Terminal-state safety ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_turn_after_farewell_raises() -> None:
    agent = EmberAgent(llm=_StubLLM(), script_context=_ctx(), state=ConversationState.FAREWELL)
    with pytest.raises(ConversationFinishedError):
        await agent.turn(TurnInput("Hi?", _slots()))


@pytest.mark.asyncio
async def test_turn_after_escalated_raises() -> None:
    agent = EmberAgent(
        llm=_StubLLM(), script_context=_ctx(), state=ConversationState.ESCALATED
    )
    with pytest.raises(ConversationFinishedError):
        await agent.turn(TurnInput("Hi?", _slots()))


# ── LLM parse-failure resilience ─────────────────────────────────────


@pytest.mark.asyncio
async def test_garbled_llm_response_treated_as_offtopic_and_escalates() -> None:
    """JSONExtractionError from the LLM → fallback to off_topic, which escalates from SCHEDULING."""

    @dataclass
    class _BrokenLLM(LLMProvider):
        model: str = "broken"

        async def generate(self, *, system: str, prompt: str, max_tokens: int = 1500) -> str:
            return "not json at all"

        async def stream(
            self, *, system: str, prompt: str, max_tokens: int = 500
        ) -> AsyncIterator[str]:
            yield "not json"

    agent = EmberAgent(
        llm=_BrokenLLM(), script_context=_ctx(), state=ConversationState.SCHEDULING
    )
    out = await agent.turn(TurnInput("what times do you have?", _slots()))
    assert out.next_state is ConversationState.ESCALATED
    assert out.needs_human is True
