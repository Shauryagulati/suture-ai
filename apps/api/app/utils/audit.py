"""Audit logging via SQLAlchemy event listeners.

Every PHI-bearing model in `AUDITED_MODELS` gets `after_insert` /
`after_update` / `after_delete` listeners that write an `audit_logs`
row. View actions for GET endpoints must call `track_view()` explicitly
(SQLAlchemy has no `after_select` event for ORM queries).

The `details` JSONB column carries **only IDs and column names** — never
PHI values. Tests verify this.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import event, inspect

from app.utils.context import (
    current_clinic_id,
    current_ip_address,
    current_user_id,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.orm import Mapper

    from app.models.base import ClinicScopedBase


# Models that emit audit events. Populated by `register_audited_models()`
# during app startup (and at module import time for the listener to attach).
AUDITED_MODELS: list[type[ClinicScopedBase]] = []


def register_audited_models() -> None:
    """Attach insert/update/delete listeners to every model in AUDITED_MODELS.

    Idempotent. Called at app startup (lifespan) and from test fixtures.
    Imports here avoid the circular-import risk during module load.
    """
    # Local imports prevent circular imports at module load.
    from app.models import (
        Appointment,
        Call,
        CallTranscript,
        DischargeSummary,
        Document,
        DocumentExtraction,
        Fax,
        InsurancePolicy,
        OutreachAttempt,
        Patient,
        Referral,
        ReferralTask,
    )

    AUDITED_MODELS.clear()
    AUDITED_MODELS.extend(
        [
            Patient,
            Document,
            DocumentExtraction,
            Referral,
            DischargeSummary,
            Appointment,
            OutreachAttempt,
            Call,
            CallTranscript,
            InsurancePolicy,
            ReferralTask,
            Fax,
        ]
    )

    for model in AUDITED_MODELS:
        if not event.contains(model, "after_insert", _audit_after_insert):
            event.listen(model, "after_insert", _audit_after_insert, propagate=True)
        if not event.contains(model, "after_update", _audit_after_update):
            event.listen(model, "after_update", _audit_after_update, propagate=True)
        if not event.contains(model, "after_delete", _audit_after_delete):
            event.listen(model, "after_delete", _audit_after_delete, propagate=True)


def _audit_after_insert(_mapper: Mapper[Any], connection: Connection, target: Any) -> None:
    _write_audit_row(
        connection,
        action="create",
        target=target,
        details={"created": True},
    )


def _audit_after_update(_mapper: Mapper[Any], connection: Connection, target: Any) -> None:
    state = inspect(target)
    changed_columns: list[str] = []
    for attr in state.attrs:
        hist = attr.history
        if hist.has_changes():
            changed_columns.append(attr.key)
    _write_audit_row(
        connection,
        action="update",
        target=target,
        # Column NAMES only — never values, which may be PHI.
        details={"changed_columns": sorted(changed_columns)},
    )


def _audit_after_delete(_mapper: Mapper[Any], connection: Connection, target: Any) -> None:
    _write_audit_row(
        connection,
        action="delete",
        target=target,
        details={"deleted": True},
    )


def _write_audit_row(
    connection: Connection,
    *,
    action: str,
    target: Any,
    details: dict[str, Any],
) -> None:
    # Local imports to avoid circular dependencies.
    from app.models.audit_log import AuditLog

    resource_type = type(target).__tablename__
    resource_id: UUID | None = getattr(target, "id", None)
    clinic_id: UUID | None = getattr(target, "clinic_id", None)
    user_id = current_user_id.get()
    ip_address = current_ip_address.get()

    from sqlalchemy import insert as sa_insert

    connection.execute(
        sa_insert(AuditLog).values(
            id=_new_uuid(),
            clinic_id=clinic_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        )
    )


def _new_uuid() -> UUID:
    from uuid import uuid4

    return uuid4()


def track_view(
    connection: Connection,
    *,
    resource_type: str,
    resource_id: UUID | None,
    clinic_id: UUID | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit a `view` audit row from a GET endpoint.

    Must be called explicitly — there is no SQLAlchemy event for SELECT.
    """
    from app.models.audit_log import AuditLog

    details: dict[str, Any] = {"viewed": True}
    if extra:
        details.update(extra)

    from sqlalchemy import insert as sa_insert

    connection.execute(
        sa_insert(AuditLog).values(
            id=_new_uuid(),
            clinic_id=clinic_id if clinic_id is not None else current_clinic_id.get(),
            user_id=current_user_id.get(),
            action="view",
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=current_ip_address.get(),
        )
    )
