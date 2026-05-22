"""FastAPI dependencies.

`get_current_user` parses the bearer JWT, looks up the user + membership,
and SETS the ContextVars (current_clinic_id, current_user_id) BEFORE the
DB session is yielded. The route signature must place it before
`Depends(get_db)` so FastAPI resolves auth first.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import ClinicMembership, User
from app.utils.context import (
    current_clinic_id,
    current_ip_address,
    current_user_id,
)
from app.utils.security import JwtError, decode_token

_bearer = HTTPBearer(auto_error=True)


@dataclass(slots=True)
class CurrentUser:
    user_id: UUID
    email: str
    full_name: str
    active_clinic_id: UUID
    role: str


async def _open_session() -> AsyncIterator[AsyncSession]:
    """Internal session opener used by get_current_user (cannot reuse get_db
    because that one depends on the ContextVar already being set)."""
    async with async_session_maker() as session:
        yield session


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> CurrentUser:
    """Decode the bearer, validate the user + active clinic membership, and
    set request-scoped ContextVars before any downstream dependency runs.
    """
    # 1) Decode the JWT.
    try:
        payload = decode_token(creds.credentials)
    except JwtError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not an access token")

    try:
        user_id = UUID(payload["sub"])
        clinic_id = UUID(payload["clinic_id"])
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="malformed claims"
        ) from e

    # 2) Open a transient session (NOT through get_db — that one needs the
    # ContextVar to already be set, which we haven't done yet).
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="user not found or inactive",
            )
        # Verify the claimed clinic_id is in fact one of the user's memberships.
        membership = (
            await session.execute(
                select(ClinicMembership).where(
                    ClinicMembership.user_id == user_id,
                    ClinicMembership.clinic_id == clinic_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="user has no membership for this clinic",
            )

        result = CurrentUser(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            active_clinic_id=clinic_id,
            role=membership.role.value,
        )

    # 3) Set ContextVars for downstream dependencies.
    current_user_id.set(user.id)
    current_clinic_id.set(clinic_id)
    if request.client is not None:
        current_ip_address.set(request.client.host)

    return result


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return user


class WebSocketAuthError(Exception):
    """Raised when WebSocket bearer-token auth fails. The caller closes
    the connection with an appropriate 4xxx code."""

    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


async def get_current_user_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> CurrentUser:
    """WebSocket auth — bearer JWT passed as `?token=...` (HTTP headers
    aren't available before the upgrade handshake). Mirrors get_current_user:
    decodes the JWT, validates the user + active membership, sets the
    ContextVars. On failure raises WebSocketAuthError; the route handler
    is responsible for `await websocket.close(code=...)`."""
    if not token:
        raise WebSocketAuthError(4401, "missing token")
    try:
        payload = decode_token(token)
    except JwtError as e:
        raise WebSocketAuthError(4401, f"invalid token: {e}") from e
    if payload.get("type") != "access":
        raise WebSocketAuthError(4401, "not an access token")
    try:
        user_id = UUID(payload["sub"])
        clinic_id = UUID(payload["clinic_id"])
    except (KeyError, ValueError, TypeError) as e:
        raise WebSocketAuthError(4401, "malformed claims") from e

    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            raise WebSocketAuthError(4401, "user not found or inactive")
        membership = (
            await session.execute(
                select(ClinicMembership).where(
                    ClinicMembership.user_id == user_id,
                    ClinicMembership.clinic_id == clinic_id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise WebSocketAuthError(4403, "user has no membership for this clinic")
        result = CurrentUser(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            active_clinic_id=clinic_id,
            role=membership.role.value,
        )

    current_user_id.set(user.id)
    current_clinic_id.set(clinic_id)
    if websocket.client is not None:
        current_ip_address.set(websocket.client.host)

    return result
