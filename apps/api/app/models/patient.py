"""Patient — tenant-scoped, PHI-bearing. Fernet-encrypted DOB/phone/SSN."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase
from app.utils.encryption import EncryptedString


class Patient(ClinicScopedBase):
    __tablename__ = "patients"

    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # PHI: encrypted at the ORM layer via Fernet (ADR 003).
    dob: Mapped[str] = mapped_column(EncryptedString, nullable=False)  # YYYY-MM-DD
    phone: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    ssn: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    mrn: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
