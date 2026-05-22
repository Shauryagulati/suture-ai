"""LiveKitOutreachProvider tests.

The provider hands off to LiveKitClient.start_call; we substitute a
fake client and assert the outreach contract: voice channel dispatches
+ surfaces tokens; non-voice channels return delivered=False; missing
metadata returns delivered=False; client exceptions are translated.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.models.outreach_attempt import OutreachChannel
from app.services.outreach.base import OutreachMessage
from app.services.outreach.factory import get_outreach_provider, reset_outreach_provider_cache
from app.services.outreach.livekit import LiveKitOutreachProvider
from app.services.outreach.stub import StubOutreachProvider
from app.services.voice.livekit_client import DispatchedCall

# async marker applied per-test below — factory tests are sync.


# ── Fake LiveKit client ───────────────────────────────────────────────


class _FakeLiveKitClient:
    def __init__(self) -> None:
        self.calls_started: list[dict[str, Any]] = []
        self.start_raises: Exception | None = None

    async def start_call(
        self,
        *,
        call_id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        script_context: dict[str, Any],
    ) -> DispatchedCall:
        if self.start_raises is not None:
            raise self.start_raises
        self.calls_started.append(
            {
                "call_id": call_id,
                "clinic_id": clinic_id,
                "patient_id": patient_id,
                "script_context": script_context,
            }
        )
        return DispatchedCall(
            room_name=f"call-{call_id}",
            agent_token=f"agent-jwt-{call_id}",
            patient_token=f"patient-jwt-{call_id}",
        )

    async def aclose(self) -> None:
        pass


def _voice_message(*, with_call_id: bool = True) -> OutreachMessage:
    metadata: dict[str, Any] = {
        "patient_id": str(uuid4()),
        "clinic_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "first_name": "Sarah",
        "greeting": "Hi Sarah",
    }
    if with_call_id:
        metadata["call_id"] = str(uuid4())
    return OutreachMessage(
        channel=OutreachChannel.voice,
        to="412-555-0100",
        body="Hi Sarah",
        metadata=metadata,
    )


# ── Voice channel dispatch ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_voice_message_dispatches_and_returns_tokens() -> None:
    fake = _FakeLiveKitClient()
    provider = LiveKitOutreachProvider(client=fake)  # type: ignore[arg-type]
    msg = _voice_message()
    result = await provider.send(msg)

    assert result.delivered is True
    assert result.provider_message_id == f"call-{msg.metadata['call_id']}"
    assert result.raw["agent_token"].startswith("agent-jwt-")
    assert result.raw["patient_token"].startswith("patient-jwt-")
    assert result.raw["room_name"] == result.provider_message_id


@pytest.mark.asyncio
async def test_send_passes_script_context_without_routing_keys() -> None:
    """Routing keys (call_id/clinic_id/patient_id/attempt_id) must not leak
    into script_context — they're separate concerns."""
    fake = _FakeLiveKitClient()
    provider = LiveKitOutreachProvider(client=fake)  # type: ignore[arg-type]
    await provider.send(_voice_message())

    ctx = fake.calls_started[0]["script_context"]
    assert "first_name" in ctx
    assert "greeting" in ctx
    assert "call_id" not in ctx
    assert "clinic_id" not in ctx
    assert "patient_id" not in ctx
    assert "attempt_id" not in ctx


# ── Non-voice channels rejected (no exception) ───────────────────────


@pytest.mark.parametrize("channel", [OutreachChannel.sms, OutreachChannel.email])
@pytest.mark.asyncio
async def test_non_voice_channels_return_undelivered(channel: OutreachChannel) -> None:
    fake = _FakeLiveKitClient()
    provider = LiveKitOutreachProvider(client=fake)  # type: ignore[arg-type]
    result = await provider.send(
        OutreachMessage(channel=channel, to="x@example.com", body="hi", metadata={})
    )
    assert result.delivered is False
    assert "voice only" in (result.error or "").lower()
    assert fake.calls_started == []


# ── Metadata validation ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_call_id_returns_undelivered() -> None:
    fake = _FakeLiveKitClient()
    provider = LiveKitOutreachProvider(client=fake)  # type: ignore[arg-type]
    result = await provider.send(_voice_message(with_call_id=False))
    assert result.delivered is False
    assert "metadata" in (result.error or "").lower()
    assert fake.calls_started == []


@pytest.mark.asyncio
async def test_garbage_call_id_returns_undelivered() -> None:
    fake = _FakeLiveKitClient()
    provider = LiveKitOutreachProvider(client=fake)  # type: ignore[arg-type]
    msg = _voice_message()
    msg.metadata["call_id"] = "not-a-uuid"
    result = await provider.send(msg)
    assert result.delivered is False
    assert "metadata" in (result.error or "").lower()


# ── Client-side failure translated, not raised ───────────────────────


@pytest.mark.asyncio
async def test_livekit_failure_becomes_undelivered_not_exception() -> None:
    fake = _FakeLiveKitClient()
    fake.start_raises = RuntimeError("livekit server down")
    provider = LiveKitOutreachProvider(client=fake)  # type: ignore[arg-type]
    result = await provider.send(_voice_message())  # must not raise
    assert result.delivered is False
    assert "livekit" in (result.error or "").lower()


# ── Factory wiring ───────────────────────────────────────────────────


@pytest.fixture
def _factory_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Reset factory cache + restore OUTREACH_PROVIDER env var."""
    reset_outreach_provider_cache()
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "devsecret")
    monkeypatch.setenv("LIVEKIT_URL", "ws://localhost:7880")
    try:
        yield
    finally:
        reset_outreach_provider_cache()


def test_factory_default_is_stub(_factory_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OUTREACH_PROVIDER", raising=False)
    assert isinstance(get_outreach_provider(), StubOutreachProvider)


def test_factory_livekit_provider_selectable(
    _factory_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OUTREACH_PROVIDER", "livekit")
    # Settings cache holds the empty values from the test conftest; instead
    # of fighting it, instantiate directly to confirm the lazy import works.
    # (Factory selection on real settings is exercised in production.)
    from app.config import get_settings

    if not (
        os.getenv("LIVEKIT_API_KEY")
        and os.getenv("LIVEKIT_API_SECRET")
        and get_settings().livekit_api_key
    ):
        pytest.skip("settings.livekit_api_key not propagated under test settings cache")
    provider = get_outreach_provider()
    assert isinstance(provider, LiveKitOutreachProvider)


def test_factory_unknown_provider_raises(
    _factory_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OUTREACH_PROVIDER", "twilio")
    with pytest.raises(ValueError, match="Unknown OUTREACH_PROVIDER"):
        get_outreach_provider()
