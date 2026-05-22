"""Pre-LLM safety filters for the Ember voice agent.

Every patient utterance is evaluated here BEFORE the LLM sees it. The
goal is to prevent Ember from giving any medical advice and to ensure
suspected emergencies route to 911 / clinic staff immediately.

Patterns are deliberately conservative — false positives (over-escalate
a benign question) are fine; false negatives (let a medical question
through) are not. Pattern lists are frozensets so adding/removing
phrases is O(1) and easy to audit.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass


class GuardrailKind(enum.StrEnum):
    EMERGENCY = "emergency"
    MEDICAL_ADVICE = "medical_advice"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True)
class GuardrailVerdict:
    kind: GuardrailKind
    canned_reply: str


# Emergency phrases → immediate 911 redirect. Match as case-insensitive
# substrings; word boundaries are not used because phrases like "chest
# pain" are unambiguous enough.
_EMERGENCY_PHRASES: frozenset[str] = frozenset(
    {
        "chest pain",
        "can't breathe",
        "cant breathe",
        "stop breathing",
        "trouble breathing",
        "shortness of breath",
        "passing out",
        "fainted",
        "having a heart attack",
        "having a stroke",
        "stroke symptoms",
        "call 911",
        "emergency",
        "bleeding heavily",
        "severe pain",
    }
)

_EMERGENCY_REPLY = (
    "I'm sorry, but if this is a medical emergency please hang up and dial "
    "911 right now. If you're not in immediate danger, please call our "
    "clinic's after-hours line and someone will help you."
)

# Medical-advice triggers. These are *intent* markers, not symptom names —
# patients may volunteer symptoms (which the agent should not respond to
# substantively); the guardrail catches the moment they ASK for advice.
_MEDICAL_ADVICE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bshould i\b", re.IGNORECASE),
    re.compile(r"\bcan i\b.*\b(take|stop|skip|increase|decrease|adjust)\b", re.IGNORECASE),
    re.compile(
        r"\bis it (safe|okay|ok|alright) (to|for me)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bdosage\b", re.IGNORECASE),
    re.compile(r"\bside effects?\b", re.IGNORECASE),
    re.compile(r"\bwhat (does|do).*\b(mean|indicate|signify)\b", re.IGNORECASE),
    re.compile(
        r"\b(stop|skip|change|increase|decrease|adjust)\b.*\b"
        r"(medication|medicine|prescription|dose|pill|drug|beta.?blocker|"
        r"statin|warfarin|coumadin|metoprolol|lisinopril)\b",
        re.IGNORECASE,
    ),
)

_MEDICAL_ADVICE_REPLY = (
    "I'm not able to give medical advice — let me get you to someone who "
    "can. I'll have a member of our clinical team call you back shortly. "
    "If this is urgent, please call the clinic directly."
)

# Out-of-scope topics: billing, insurance disputes, prescription refills,
# medical records, anything that isn't appointment scheduling.
_OUT_OF_SCOPE_PHRASES: frozenset[str] = frozenset(
    {
        "billing",
        "bill",
        "invoice",
        "insurance claim",
        "insurance dispute",
        "prescription refill",
        "refill my prescription",
        "medical records",
        "release of records",
        "transfer my records",
        "talk to a nurse",
        "talk to the doctor",
        "talk to my doctor",
        "speak to a person",
    }
)

_OUT_OF_SCOPE_REPLY = (
    "That's something our front desk handles — let me transfer you. One "
    "moment please."
)


class Guardrails:
    """Stateless evaluator. Cheap to construct; tests use a fresh instance."""

    def evaluate(self, utterance: str) -> GuardrailVerdict | None:
        """Return a verdict if the utterance trips a rail; None otherwise."""
        if not utterance or not utterance.strip():
            return None
        normalized = utterance.lower().strip()

        for phrase in _EMERGENCY_PHRASES:
            if phrase in normalized:
                return GuardrailVerdict(GuardrailKind.EMERGENCY, _EMERGENCY_REPLY)

        for pattern in _MEDICAL_ADVICE_PATTERNS:
            if pattern.search(utterance):
                return GuardrailVerdict(GuardrailKind.MEDICAL_ADVICE, _MEDICAL_ADVICE_REPLY)

        for phrase in _OUT_OF_SCOPE_PHRASES:
            if phrase in normalized:
                return GuardrailVerdict(GuardrailKind.OUT_OF_SCOPE, _OUT_OF_SCOPE_REPLY)

        return None
