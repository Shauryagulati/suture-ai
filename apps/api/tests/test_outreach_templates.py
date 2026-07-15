"""Pure-function tests for message template renderers."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

from app.models.discharge_summary import UrgencyTier  # noqa: E402
from app.models.document import UrgencyLevel  # noqa: E402
from app.services.outreach.templates import (  # noqa: E402
    render_email,
    render_sms,
    render_voice_script_context,
    urgency_label,
)


async def test_urgency_label_critical_is_patient_friendly_urgent() -> None:
    assert urgency_label(UrgencyTier.critical) == "urgent"
    assert urgency_label(UrgencyLevel.stat) == "urgent"


async def test_urgency_label_high_is_soon() -> None:
    assert urgency_label(UrgencyTier.high) == "soon"
    assert urgency_label(UrgencyLevel.urgent) == "soon"


async def test_urgency_label_routine_is_routine() -> None:
    assert urgency_label(UrgencyTier.routine) == "routine"
    assert urgency_label(UrgencyLevel.routine) == "routine"


async def test_urgency_label_unclassified_is_followup() -> None:
    assert urgency_label(UrgencyLevel.unclassified) == "follow-up"


async def test_urgency_label_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown urgency"):
        urgency_label("garbage")  # type: ignore[arg-type]


async def test_render_sms_includes_name_link_and_opt_out() -> None:
    msg = render_sms(
        patient_first_name="Pat",
        scheduling_link_url="https://app/schedule/abc",
        urgency=UrgencyLevel.routine,
    )
    assert msg.subject is None
    assert "Pat" in msg.body
    assert "https://app/schedule/abc" in msg.body
    assert "STOP" in msg.body
    assert "routine" in msg.body


async def test_render_sms_critical_says_urgent() -> None:
    msg = render_sms(
        patient_first_name="Pat",
        scheduling_link_url="https://app/schedule/abc",
        urgency=UrgencyTier.critical,
    )
    assert "urgent" in msg.body


async def test_render_email_includes_subject_and_clinic_name() -> None:
    msg = render_email(
        patient_first_name="Pat",
        scheduling_link_url="https://app/schedule/abc",
        urgency=UrgencyLevel.routine,
        clinic_name="Steel City Cardiology",
    )
    assert msg.subject is not None
    assert "Steel City Cardiology" in msg.subject
    assert "Steel City Cardiology" in msg.body
    assert "Pat" in msg.body
    assert "https://app/schedule/abc" in msg.body


async def test_render_voice_script_context_carries_greeting() -> None:
    ctx = render_voice_script_context(
        patient_first_name="Pat",
        urgency=UrgencyLevel.urgent,
        clinic_name="Steel City Cardiology",
    )
    assert ctx["first_name"] == "Pat"
    assert ctx["urgency_label"] == "soon"
    assert ctx["clinic_name"] == "Steel City Cardiology"
    assert "Pat" in ctx["greeting"]
    assert "Steel City Cardiology" in ctx["greeting"]


async def test_templates_never_double_the_follow_up_label() -> None:
    """Regression: the 'follow-up' urgency label composed as
    'a follow-up cardiology follow-up' across SMS, email, and voice."""
    ctx = render_voice_script_context(
        patient_first_name="Amy",
        urgency=UrgencyLevel.unclassified,  # label == "follow-up"
        clinic_name="Steel City Cardiology",
    )
    assert "follow-up cardiology follow-up" not in ctx["greeting"]
    assert "follow-up follow-up" not in ctx["greeting"]

    email = render_email(
        patient_first_name="Amy",
        scheduling_link_url="https://app/schedule/abc",
        urgency=UrgencyLevel.unclassified,
        clinic_name="Steel City Cardiology",
    )
    assert "follow-up follow-up" not in (email.subject or "")
    assert "follow-up cardiology follow-up" not in email.body

    sms = render_sms(
        patient_first_name="Amy",
        scheduling_link_url="https://app/schedule/abc",
        urgency=UrgencyLevel.unclassified,
    )
    assert "follow-up follow-up" not in sms.body


async def test_voice_greeting_is_grammatical() -> None:
    """Regression: greeting opened 'Hello, this is calling from X for Amy.'"""
    ctx = render_voice_script_context(
        patient_first_name="Amy",
        urgency=UrgencyLevel.stat,  # label == "urgent"
        clinic_name="Steel City Cardiology",
    )
    assert "this is calling from" not in ctx["greeting"]
    assert "this is Steel City Cardiology calling" in ctx["greeting"]
    assert "an urgent cardiology follow-up" in ctx["greeting"]


async def test_soon_label_reads_naturally_in_email() -> None:
    """'soon' is not an adjective — 'a soon cardiology follow-up' is broken."""
    email = render_email(
        patient_first_name="Amy",
        scheduling_link_url="https://app/schedule/abc",
        urgency=UrgencyLevel.urgent,  # label == "soon"
        clinic_name="Steel City Cardiology",
    )
    assert "a soon " not in email.body
    assert " soon follow-up" not in email.body
