"""Defense-in-depth: OutreachAttemptResponse must never serialize token keys.

Even if some upstream path persisted a token into outcome, the response
schema strips any ``*_token`` key before it reaches a client.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.models.outreach_attempt import OutreachAttempt, OutreachChannel, OutreachStatus
from app.schemas.outreach import OutreachAttemptResponse


def _attempt(outcome: dict) -> OutreachAttempt:
    now = datetime.now(UTC)
    a = OutreachAttempt(
        id=uuid4(),
        patient_id=uuid4(),
        channel=OutreachChannel.voice,
        status=OutreachStatus.sent,
        scheduled_at=now,
        sent_at=now,
        attempt_number=1,
        outcome=outcome,
    )
    a.created_at = now
    a.updated_at = now
    return a


def test_response_strips_tokens_from_provider_raw() -> None:
    resp = OutreachAttemptResponse.from_model(
        _attempt(
            {
                "delivered": True,
                "call_id": "c-1",
                "provider_raw": {
                    "room_name": "r-1",
                    "agent_token": "AAA",
                    "patient_token": "BBB",
                },
            }
        )
    )
    pr = resp.outcome["provider_raw"]
    assert pr == {"room_name": "r-1"}
    assert "agent_token" not in pr
    assert "patient_token" not in pr


def test_response_strips_top_level_token_keys() -> None:
    resp = OutreachAttemptResponse.from_model(_attempt({"some_token": "leak", "call_id": "c-2"}))
    assert "some_token" not in resp.outcome
    assert resp.outcome["call_id"] == "c-2"
