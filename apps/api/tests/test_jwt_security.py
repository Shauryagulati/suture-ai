"""JWT hardening tests.

Two new behaviors are driven here (must fail before the fix):
  1. ``decode_token`` rejects tokens missing ``exp``/``iat`` (python-jose
     does not require them by default — a token with no expiry never
     expires).
  2. ``ensure_jwt_secret_configured`` fails closed on an empty/blank
     JWT_SECRET (an empty HS256 key makes every token forgeable).

The alg=none / wrong-secret / expired / valid cases are regression locks
on behavior that is already correct.
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from jose import jwt

from app.config import get_settings
from app.utils.security import (
    JwtError,
    JwtSecretMissingError,
    decode_token,
    ensure_jwt_secret_configured,
)


def _unsigned_none_token(payload: dict) -> str:
    """Hand-build an ``alg=none`` JWT (header.payload.<empty sig>)."""

    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(payload)}."


# ── decode_token requires exp + iat (NEW behavior — must fail first) ──


def test_decode_token_rejects_missing_exp() -> None:
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": "x", "iat": now},  # no exp
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(JwtError):
        decode_token(token)


def test_decode_token_rejects_missing_iat() -> None:
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": "x", "exp": now + 3600},  # no iat
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(JwtError):
        decode_token(token)


# ── regression locks (already correct) ──


def test_decode_token_rejects_alg_none() -> None:
    token = _unsigned_none_token({"sub": "x", "iat": 1, "exp": 9_999_999_999})
    with pytest.raises(JwtError):
        decode_token(token)


def test_decode_token_rejects_wrong_secret() -> None:
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": "x", "iat": now, "exp": now + 3600},
        "a-totally-different-secret-value",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(JwtError):
        decode_token(token)


def test_decode_token_rejects_expired() -> None:
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": "x", "iat": now - 7200, "exp": now - 3600},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(JwtError):
        decode_token(token)


def test_decode_token_accepts_valid_token() -> None:
    settings = get_settings()
    now = int(time.time())
    token = jwt.encode(
        {"sub": "x", "iat": now, "exp": now + 3600},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    decoded = decode_token(token)
    assert decoded["sub"] == "x"


# ── empty-secret boot guard (NEW behavior — must fail first) ──


def test_ensure_jwt_secret_rejects_empty() -> None:
    with pytest.raises(JwtSecretMissingError):
        ensure_jwt_secret_configured("")


def test_ensure_jwt_secret_rejects_blank() -> None:
    with pytest.raises(JwtSecretMissingError):
        ensure_jwt_secret_configured("   ")


def test_ensure_jwt_secret_accepts_real_secret() -> None:
    # No raise for a present secret.
    ensure_jwt_secret_configured("a" * 40)
