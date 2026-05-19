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
