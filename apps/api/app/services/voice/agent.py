"""EmberAgent — voice agent conversation state machine.

Pure Python: no LiveKit, no audio I/O. Owns the conversation state
machine that drives a single patient call, and the LLM-mediated intent
classification + reply generation.

Wired into the LiveKit worker (`services/voice-agent/`) at Module 6.
Tested standalone with a stub LLMProvider.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.llm.base import JSONExtractionError, LLMProvider
from app.services.voice.guardrails import GuardrailKind, Guardrails, GuardrailVerdict

# agent.py → voice → services → app → api → apps → repo_root
_REPO_ROOT = Path(__file__).resolve().parents[5]
_PROMPT_PATH = _REPO_ROOT / "ai" / "prompts" / "voice" / "scheduling_v1.md"


def load_scheduling_prompt() -> str:
    """Load the versioned scheduling system prompt from disk."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


class ConversationState(enum.StrEnum):
    GREETING = "greeting"
    SCHEDULING = "scheduling"
    CONFIRMATION = "confirmation"
    FAREWELL = "farewell"
    ESCALATED = "escalated"


class ConversationFinishedError(RuntimeError):
    """Raised when turn() is called after the conversation reached a terminal state."""


@dataclass
class TurnInput:
    patient_utterance: str
    available_slots: Sequence[datetime]


@dataclass
class TurnOutput:
    agent_utterance: str
    next_state: ConversationState
    booked_slot: datetime | None = None
    needs_human: bool = False
    escalation_reason: str | None = None  # GuardrailKind value when escalated


def _fmt_slot(slot: datetime) -> str:
    """Human-friendly slot phrasing, e.g. 'Tuesday May 26 at 3:00 PM'."""
    return slot.strftime("%A %B %-d at %-I:%M %p")


def _format_slot_block(slots: Sequence[datetime], limit: int = 3) -> str:
    if not slots:
        return "(no available slots)"
    return "\n".join(f"  [{i}] {_fmt_slot(s)}" for i, s in enumerate(slots[:limit]))


@dataclass
class EmberAgent:
    """One agent instance per call. Drives one patient ↔ agent dialogue."""

    llm: LLMProvider
    script_context: dict[str, Any]
    guardrails: Guardrails = field(default_factory=Guardrails)
    state: ConversationState = ConversationState.GREETING
    pending_slot: datetime | None = None
    _system_prompt: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self._system_prompt = load_scheduling_prompt()

    # ── Public API ────────────────────────────────────────────────

    def open(self) -> str:
        """Return the opening greeting. Synchronous — no LLM call."""
        first_name = self.script_context.get("first_name", "there")
        clinic_name = self.script_context.get("clinic_name", "the clinic")
        self.state = ConversationState.GREETING
        return (
            f"Hi {first_name}, this is Ember calling from {clinic_name} "
            f"about your follow-up appointment. Do you have a quick moment?"
        )

    async def turn(self, turn_input: TurnInput) -> TurnOutput:
        """Drive one patient → agent turn. Updates `self.state`."""
        if self.state in (ConversationState.FAREWELL, ConversationState.ESCALATED):
            raise ConversationFinishedError(
                f"turn() called after terminal state {self.state.value!r}"
            )

        # 1. Guardrails — pre-LLM. Tripped utterances bypass the model
        #    and route straight to escalation.
        verdict = self.guardrails.evaluate(turn_input.patient_utterance)
        if verdict is not None:
            return self._escalate(verdict)

        # 2. Classify intent + draft reply via the LLM.
        parsed = await self._classify_and_reply(turn_input)
        intent = parsed.get("intent", "off_topic")
        reply = str(parsed.get("reply", "")).strip() or self._fallback_reply()

        # 3. Apply state transition.
        return self._transition(intent, parsed, reply, turn_input.available_slots)

    # ── LLM call ──────────────────────────────────────────────────

    async def _classify_and_reply(self, turn_input: TurnInput) -> dict[str, Any]:
        user_prompt = (
            f"CURRENT_STATE: {self.state.value}\n"
            f"PATIENT_FIRST_NAME: {self.script_context.get('first_name', '')}\n"
            f"CLINIC_NAME: {self.script_context.get('clinic_name', '')}\n"
            f"URGENCY: {self.script_context.get('urgency_label', 'routine')}\n"
            f"PROPOSED_SLOT_AWAITING_CONFIRMATION: "
            f"{_fmt_slot(self.pending_slot) if self.pending_slot else 'none'}\n"
            f"AVAILABLE_SLOTS:\n{_format_slot_block(turn_input.available_slots)}\n\n"
            f'PATIENT_UTTERANCE: "{turn_input.patient_utterance}"\n\n'
            f"Respond with the JSON object described in the system prompt."
        )
        try:
            return await self.llm.extract_json(
                system=self._system_prompt,
                prompt=user_prompt,
                max_tokens=400,
            )
        except JSONExtractionError:
            # Treat parse failure as off-topic — escalate gracefully.
            return {"intent": "off_topic", "reply": self._fallback_reply()}

    # ── State transitions ────────────────────────────────────────

    def _transition(
        self,
        intent: str,
        parsed: dict[str, Any],
        reply: str,
        available_slots: Sequence[datetime],
    ) -> TurnOutput:
        if self.state == ConversationState.GREETING:
            self.state = ConversationState.SCHEDULING
            return TurnOutput(agent_utterance=reply, next_state=self.state)

        if self.state == ConversationState.SCHEDULING:
            if intent == "pick_slot":
                slot_idx = parsed.get("slot_index")
                if isinstance(slot_idx, int) and 0 <= slot_idx < len(available_slots):
                    self.pending_slot = available_slots[slot_idx]
                    self.state = ConversationState.CONFIRMATION
                    return TurnOutput(agent_utterance=reply, next_state=self.state)
                # Bogus index — fall through as a clarification.
            if intent == "off_topic":
                return self._escalate_offtopic()
            # ask_clarification or unhandled → stay in SCHEDULING.
            return TurnOutput(agent_utterance=reply, next_state=self.state)

        if self.state == ConversationState.CONFIRMATION:
            if intent == "confirm_yes":
                booked = self.pending_slot
                self.state = ConversationState.FAREWELL
                return TurnOutput(
                    agent_utterance=reply,
                    next_state=self.state,
                    booked_slot=booked,
                )
            if intent == "confirm_no":
                self.pending_slot = None
                self.state = ConversationState.SCHEDULING
                return TurnOutput(agent_utterance=reply, next_state=self.state)
            if intent == "off_topic":
                return self._escalate_offtopic()
            # Anything ambiguous — re-ask in CONFIRMATION.
            return TurnOutput(agent_utterance=reply, next_state=self.state)

        # Defensive default — should never reach here.
        return TurnOutput(agent_utterance=reply, next_state=self.state)

    def _escalate(self, verdict: GuardrailVerdict) -> TurnOutput:
        self.state = ConversationState.ESCALATED
        return TurnOutput(
            agent_utterance=verdict.canned_reply,
            next_state=self.state,
            needs_human=True,
            escalation_reason=verdict.kind.value,
        )

    def _escalate_offtopic(self) -> TurnOutput:
        self.state = ConversationState.ESCALATED
        return TurnOutput(
            agent_utterance=(
                "Let me have someone from the clinic call you back to help "
                "find a time that works."
            ),
            next_state=self.state,
            needs_human=True,
            escalation_reason=GuardrailKind.OUT_OF_SCOPE.value,
        )

    @staticmethod
    def _fallback_reply() -> str:
        return "Sorry, I didn't catch that. Could you say it again?"
