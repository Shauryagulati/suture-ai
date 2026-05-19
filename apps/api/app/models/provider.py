"""Provider — referring or internal practitioner. Tenant-scoped."""

from __future__ import annotations

import enum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import ClinicScopedBase


class ProviderType(enum.StrEnum):
    referring = "referring"
    internal = "internal"


class Provider(ClinicScopedBase):
    __tablename__ = "providers"

    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    npi: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    practice_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    practice_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    practice_fax: Mapped[str | None] = mapped_column(String(32), nullable=True)
    practice_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    provider_type: Mapped[ProviderType] = mapped_column(
        Enum(ProviderType, name="provider_type"), nullable=False
    )
    specialty: Mapped[str | None] = mapped_column(String(120), nullable=True)
