"""Auth business logic — login, refresh, register.

These functions do not own the HTTP layer (that's `app/routers/auth.py`).
They take a session and the relevant inputs, and raise typed exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Clinic, ClinicMembership, MembershipRole, User
from app.utils.security import (
    JwtError,
    decode_token,
    encode_access_token,
    encode_refresh_token,
    hash_password,
    verify_password,
)


class AuthError(Exception):
    """Base for auth failures."""


class InvalidCredentialsError(AuthError):
    """Email/password did not match."""


class InactiveUserError(AuthError):
    """User exists but is_active=False."""


class NoMembershipError(AuthError):
    """User has no clinic_memberships — cannot mint a clinic-bound JWT."""


class InvalidRefreshTokenError(AuthError):
    """Refresh token was malformed, expired, or not of type=refresh."""


class EmailAlreadyExistsError(AuthError):
    """Registration: another user already has this email."""


@dataclass(slots=True)
class LoginResult:
    access_token: str
    refresh_token: str
    user_id: UUID
    active_clinic_id: UUID
    role: str
    memberships: list[ClinicMembership]


async def authenticate(db: AsyncSession, *, email: str, password: str) -> LoginResult:
    """Validate credentials, return tokens bound to the user's default membership."""
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        raise InvalidCredentialsError("no user with that email")
    if not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError("password mismatch")
    if not user.is_active:
        raise InactiveUserError("user is deactivated")

    memberships = (
        (await db.execute(select(ClinicMembership).where(ClinicMembership.user_id == user.id)))
        .scalars()
        .all()
    )
    if not memberships:
        raise NoMembershipError("user has no clinic memberships")

    # Pick the default membership; fall back to first if none flagged.
    default = next((m for m in memberships if m.is_default), memberships[0])

    access_token, _ = encode_access_token(
        user_id=user.id, clinic_id=default.clinic_id, role=default.role.value
    )
    refresh_token, _ = encode_refresh_token(user_id=user.id)

    return LoginResult(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        active_clinic_id=default.clinic_id,
        role=default.role.value,
        memberships=list(memberships),
    )


async def refresh_access_token(db: AsyncSession, *, refresh_token: str) -> str:
    """Mint a new access token from a valid refresh token.

    Looks up the user and their default membership; if either has changed
    (deactivated, membership revoked), refresh fails.
    """
    try:
        payload = decode_token(refresh_token)
    except JwtError as e:
        raise InvalidRefreshTokenError(str(e)) from e

    if payload.get("type") != "refresh":
        raise InvalidRefreshTokenError("token type is not refresh")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise InvalidRefreshTokenError("missing sub")

    try:
        user_id = UUID(user_id_str)
    except ValueError as e:
        raise InvalidRefreshTokenError("malformed sub") from e

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise InvalidRefreshTokenError("user not found or inactive")

    memberships = (
        (await db.execute(select(ClinicMembership).where(ClinicMembership.user_id == user.id)))
        .scalars()
        .all()
    )
    if not memberships:
        raise InvalidRefreshTokenError("user has no memberships")
    default = next((m for m in memberships if m.is_default), memberships[0])

    access_token, _ = encode_access_token(
        user_id=user.id, clinic_id=default.clinic_id, role=default.role.value
    )
    return access_token


async def register_user(
    db: AsyncSession,
    *,
    caller_clinic_id: UUID,
    email: str,
    password: str,
    full_name: str,
    role: str,
) -> User:
    """Admin-only: create a new user inside the caller's clinic.

    The admin check happens at the route layer; this service trusts that
    caller_clinic_id is authoritative.
    """
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        raise EmailAlreadyExistsError(f"user with email {email!r} already exists")

    # Verify the clinic exists.
    clinic = await db.get(Clinic, caller_clinic_id)
    if clinic is None:
        raise AuthError(f"clinic {caller_clinic_id} not found")

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
    )
    db.add(user)
    await db.flush()  # populate user.id

    membership = ClinicMembership(
        user_id=user.id,
        clinic_id=caller_clinic_id,
        role=MembershipRole(role),
        is_default=True,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(user)
    return user
