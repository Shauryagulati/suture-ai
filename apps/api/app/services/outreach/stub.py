"""StubOutreachProvider — records sends in-process; v1 default.

Used in dev + tests so the outreach pipeline can be exercised end-to-end
without real Twilio / SendGrid / LiveKit credentials. Real providers
slot in via `OUTREACH_PROVIDER` env var; their implementations live in
sibling modules (twilio.py, sendgrid.py, ...) added later.

The instance carries its own `sent` list — tests instantiate a fresh
provider per case to avoid cross-test bleed. The factory caches one
instance for the process, which is fine in dev (cleared between
process restarts) but tests should not rely on the singleton's history.
"""

from __future__ import annotations

from uuid import uuid4

from app.services.outreach.base import OutreachMessage, OutreachProvider, OutreachResult
from app.utils.logging import get_logger

log = get_logger(__name__)


def _redact(value: str) -> str:
    """Return a short fingerprint so the log line confirms a send happened
    without echoing the phone number / email address into logs.

    PHI keys are scrubbed by the logging processor regardless; this
    keeps even non-PHI keys ('to_fingerprint') from leaking the value.
    """
    if not value:
        return "<empty>"
    if "@" in value:
        local, _, domain = value.partition("@")
        return f"{local[:1]}***@{domain[-6:]}"
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 4:
        return f"***-{digits[-4:]}"
    return "***"


class StubOutreachProvider(OutreachProvider):
    """In-memory provider. Records every send on `self.sent` and returns
    delivered=True with a fake provider_message_id."""

    def __init__(self) -> None:
        self.sent: list[OutreachMessage] = []

    async def send(self, message: OutreachMessage) -> OutreachResult:
        self.sent.append(message)
        log.info(
            "outreach.stub.send",
            channel=message.channel.value,
            to_fingerprint=_redact(message.to),
            body_len=len(message.body),
        )
        return OutreachResult(
            delivered=True,
            provider_message_id=f"stub-{uuid4().hex[:12]}",
        )
