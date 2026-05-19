"""Async SQLAlchemy engine + ClinicScopedSession with tenant guard.

The tenant guard:
- A `do_orm_execute` event listener on Session inspects every ORM
  statement. For models inheriting `ClinicScopedBase`, it applies a
  `with_loader_criteria` clause restricting rows to `clinic_id =
  current_clinic_id.get()`. If `current_clinic_id` is unset, the listener
  raises `TenantContextMissingError` — fail closed.
- A `before_insert` event listener on `ClinicScopedBase` sets `clinic_id`
  from the ContextVar if missing and rejects mismatches.

Raw `text()` SQL bypasses the guard. ADR 002 forbids it in app code
outside Alembic migrations.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.base import ClinicScopedBase
from app.utils.context import (
    TenantContextMismatchError,
    TenantContextMissingError,
    current_clinic_id,
)


def _build_engine() -> Any:
    settings = get_settings()
    # NullPool: each checkout opens a fresh asyncpg connection, each return
    # closes it. Sidesteps event-loop-binding issues in tests and is fine for
    # local-dev load. Production will switch to a pooled engine in deploy
    # config (env-driven).
    return create_async_engine(
        settings.database_url,
        echo=False,
        poolclass=NullPool,
    )


engine = _build_engine()
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ─── Tenant guard ──────────────────────────────────────────────────────


def _is_clinic_scoped_statement(state: ORMExecuteState) -> bool:
    """True if the statement involves any ClinicScopedBase subclass."""
    for mapper in state.all_mappers:
        cls = mapper.class_
        if getattr(cls, "_skip_tenant_guard", False):
            continue
        if issubclass(cls, ClinicScopedBase):
            return True
    return False


@event.listens_for(Session, "do_orm_execute")
def _tenant_filter(state: ORMExecuteState) -> None:
    """Inject WHERE clinic_id = :current_clinic_id on every clinic-scoped query.

    For SELECT/UPDATE/DELETE. INSERT goes through `before_insert` below.
    """
    if not _is_clinic_scoped_statement(state):
        return

    # AuditLog inherits ClinicScopedBase but has nullable clinic_id (system
    # rows). Treat it as guard-bypassed: writes are direct, reads are
    # explicit; we don't want the guard to hide NULL-clinic system events.
    if state.is_select or state.is_update or state.is_delete:
        cid = current_clinic_id.get()
        if cid is None:
            raise TenantContextMissingError(
                "Clinic-scoped query attempted without current_clinic_id set. "
                "The auth dependency must populate the ContextVar before any "
                "ORM access."
            )
        state.statement = state.statement.options(
            with_loader_criteria(
                ClinicScopedBase,
                lambda cls: cls.clinic_id == cid,
                include_aliases=True,
            )
        )


@event.listens_for(ClinicScopedBase, "before_insert", propagate=True)
def _set_clinic_id_on_insert(_mapper: Any, _connection: Any, target: Any) -> None:
    """Populate or validate `clinic_id` against the ContextVar at INSERT time."""
    # AuditLog rows are inserted by the audit listener with an explicit
    # clinic_id (sometimes NULL for system events) and must bypass.
    if getattr(type(target), "_audit_exempt", False):
        return

    cid = current_clinic_id.get()
    if cid is None:
        raise TenantContextMissingError("INSERT on clinic-scoped table requires current_clinic_id.")

    if target.clinic_id is None:
        target.clinic_id = cid
    elif target.clinic_id != cid:
        raise TenantContextMismatchError(
            f"INSERT clinic_id={target.clinic_id} does not match current_clinic_id={cid}."
        )


# ─── FastAPI dependency ────────────────────────────────────────────────


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield an async session. The auth dependency must set the ContextVar
    BEFORE this is yielded — wire ordering in the router.
    """
    async with async_session_maker() as session:
        yield session
