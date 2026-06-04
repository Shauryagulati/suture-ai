"""Pydantic schemas for the patient registry."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PatientListItem(BaseModel):
    """Row in the patient registry list. Deliberately minimal PHI — no
    dob/phone in bulk responses; those surface on the detail view."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    mrn: str | None
    city: str | None
    state: str | None
    created_at: datetime


class PatientListResponse(BaseModel):
    items: list[PatientListItem]
    total: int
    limit: int
    offset: int


class PatientDetail(BaseModel):
    """Full demographics for a single patient. dob/phone decrypt via the
    EncryptedString TypeDecorator when read from the ORM."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    dob: str
    phone: str
    email: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    mrn: str | None
    created_at: datetime
