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
