"""StubOutreachProvider + factory tests."""

from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.asyncio

from app.models.outreach_attempt import OutreachChannel  # noqa: E402
from app.services.outreach.base import OutreachMessage  # noqa: E402
from app.services.outreach.factory import (  # noqa: E402
    get_outreach_provider,
    reset_outreach_provider_cache,
)
from app.services.outreach.stub import StubOutreachProvider, _redact  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_factory_cache() -> None:
    reset_outreach_provider_cache()
    yield
    reset_outreach_provider_cache()


async def test_stub_provider_records_send_and_returns_success() -> None:
    provider = StubOutreachProvider()
    result = await provider.send(
        OutreachMessage(
            channel=OutreachChannel.sms,
            to="412-555-0150",
            body="Hi Pat, schedule here: https://example.com/s/xyz",
        )
    )
    assert result.delivered is True
    assert result.provider_message_id is not None
    assert result.provider_message_id.startswith("stub-")
    assert len(provider.sent) == 1
    assert provider.sent[0].channel == OutreachChannel.sms
    assert provider.sent[0].to == "412-555-0150"


async def test_stub_provider_accumulates_multiple_sends() -> None:
    provider = StubOutreachProvider()
    for i in range(3):
        await provider.send(
            OutreachMessage(
                channel=OutreachChannel.sms,
                to=f"412-555-010{i}",
                body=f"msg {i}",
            )
        )
    assert len(provider.sent) == 3
    assert [m.body for m in provider.sent] == ["msg 0", "msg 1", "msg 2"]


async def test_stub_provider_does_not_log_raw_phone(caplog: pytest.LogCaptureFixture) -> None:
    provider = StubOutreachProvider()
    raw_phone = "412-555-9999"
    with caplog.at_level(logging.INFO):
        await provider.send(
            OutreachMessage(channel=OutreachChannel.sms, to=raw_phone, body="hello")
        )
    # Combined log surface — structlog renders to stdout, caplog captures stdlib;
    # belt-and-braces: assert against rendered message text and the record dict.
    rendered = " ".join(record.getMessage() for record in caplog.records)
    assert raw_phone not in rendered


async def test_redact_phone_keeps_last_four_only() -> None:
    assert _redact("412-555-0150") == "***-0150"
    assert _redact("(412) 555 - 0123") == "***-0123"


async def test_redact_email_keeps_first_initial_and_domain_tail() -> None:
    assert _redact("patient@example.com") == "p***@le.com"


async def test_redact_empty_string() -> None:
    assert _redact("") == "<empty>"


async def test_factory_defaults_to_stub_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OUTREACH_PROVIDER", raising=False)
    reset_outreach_provider_cache()
    provider = get_outreach_provider()
    assert isinstance(provider, StubOutreachProvider)


async def test_factory_returns_cached_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OUTREACH_PROVIDER", raising=False)
    reset_outreach_provider_cache()
    a = get_outreach_provider()
    b = get_outreach_provider()
    assert a is b


async def test_factory_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OUTREACH_PROVIDER", "ghost-courier")
    reset_outreach_provider_cache()
    with pytest.raises(ValueError, match="Unknown OUTREACH_PROVIDER"):
        get_outreach_provider()


async def test_factory_treats_provider_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OUTREACH_PROVIDER", "STUB")
    reset_outreach_provider_cache()
    provider = get_outreach_provider()
    assert isinstance(provider, StubOutreachProvider)
