"""StubFaxProvider + factory tests."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio

from app.services.fax import stub as stub_mod  # noqa: E402
from app.services.fax.base import FaxRequest  # noqa: E402
from app.services.fax.factory import (  # noqa: E402
    get_fax_provider,
    reset_fax_provider_cache,
)
from app.services.fax.stub import StubFaxProvider, _redact  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_factory_cache():
    reset_fax_provider_cache()
    yield
    reset_fax_provider_cache()


@pytest.fixture
def _isolated_outbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the stub provider's on-disk outbox to a per-test tmp dir."""
    outbox = tmp_path / "fax_outbox"
    monkeypatch.setattr(stub_mod, "_OUTBOX_ROOT", outbox)
    return outbox


async def test_stub_records_send_and_persists_pdf(_isolated_outbox: Path) -> None:
    provider = StubFaxProvider()
    discharge_id = uuid4()
    req = FaxRequest(
        to_number="412-555-9999",
        pdf_bytes=b"%PDF-1.4\n%fake\n",
        subject="Discharge Follow-Up Confirmation",
        discharge_summary_id=discharge_id,
    )

    result = await provider.send_fax(req)

    assert result.delivered is True
    assert result.provider_message_id is not None
    assert result.provider_message_id.startswith("stub-fax-")
    assert provider.sent == [req]

    persisted = _isolated_outbox / f"{discharge_id}.pdf"
    assert persisted.exists()
    assert persisted.read_bytes() == b"%PDF-1.4\n%fake\n"


async def test_stub_accumulates_multiple_sends(_isolated_outbox: Path) -> None:
    provider = StubFaxProvider()
    ids = [uuid4() for _ in range(3)]
    for did in ids:
        await provider.send_fax(
            FaxRequest(
                to_number="412-555-0100",
                pdf_bytes=b"%PDF-1.4\n",
                subject="x",
                discharge_summary_id=did,
            )
        )
    assert len(provider.sent) == 3
    assert [r.discharge_summary_id for r in provider.sent] == ids


async def test_stub_does_not_log_raw_fax_number(
    _isolated_outbox: Path, caplog: pytest.LogCaptureFixture
) -> None:
    raw_number = "412-555-7777"
    provider = StubFaxProvider()
    with caplog.at_level(logging.INFO):
        await provider.send_fax(
            FaxRequest(
                to_number=raw_number,
                pdf_bytes=b"%PDF-1.4\n",
                subject="x",
                discharge_summary_id=uuid4(),
            )
        )
    rendered = " ".join(r.getMessage() for r in caplog.records)
    assert raw_number not in rendered


async def test_redact_fax_keeps_last_four_only() -> None:
    assert _redact("412-555-9999") == "***-9999"
    assert _redact("(412) 555 - 0123") == "***-0123"


async def test_redact_empty_returns_short_mask() -> None:
    assert _redact("") == "***"


async def test_factory_defaults_to_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAX_PROVIDER", raising=False)
    reset_fax_provider_cache()
    assert isinstance(get_fax_provider(), StubFaxProvider)


async def test_factory_returns_cached_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FAX_PROVIDER", raising=False)
    reset_fax_provider_cache()
    a = get_fax_provider()
    b = get_fax_provider()
    assert a is b


async def test_factory_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAX_PROVIDER", "totally-fake")
    reset_fax_provider_cache()
    with pytest.raises(ValueError, match="Unknown FAX_PROVIDER"):
        get_fax_provider()


async def test_factory_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAX_PROVIDER", "STUB")
    reset_fax_provider_cache()
    assert isinstance(get_fax_provider(), StubFaxProvider)
