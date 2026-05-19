"""Auth routes — login, refresh, me, register."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user, require_admin
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MembershipSummary,
    MeResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
)
from app.services.auth import (
    EmailAlreadyExistsError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    NoMembershipError,
    authenticate,
    refresh_access_token,
    register_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    try:
        result = await authenticate(db, email=body.email, password=body.password)
    except (InvalidCredentialsError, NoMembershipError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except InactiveUserError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e

    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        user_id=result.user_id,
        active_clinic_id=result.active_clinic_id,
        role=result.role,
        memberships=[
            MembershipSummary(clinic_id=m.clinic_id, role=m.role.value, is_default=m.is_default)
            for m in result.memberships
        ],
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    try:
        token = await refresh_access_token(db, refresh_token=body.refresh_token)
    except InvalidRefreshTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    return RefreshResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        active_clinic_id=user.active_clinic_id,
        role=user.role,
    )


@router.post(
    "/register",
    response_model=MeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    caller: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Admin-only: create a new user inside the caller's clinic."""
    try:
        new_user = await register_user(
            db,
            caller_clinic_id=caller.active_clinic_id,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            role=body.role,
        )
    except EmailAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    return MeResponse(
        user_id=new_user.id,
        email=new_user.email,
        full_name=new_user.full_name,
        active_clinic_id=caller.active_clinic_id,
        role=body.role,
    )
