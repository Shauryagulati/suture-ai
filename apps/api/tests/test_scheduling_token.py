"""Scheduling JWT encode/decode roundtrip + rejection tests."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from app.utils.security import (
    JwtError,
    decode_scheduling_token,
    encode_access_token,
    encode_scheduling_token,
)


def test_encode_decode_scheduling_token_roundtrip() -> None:
    patient_id = uuid4()
    clinic_id = uuid4()
    attempt_id = uuid4()
    referral_id = uuid4()

    token, expires = encode_scheduling_token(
        patient_id=patient_id,
        clinic_id=clinic_id,
        outreach_attempt_id=attempt_id,
        referral_id=referral_id,
    )
    claims = decode_scheduling_token(token)

    assert claims["patient_id"] == str(patient_id)
    assert claims["clinic_id"] == str(clinic_id)
    assert claims["outreach_attempt_id"] == str(attempt_id)
    assert claims["referral_id"] == str(referral_id)
    assert claims["discharge_summary_id"] is None
    assert claims["type"] == "scheduling"
    assert claims["exp"] == int(expires.timestamp())


def test_encode_with_discharge_id_only_omits_referral() -> None:
    discharge_id = uuid4()
    token, _ = encode_scheduling_token(
        patient_id=uuid4(),
        clinic_id=uuid4(),
        outreach_attempt_id=uuid4(),
        discharge_summary_id=discharge_id,
    )
    claims = decode_scheduling_token(token)
    assert claims["referral_id"] is None
    assert claims["discharge_summary_id"] == str(discharge_id)


def test_decode_rejects_wrong_token_type() -> None:
    """An access token must not be accepted by the scheduling decoder."""
    access, _ = encode_access_token(user_id=uuid4(), clinic_id=uuid4(), role="admin")
    with pytest.raises(JwtError, match="not 'scheduling'"):
        decode_scheduling_token(access)


def test_decode_rejects_garbage() -> None:
    with pytest.raises(JwtError):
        decode_scheduling_token("not-a-jwt")


def test_decode_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    # Override TTL on the cached settings instance for this test.
    settings = get_settings()
    original_ttl = settings.scheduling_token_ttl_seconds
    monkeypatch.setattr(settings, "scheduling_token_ttl_seconds", 1, raising=False)
    try:
        token, _ = encode_scheduling_token(
            patient_id=uuid4(), clinic_id=uuid4(), outreach_attempt_id=uuid4()
        )
        time.sleep(2)
        with pytest.raises(JwtError):
            decode_scheduling_token(token)
    finally:
        monkeypatch.setattr(
            settings, "scheduling_token_ttl_seconds", original_ttl, raising=False
        )


def test_scheduling_token_carries_iat_and_exp_in_correct_order() -> None:
    token, _ = encode_scheduling_token(
        patient_id=uuid4(), clinic_id=uuid4(), outreach_attempt_id=uuid4()
    )
    claims = decode_scheduling_token(token)
    assert "iat" in claims
    assert "exp" in claims
    assert claims["exp"] > claims["iat"]
