"""Per-urgency message templates for SMS / email / voice greeting."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.discharge_summary import UrgencyTier
from app.models.document import UrgencyLevel

# Urgency labels are patient-friendly (no clinical terms).
URGENCY_LABEL: dict[UrgencyTier | UrgencyLevel, str] = {
    UrgencyTier.critical: "urgent",
    UrgencyLevel.stat: "urgent",
    UrgencyTier.high: "soon",
    UrgencyLevel.urgent: "soon",
    UrgencyTier.medium: "follow-up",
    UrgencyTier.routine: "routine",
    UrgencyLevel.routine: "routine",
    UrgencyLevel.unclassified: "follow-up",
}


def urgency_label(urgency: UrgencyTier | UrgencyLevel) -> str:
    """Patient-friendly urgency label. Raises ValueError for unknown enums."""
    if urgency not in URGENCY_LABEL:
        raise ValueError(f"unknown urgency: {urgency!r}")
    return URGENCY_LABEL[urgency]


# Adjective form of each urgency label for composing "<adj> cardiology
# follow-up". Two labels are not usable as adjectives: "follow-up" IS the
# noun (composing it doubled to "follow-up cardiology follow-up") and
# "soon" is an adverb ("a soon follow-up" is broken English).
_URGENCY_ADJECTIVE: dict[str, str] = {
    "urgent": "urgent",
    "soon": "time-sensitive",
    "routine": "routine",
    "follow-up": "",
}


def _follow_up_phrase(label: str, *, with_article: bool = False) -> str:
    """Noun phrase for the follow-up, e.g. 'urgent cardiology follow-up'
    or plain 'cardiology follow-up', optionally with a correct article."""
    adjective = _URGENCY_ADJECTIVE.get(label, "")
    phrase = f"{adjective} cardiology follow-up" if adjective else "cardiology follow-up"
    if not with_article:
        return phrase
    article = "an" if phrase[0] in "aeiou" else "a"
    return f"{article} {phrase}"


@dataclass
class RenderedMessage:
    body: str
    subject: str | None = None


def render_sms(
    *,
    patient_first_name: str,
    scheduling_link_url: str,
    urgency: UrgencyTier | UrgencyLevel,
) -> RenderedMessage:
    label = urgency_label(urgency)
    return RenderedMessage(
        body=(
            f"Hi {patient_first_name}, this is your cardiology clinic. "
            f"Please schedule your {_follow_up_phrase(label)} here: {scheduling_link_url} "
            "Reply STOP to opt out."
        )
    )


def render_email(
    *,
    patient_first_name: str,
    scheduling_link_url: str,
    urgency: UrgencyTier | UrgencyLevel,
    clinic_name: str,
) -> RenderedMessage:
    label = urgency_label(urgency)
    return RenderedMessage(
        subject=f"Schedule your {_follow_up_phrase(label)} with {clinic_name}",
        body=(
            f"Hi {patient_first_name},\n\n"
            f"Your provider has requested {_follow_up_phrase(label, with_article=True)}.\n\n"
            f"Pick a time that works for you: {scheduling_link_url}\n\n"
            f"Thank you,\n{clinic_name}"
        ),
    )


def render_voice_script_context(
    *,
    patient_first_name: str,
    urgency: UrgencyTier | UrgencyLevel,
    clinic_name: str,
) -> dict[str, str]:
    """Context dict consumed by the voice agent (Module 6) to drive
    LiveKit + Claude Haiku dialogue. v1 stores it in Call.outcome and
    OutreachAttempt.metadata so the agent can pick it up later."""
    label = urgency_label(urgency)
    return {
        "first_name": patient_first_name,
        "urgency_label": label,
        "clinic_name": clinic_name,
        "greeting": (
            f"Hello, this is {clinic_name} calling for {patient_first_name}. "
            f"We need to schedule {_follow_up_phrase(label, with_article=True)}."
        ),
    }
