"""Outreach provider factory — env-driven, cached.

Mirrors the LLM / embedding factory pattern. Default provider is the
stub; real providers (Twilio, SendGrid, LiveKit) require explicit opt-in
via `OUTREACH_PROVIDER` env var so dev + test setups don't accidentally
hit billable APIs.
"""

from __future__ import annotations

import functools
import os

from app.services.outreach.base import OutreachProvider
from app.services.outreach.stub import StubOutreachProvider

_DEFAULT_PROVIDER = "stub"


@functools.lru_cache(maxsize=1)
def get_outreach_provider() -> OutreachProvider:
    """Return the configured OutreachProvider. Defaults to stub."""
    name = os.getenv("OUTREACH_PROVIDER", _DEFAULT_PROVIDER).lower()

    if name == "stub":
        return StubOutreachProvider()

    if name == "livekit":
        # Lazy import — LiveKitOutreachProvider pulls in the livekit SDK
        # which we don't want loaded under OUTREACH_PROVIDER=stub.
        from app.services.outreach.livekit import LiveKitOutreachProvider

        return LiveKitOutreachProvider()

    raise ValueError(
        f"Unknown OUTREACH_PROVIDER={name!r}; expected one of: stub, livekit"
    )


def reset_outreach_provider_cache() -> None:
    """Drop the cached provider so tests can install a fresh stub."""
    get_outreach_provider.cache_clear()
