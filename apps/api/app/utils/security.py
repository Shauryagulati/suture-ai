"""JWT encode/decode + bcrypt password hashing.

HS256 chosen for simplicity in local dev. JWT_SECRET from env. ADR 006
documents the choice and the upgrade path (RS256 / KMS-managed key).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Passwords ─────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ─── JWT ───────────────────────────────────────────────────────────────


class JwtError(Exception):
    """Raised when a JWT fails to decode or has an unexpected claim shape."""


def _now() -> datetime:
    return datetime.now(UTC)


def encode_access_token(*, user_id: UUID, clinic_id: UUID, role: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires = _now() + timedelta(seconds=settings.jwt_access_token_ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "clinic_id": str(clinic_id),
        "role": role,
        "type": "access",
        "iat": int(_now().timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires


def encode_refresh_token(*, user_id: UUID) -> tuple[str, datetime]:
    settings = get_settings()
    expires = _now() + timedelta(seconds=settings.jwt_refresh_token_ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": int(_now().timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        decoded: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as e:
        raise JwtError(f"invalid token: {e}") from e
    return decoded


# ─── Scheduling links ──────────────────────────────────────────────────


def encode_scheduling_token(
    *,
    patient_id: UUID,
    clinic_id: UUID,
    outreach_attempt_id: UUID,
    referral_id: UUID | None = None,
    discharge_summary_id: UUID | None = None,
) -> tuple[str, datetime]:
    """Sign a public scheduling-link token (HS256).

    The patient receives this in SMS/email; the unauthed scheduling
    endpoint decodes it and uses the embedded clinic_id to scope DB
    access. Type-tagged so it cannot be confused with an access token.
    """
    settings = get_settings()
    expires = _now() + timedelta(seconds=settings.scheduling_token_ttl_seconds)
    payload: dict[str, Any] = {
        "patient_id": str(patient_id),
        "clinic_id": str(clinic_id),
        "outreach_attempt_id": str(outreach_attempt_id),
        "referral_id": str(referral_id) if referral_id is not None else None,
        "discharge_summary_id": (
            str(discharge_summary_id) if discharge_summary_id is not None else None
        ),
        "type": "scheduling",
        "iat": int(_now().timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires


def decode_scheduling_token(token: str) -> dict[str, Any]:
    """Decode + verify a scheduling token. Raises JwtError if invalid,
    expired, or not type=scheduling."""
    decoded = decode_token(token)
    if decoded.get("type") != "scheduling":
        raise JwtError("token type is not 'scheduling'")
    return decoded
