"""Request-scoped ContextVars for tenancy, identity, and audit.

These are set by the auth dependency (Gate B2) and request middleware
(Gate B2). Read by the tenant guard (database.py) and the audit listener
(audit.py).

Tests set these directly via the `set_clinic_context` fixture.
"""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

current_clinic_id: ContextVar[UUID | None] = ContextVar("current_clinic_id", default=None)
current_user_id: ContextVar[UUID | None] = ContextVar("current_user_id", default=None)
current_ip_address: ContextVar[str | None] = ContextVar("current_ip_address", default=None)


class TenantContextMissingError(RuntimeError):
    """Raised when a clinic-scoped query runs without `current_clinic_id` set.

    Fail-closed: a missing tenant context is a programming error, not a
    silent leak. The auth dependency must set `current_clinic_id` before
    any DB session is yielded.
    """


class TenantContextMismatchError(RuntimeError):
    """Raised on INSERT when target.clinic_id != current_clinic_id.

    Indicates a bug where app code tried to insert into a different
    tenant's table than the one the request is scoped to.
    """
