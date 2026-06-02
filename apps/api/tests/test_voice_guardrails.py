"""Guardrails tests for the voice agent.

Conservative-bias here: any pattern miss is a HIPAA-class issue
because Ember might give medical advice. Each rail has positive +
negative cases.
"""

from __future__ import annotations

import pytest

from app.services.voice.guardrails import GuardrailKind, Guardrails


@pytest.fixture
def rails() -> Guardrails:
    return Guardrails()


# ── Emergency ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "utterance",
    [
        "I'm having chest pain right now.",
        "I can't breathe properly.",
        "I think I'm having a heart attack.",
        "I'm having stroke symptoms.",
        "He's bleeding heavily — should we call 911?",
        "This feels like an emergency.",
    ],
)
def test_emergency_phrases_trip_emergency(rails: Guardrails, utterance: str) -> None:
    verdict = rails.evaluate(utterance)
    assert verdict is not None
    assert verdict.kind is GuardrailKind.EMERGENCY
    assert "911" in verdict.canned_reply


# ── Medical advice ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "utterance",
    [
        "Should I stop my beta blocker?",
        "Can I take an extra dose tonight?",
        "Is it safe to skip my statin?",
        "What's the right dosage for me?",
        "What are the side effects of metoprolol?",
        "What does my ejection fraction mean?",
        "Can I adjust my warfarin if I forget a dose?",
    ],
)
def test_medical_advice_questions_trip_medical_advice(rails: Guardrails, utterance: str) -> None:
    verdict = rails.evaluate(utterance)
    assert verdict is not None
    assert verdict.kind is GuardrailKind.MEDICAL_ADVICE
    assert "medical advice" in verdict.canned_reply.lower()


# ── Out of scope ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "utterance",
    [
        "I want to dispute my billing.",
        "Can I get a prescription refill?",
        "I need to transfer my records.",
        "Can I speak to a person?",
        "I'd like to talk to a nurse.",
    ],
)
def test_out_of_scope_topics_trip_out_of_scope(rails: Guardrails, utterance: str) -> None:
    verdict = rails.evaluate(utterance)
    assert verdict is not None
    assert verdict.kind is GuardrailKind.OUT_OF_SCOPE


# ── Negative cases (scheduling intent must pass through cleanly) ──────


@pytest.mark.parametrize(
    "utterance",
    [
        "I'd like Tuesday at 3 pm.",
        "Yes, that time works for me.",
        "No, I can't make that day.",
        "Can you offer me an evening slot?",
        "I'm free on Wednesday morning.",
        "What times do you have?",
        "Sorry, repeat that?",
        "Sounds good, let's book it.",
    ],
)
def test_scheduling_intent_passes_through(rails: Guardrails, utterance: str) -> None:
    assert rails.evaluate(utterance) is None


def test_empty_or_whitespace_does_not_trip(rails: Guardrails) -> None:
    assert rails.evaluate("") is None
    assert rails.evaluate("   \n  ") is None


def test_emergency_outranks_medical_advice(rails: Guardrails) -> None:
    """A single utterance hitting both rails must surface the emergency rail first."""
    verdict = rails.evaluate("Should I take more nitro? I'm having chest pain.")
    assert verdict is not None
    assert verdict.kind is GuardrailKind.EMERGENCY
