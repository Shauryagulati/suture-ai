"""Clinic settings endpoint — roster is scoped to the caller's clinic."""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic_membership import MembershipRole
from tests._doc_helpers import auth_headers, make_user_and_login

pytestmark = pytest.mark.asyncio


async def test_settings_returns_clinic_and_scoped_members(
    client: AsyncClient, db_session: AsyncSession, two_clinics: tuple[UUID, UUID]
) -> None:
    clinic_a, clinic_b = two_clinics
    admin_token = await make_user_and_login(
        client=client,
        db=db_session,
        email="settings-admin@suture-test.example.com",
        password="settings-pw-1",
        clinic_id=clinic_a,
        role=MembershipRole.admin,
    )
    await make_user_and_login(
        client=client,
        db=db_session,
        email="settings-reviewer@suture-test.example.com",
        password="settings-pw-2",
        clinic_id=clinic_a,
        role=MembershipRole.reviewer,
    )
    # A member of the OTHER clinic must not appear in clinic A's roster.
    await make_user_and_login(
        client=client,
        db=db_session,
        email="other-clinic@suture-test.example.com",
        password="settings-pw-3",
        clinic_id=clinic_b,
        role=MembershipRole.admin,
    )

    resp = await client.get("/api/clinic/settings", headers=auth_headers(admin_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["clinic_name"] == "Test Clinic A"
    assert body["your_role"] == "admin"
    emails = {m["email"] for m in body["members"]}
    assert "settings-admin@suture-test.example.com" in emails
    assert "settings-reviewer@suture-test.example.com" in emails
    assert "other-clinic@suture-test.example.com" not in emails
    assert all(m["role"] in {"admin", "reviewer", "readonly"} for m in body["members"])


async def test_settings_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/clinic/settings")
    assert resp.status_code in (401, 403)
