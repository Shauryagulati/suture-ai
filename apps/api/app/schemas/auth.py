"""Pydantic schemas for auth endpoints."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class MembershipSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    clinic_id: UUID
    role: str
    is_default: bool


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: UUID
    active_clinic_id: UUID
    role: str
    memberships: list[MembershipSummary]


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = Field(pattern="^(admin|reviewer|readonly)$")


class MeResponse(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    active_clinic_id: UUID
    role: str
