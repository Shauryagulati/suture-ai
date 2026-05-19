"""Verify the JWT's clinic_id drives the tenant guard, and that a JWT
with an unauthorized clinic_id is rejected."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClinicMembership, MembershipRole, Patient, User
from app.utils.security import encode_access_token, hash_password

pytestmark = pytest.mark.asyncio


async def _admin_user(
    db: AsyncSession, *, email: str, clinic_id: UUID, password: str = "pw1234567"
) -> User:
    user = User(
        id=uuid4(),
        email=email,
        hashed_password=hash_password(password),
        full_name="Admin",
    )
    db.add(user)
    await db.flush()
    db.add(
        ClinicMembership(
            user_id=user.id,
            clinic_id=clinic_id,
            role=MembershipRole.admin,
            is_default=True,
        )
    )
    await db.commit()
    return user


async def test_jwt_clinic_id_drives_tenant_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
) -> None:
    """Logging in as clinic-A's admin and hitting /me returns that clinic_id.

    This proves the JWT's clinic_id flows into the request scope. The
    full "clinic A user listing patients sees only clinic A rows" test
    will land in Module 1 when the patients router exists. For now we
    cover the binding via /me.
    """
    clinic_a, clinic_b = two_clinics
    await _admin_user(db_session, email="admin-a@suture-test.example.com", clinic_id=clinic_a)
    await _admin_user(db_session, email="admin-b@suture-test.example.com", clinic_id=clinic_b)
    # Sanity: a patient exists in each clinic.
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        db_session.add(
            Patient(
                clinic_id=clinic_a,
                first_name="A",
                last_name="P",
                dob="1970-01-01",
                phone="555-0001",
            )
        )
        await db_session.commit()
    with set_clinic_context(clinic_id=clinic_b):  # type: ignore[operator]
        db_session.add(
            Patient(
                clinic_id=clinic_b,
                first_name="B",
                last_name="P",
                dob="1970-01-01",
                phone="555-0002",
            )
        )
        await db_session.commit()

    login = await client.post(
        "/api/auth/login",
        json={"email": "admin-a@suture-test.example.com", "password": "pw1234567"},
    )
    access = login.json()["access_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["active_clinic_id"] == str(clinic_a)


async def test_jwt_with_unauthorized_clinic_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    """A JWT claiming a clinic the user has no membership for must be rejected.

    This is the "forged bearer" defense: even if a token is valid-signed,
    if the user_id has no membership for the claimed clinic_id, the
    request is forbidden.
    """
    clinic_a, clinic_b = two_clinics
    user = await _admin_user(
        db_session, email="admin-a@suture-test.example.com", clinic_id=clinic_a
    )

    # Hand-craft a JWT for this user but claiming clinic_b (which they
    # have no membership for).
    forged, _ = encode_access_token(user_id=user.id, clinic_id=clinic_b, role="admin")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 403, resp.text
    assert "membership" in resp.json()["detail"].lower()
