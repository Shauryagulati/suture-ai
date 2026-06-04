"""Schemas for the clinic settings (read-only) view."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ClinicMemberOut(BaseModel):
    email: str
    full_name: str
    role: str


class ClinicSettingsResponse(BaseModel):
    clinic_id: UUID
    clinic_name: str
    your_role: str
    members: list[ClinicMemberOut]
