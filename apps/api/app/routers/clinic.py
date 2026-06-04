"""Clinic settings — read-only clinic profile + membership roster.

Clinic / membership / user are GlobalBase (no tenant guard), so the roster is
explicitly scoped to the caller's active clinic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models.clinic import Clinic
from app.models.clinic_membership import ClinicMembership
from app.models.user import User
from app.schemas.clinic import ClinicMemberOut, ClinicSettingsResponse

router = APIRouter(prefix="/api/clinic", tags=["clinic"])


@router.get("/settings", response_model=ClinicSettingsResponse)
async def clinic_settings(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClinicSettingsResponse:
    clinic = await db.get(Clinic, user.active_clinic_id)
    rows = (
        await db.execute(
            select(ClinicMembership, User)
            .join(User, User.id == ClinicMembership.user_id)
            .where(ClinicMembership.clinic_id == user.active_clinic_id)
        )
    ).all()
    members = [
        ClinicMemberOut(email=u.email, full_name=u.full_name, role=m.role.value) for (m, u) in rows
    ]
    members.sort(key=lambda x: (x.role, x.email))
    return ClinicSettingsResponse(
        clinic_id=user.active_clinic_id,
        clinic_name=clinic.name if clinic is not None else "",
        your_role=user.role,
        members=members,
    )
