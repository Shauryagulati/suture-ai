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

from fastapi import Depends, HTTPException, Request, status
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
