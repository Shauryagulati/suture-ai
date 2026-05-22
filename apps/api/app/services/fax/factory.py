"""Fax provider factory — env-driven, cached.

Mirrors the LLM/embedding/outreach factory pattern. Default provider is
the stub; real providers require explicit opt-in via FAX_PROVIDER env
var so dev + test setups don't accidentally bill or send real faxes.
"""

from __future__ import annotations

import functools
import os

from app.services.fax.base import FaxProvider
from app.services.fax.stub import StubFaxProvider

_DEFAULT_PROVIDER = "stub"


@functools.lru_cache(maxsize=1)
def get_fax_provider() -> FaxProvider:
    """Return the configured FaxProvider. Defaults to stub."""
    name = os.getenv("FAX_PROVIDER", _DEFAULT_PROVIDER).lower()

    if name == "stub":
        return StubFaxProvider()

    raise ValueError(
        f"Unknown FAX_PROVIDER={name!r}; expected one of: stub"
    )


def reset_fax_provider_cache() -> None:
    """Drop the cached provider so tests can install a fresh stub."""
    get_fax_provider.cache_clear()
