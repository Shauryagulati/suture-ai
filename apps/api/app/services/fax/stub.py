"""StubFaxProvider — records sends in-process.

Writes the PDF under var/fax_outbox/{discharge_id}.pdf for local manual
inspection, mirroring the prior-auth packet's local-storage ergonomics.
Real fax providers (eFax, SRFax) slot in via FAX_PROVIDER env var; their
implementations live in sibling modules added later.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.services.fax.base import FaxProvider, FaxRequest, FaxResult
from app.utils.logging import get_logger

log = get_logger(__name__)

_OUTBOX_ROOT = Path(__file__).resolve().parents[3] / "var" / "fax_outbox"


def _redact(number: str) -> str:
    """Return a short fingerprint so the log line confirms a send happened
    without echoing the recipient fax into logs."""
    digits = "".join(ch for ch in number if ch.isdigit())
    return f"***-{digits[-4:]}" if len(digits) >= 4 else "***"


class StubFaxProvider(FaxProvider):
    """In-memory recorder. Writes the PDF to disk and appends to `sent`."""

    def __init__(self) -> None:
        self.sent: list[FaxRequest] = []

    async def send_fax(self, request: FaxRequest) -> FaxResult:
        _OUTBOX_ROOT.mkdir(parents=True, exist_ok=True)
        out_path = _OUTBOX_ROOT / f"{request.discharge_summary_id}.pdf"
        out_path.write_bytes(request.pdf_bytes)
        self.sent.append(request)
        log.info(
            "fax.stub.send",
            discharge_summary_id=str(request.discharge_summary_id),
            to_fingerprint=_redact(request.to_number),
            bytes=len(request.pdf_bytes),
            outbox_path=str(out_path),
        )
        return FaxResult(
            delivered=True,
            provider_message_id=f"stub-fax-{uuid4().hex[:12]}",
            raw={"outbox_path": str(out_path)},
        )
