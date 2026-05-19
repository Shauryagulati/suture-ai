"""Auth endpoint tests — login, refresh, me, register."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClinicMembership, MembershipRole, User
from app.utils.security import hash_password

pytestmark = pytest.mark.asyncio


# ─── Fixtures specific to auth tests ───────────────────────────────────


async def _make_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    clinic_id: UUID,
    role: MembershipRole = MembershipRole.admin,
    is_active: bool = True,
) -> User:
    user = User(
        id=uuid4(),
        email=email,
        hashed_password=hash_password(password),
        full_name="Test User",
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    db.add(ClinicMembership(user_id=user.id, clinic_id=clinic_id, role=role, is_default=True))
    await db.commit()
    return user


# ─── Tests ─────────────────────────────────────────────────────────────


async def test_login_returns_tokens(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    await _make_user(
        db_session,
        email="admin@a.example.com",
        password="suture_dev_123",
        clinic_id=clinic_a,
    )

    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@a.example.com", "password": "suture_dev_123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["active_clinic_id"] == str(clinic_a)
    assert body["role"] == "admin"
    assert len(body["memberships"]) == 1


async def test_login_wrong_password_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    await _make_user(
        db_session,
        email="admin@a.example.com",
        password="correct_horse_battery_staple",
        clinic_id=clinic_a,
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@a.example.com", "password": "wrong_password"},
    )
    assert resp.status_code == 401


async def test_login_inactive_user_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    await _make_user(
        db_session,
        email="admin@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
        is_active=False,
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@a.example.com", "password": "pw1234567"},
    )
    assert resp.status_code == 403


async def test_refresh_returns_new_access_token(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    await _make_user(
        db_session,
        email="admin@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@a.example.com", "password": "pw1234567"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200
    assert refresh_resp.json()["access_token"]


async def test_refresh_invalid_returns_401(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/refresh", json={"refresh_token": "not.a.valid.jwt"})
    assert resp.status_code == 401


async def test_me_requires_bearer(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/me")
    assert resp.status_code in (401, 403)  # HTTPBearer auto-rejects


async def test_me_returns_user_clinic_role(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    await _make_user(
        db_session,
        email="admin@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
        role=MembershipRole.reviewer,
    )
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@a.example.com", "password": "pw1234567"},
    )
    access = login_resp.json()["access_token"]

    me_resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me_resp.status_code == 200, me_resp.text
    body = me_resp.json()
    assert body["email"] == "admin@a.example.com"
    assert body["active_clinic_id"] == str(clinic_a)
    assert body["role"] == "reviewer"


async def test_register_requires_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    # Reviewer (not admin) tries to register a user.
    await _make_user(
        db_session,
        email="reviewer@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
        role=MembershipRole.reviewer,
    )
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "reviewer@a.example.com", "password": "pw1234567"},
    )
    access = login_resp.json()["access_token"]

    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "newbie@a.example.com",
            "password": "pw87654321",
            "full_name": "Newbie",
            "role": "readonly",
        },
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 403


async def test_register_creates_user_and_membership(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    await _make_user(
        db_session,
        email="admin@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
        role=MembershipRole.admin,
    )
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@a.example.com", "password": "pw1234567"},
    )
    access = login_resp.json()["access_token"]

    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "newbie@a.example.com",
            "password": "pw87654321",
            "full_name": "Newbie User",
            "role": "readonly",
        },
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "newbie@a.example.com"
    assert body["full_name"] == "Newbie User"
    assert body["active_clinic_id"] == str(clinic_a)
    assert body["role"] == "readonly"

    # New user can log in.
    login2 = await client.post(
        "/api/auth/login",
        json={"email": "newbie@a.example.com", "password": "pw87654321"},
    )
    assert login2.status_code == 200
