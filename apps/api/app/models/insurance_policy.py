"""InsurancePolicy + EligibilityCheck — payer coverage tracking."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase
from app.utils.encryption import EncryptedString


class VerificationStatus(enum.StrEnum):
    unverified = "unverified"
    verified = "verified"
    invalid = "invalid"
    expired = "expired"


class EligibilityResult(enum.StrEnum):
    eligible = "eligible"
    ineligible = "ineligible"
    pending = "pending"
    error = "error"


class InsurancePolicy(ClinicScopedBase):
    __tablename__ = "insurance_policies"

    patient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    payer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # PHI: encrypted at app layer.
    member_id: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    group_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.unverified,
    )


class EligibilityCheck(ClinicScopedBase):
    __tablename__ = "eligibility_checks"

    patient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    insurance_policy_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("insurance_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[EligibilityResult] = mapped_column(
        Enum(EligibilityResult, name="eligibility_result"), nullable=False
    )
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
