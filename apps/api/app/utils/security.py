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


class JwtSecretMissingError(RuntimeError):
    """Raised at startup when JWT_SECRET is empty/blank.

    HS256 signs and verifies with the same key. An empty key is accepted
    by jose for *both* operations, which means an unconfigured deployment
    would accept any forged token. Fail closed at boot — same posture as
    `PhiEncryptionKeyMissingError` for the PHI key.
    """


def ensure_jwt_secret_configured(secret: str) -> None:
    """Refuse to operate without a JWT secret. Call at app startup.

    Hard-fails on an empty or whitespace-only secret (the security-critical
    case). A present-but-short secret is allowed but should be warned about
    by the caller; we don't hard-fail there to avoid breaking existing
    local/test secrets.
    """
    if not secret or not secret.strip():
        raise JwtSecretMissingError(
            "JWT_SECRET is not set. Run `make gen-jwt-keys` to generate one. "
            "An empty HS256 secret makes every token forgeable."
        )


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
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            # Require expiry + issued-at. python-jose validates these claims
            # only when present; without `require_*` a token minted with no
            # `exp` would never expire. Every token we issue sets both.
            options={"require_exp": True, "require_iat": True},
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


# ─── Transcript stream tokens ──────────────────────────────────────────


def encode_stream_token(*, call_id: UUID, clinic_id: UUID) -> tuple[str, datetime]:
    """Sign a short-lived token scoped to a single call's transcript stream.

    Minted by an authenticated, clinic-scoped endpoint and handed to the
    browser so the full access bearer never reaches the client or the WS
    URL. Type-tagged so it can't be confused with an access token.
    """
    settings = get_settings()
    expires = _now() + timedelta(seconds=settings.stream_token_ttl_seconds)
    payload: dict[str, Any] = {
        "call_id": str(call_id),
        "clinic_id": str(clinic_id),
        "type": "stream",
        "iat": int(_now().timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires


def decode_stream_token(token: str) -> dict[str, Any]:
    """Decode + verify a stream token. Raises JwtError if invalid, expired,
    or not type=stream (an access bearer is rejected here)."""
    decoded = decode_token(token)
    if decoded.get("type") != "stream":
        raise JwtError("token type is not 'stream'")
    return decoded
