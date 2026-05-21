"""OutreachProvider — abstract send interface used by SMS/email/voice services.

Real implementations (Twilio, SendGrid, LiveKit) slot in behind this ABC; v1
ships only `StubOutreachProvider`. Selection happens in `factory.get_outreach_provider`,
driven by the `OUTREACH_PROVIDER` env var.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models.outreach_attempt import OutreachChannel


@dataclass
class OutreachMessage:
    """A single outbound message handed to a provider."""

    channel: OutreachChannel
    to: str
    body: str
    subject: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutreachResult:
    """Result returned by a provider's `send()` call."""

    delivered: bool
    provider_message_id: str | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class OutreachProvider(ABC):
    """Send messages over SMS / email / voice. Implementations decide
    which channels they support — sending an unsupported channel
    should return `OutreachResult(delivered=False, error=...)`, not raise."""

    @abstractmethod
    async def send(self, message: OutreachMessage) -> OutreachResult:
        """Send a single message. Must not raise on routine delivery failures;
        return `OutreachResult(delivered=False, error=...)` instead."""
