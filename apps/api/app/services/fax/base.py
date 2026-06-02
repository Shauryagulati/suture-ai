"""FaxProvider — abstract outbound fax interface.

Real implementations (eFax, SRFax, Documo) slot in behind this ABC; v1
ships only StubFaxProvider. Selection lives in factory.get_fax_provider,
driven by FAX_PROVIDER env var. Mirrors OutreachProvider intentionally so
the calling convention is consistent across outbound-channel services.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class FaxRequest:
    """A single outbound fax. `pdf_bytes` must be a complete PDF document."""

    to_number: str
    pdf_bytes: bytes
    subject: str
    discharge_summary_id: UUID
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FaxResult:
    """Result returned by a provider's send_fax() call."""

    delivered: bool
    provider_message_id: str | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class FaxProvider(ABC):
    """Send a fax. Implementations must not raise on routine delivery
    failures — return FaxResult(delivered=False, error=...) instead."""

    @abstractmethod
    async def send_fax(self, request: FaxRequest) -> FaxResult: ...
