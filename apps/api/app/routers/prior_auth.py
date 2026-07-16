"""Prior-auth endpoints — stateless check + packet/appeal lifecycle.

Endpoints (mounted at /api/prior-auth):
- POST   /check                          — stateless RAG determination
- POST   /packet/{referral_id}           — create prior_auths row + render packet PDF
- GET    /                               — list current clinic's prior auths
- GET    /{id}                           — detail (with events) + track_view
- PATCH  /{id}                           — status update, sets follow_up_at on submit
- POST   /{id}/appeal                    — generate appeal letter PDF, set appealing

Storage path for packets/appeals is `apps/api/var/auth_packets/{id}.pdf`.
A future scheduled job (Module 3a) will scan `prior_auths.follow_up_at <
now()` to surface stale auths — no Celery in v1.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.models import (
    InsurancePolicy,
    PriorAuth,
    PriorAuthEvent,
    PriorAuthEventType,
    PriorAuthStatus,
    Referral,
)
from app.schemas.prior_auth import (
    AuthCheckRequest,
    AuthDetermination,
    PacketGenerateRequest,
    PriorAuthAppealRequest,
    PriorAuthDetailRead,
    PriorAuthEventRead,
    PriorAuthRead,
    PriorAuthStatusUpdate,
)
from app.services.prior_auth.appeal import generate_denial_appeal
from app.services.prior_auth.determine import PayerRulesEmptyError, check_prior_auth
from app.services.prior_auth.packet import generate_auth_packet
from app.utils.audit import track_view

router = APIRouter(prefix="/api/prior-auth", tags=["prior-auth"])

# Packets/appeals are persisted to a dev-local directory under apps/api/var/.
# Production will swap this for an S3-compatible store (see docs/SECURITY.md).
_PACKET_ROOT = Path(__file__).resolve().parents[2] / "var" / "auth_packets"


def _packet_path(prior_auth_id: UUID) -> Path:
    _PACKET_ROOT.mkdir(parents=True, exist_ok=True)
    return _PACKET_ROOT / f"{prior_auth_id}.pdf"


# ─── POST /check ───────────────────────────────────────────────────────


@router.post("/check", response_model=AuthDetermination)
async def check(
    body: AuthCheckRequest,
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthDetermination:
    """Stateless RAG determination. No prior_auths row is created here."""
    try:
        return await check_prior_auth(db, body)
    except PayerRulesEmptyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ─── POST /packet/{referral_id} ────────────────────────────────────────


@router.post(
    "/packet/{referral_id}",
    status_code=status.HTTP_201_CREATED,
)
async def generate_packet(
    referral_id: UUID,
    body: PacketGenerateRequest,
    inline: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Run determination, persist a prior_auths row, write the PDF, return either
    the JSON record (default) or the PDF inline (`?inline=true`).
    """
    referral = await db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=404, detail="referral not found")

    # Look up the patient's primary payer — packet generation needs a payer.
    primary = (
        await db.execute(
            select(InsurancePolicy)
            .where(InsurancePolicy.patient_id == referral.patient_id)
            .where(InsurancePolicy.is_primary.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    if primary is None:
        raise HTTPException(status_code=409, detail="no primary insurance on file for this patient")

    summary = body.clinical_summary or referral.notes
    try:
        determination = await check_prior_auth(
            db,
            AuthCheckRequest(
                payer_name=primary.payer_name,
                procedure_codes=list(referral.procedure_codes),
                diagnosis_codes=list(referral.diagnosis_codes),
                clinical_summary=summary,
            ),
        )
    except PayerRulesEmptyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    initial_status = (
        PriorAuthStatus.required if determination.auth_required else PriorAuthStatus.not_needed
    )
    prior_auth = PriorAuth(
        referral_id=referral.id,
        patient_id=referral.patient_id,
        payer_name=primary.payer_name,
        payer_id=primary.payer_id,
        member_id=primary.member_id,
        procedure_codes=list(referral.procedure_codes),
        diagnosis_codes=list(referral.diagnosis_codes),
        auth_required=determination.auth_required,
        auth_required_reasoning=determination.reasoning,
        status=initial_status,
    )
    db.add(prior_auth)
    await db.flush()  # need prior_auth.id for the path + event

    pdf_bytes = await generate_auth_packet(db, referral.id, determination)
    out_path = _packet_path(prior_auth.id)
    out_path.write_bytes(pdf_bytes)
    prior_auth.packet_file_path = str(out_path)

    db.add(
        PriorAuthEvent(
            prior_auth_id=prior_auth.id,
            event_type=PriorAuthEventType.created,
            details={
                "auth_required": determination.auth_required,
                "confidence": determination.confidence,
                "matched_excerpts": len(determination.relevant_policy_excerpts),
            },
            created_by=user.user_id,
        )
    )
    await db.commit()
    await db.refresh(prior_auth)

    if inline:
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="auth-packet-{prior_auth.id}.pdf"',
            },
        )
    return Response(
        content=PriorAuthRead.model_validate(prior_auth).model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_201_CREATED,
    )


# ─── GET / ─────────────────────────────────────────────────────────────


@router.get("/", response_model=list[PriorAuthRead])
async def list_prior_auths(
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PriorAuthRead]:
    """List the current clinic's prior auths. Tenant guard scopes the query."""
    rows = (
        (await db.execute(select(PriorAuth).order_by(PriorAuth.created_at.desc()))).scalars().all()
    )

    # Audit the list view at the connection level. List endpoint returns
    # PHI-adjacent metadata so we record an unspecified-resource view.
    conn = await db.connection()
    await conn.run_sync(
        lambda sync_conn: track_view(sync_conn, resource_type="prior_auths", resource_id=None)
    )
    await db.commit()
    return [PriorAuthRead.model_validate(r) for r in rows]


# ─── GET /{id} ─────────────────────────────────────────────────────────


@router.get("/{prior_auth_id}", response_model=PriorAuthDetailRead)
async def get_prior_auth(
    prior_auth_id: UUID,
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PriorAuthDetailRead:
    prior_auth = await db.get(PriorAuth, prior_auth_id)
    if prior_auth is None:
        raise HTTPException(status_code=404, detail="prior_auth not found")

    events = list(
        (
            await db.execute(
                select(PriorAuthEvent)
                .where(PriorAuthEvent.prior_auth_id == prior_auth.id)
                .order_by(PriorAuthEvent.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    conn = await db.connection()
    await conn.run_sync(
        lambda sync_conn: track_view(
            sync_conn, resource_type="prior_auths", resource_id=prior_auth.id
        )
    )
    await db.commit()

    base = PriorAuthRead.model_validate(prior_auth).model_dump()
    return PriorAuthDetailRead(
        **base,
        events=[PriorAuthEventRead.model_validate(e) for e in events],
    )


# ─── PATCH /{id} ───────────────────────────────────────────────────────


def _event_for_status(new_status: PriorAuthStatus) -> PriorAuthEventType | None:
    return {
        PriorAuthStatus.submitted: PriorAuthEventType.submitted,
        PriorAuthStatus.approved: PriorAuthEventType.approved,
        PriorAuthStatus.denied: PriorAuthEventType.denied,
        PriorAuthStatus.appealing: PriorAuthEventType.appeal_submitted,
        PriorAuthStatus.appeal_approved: PriorAuthEventType.appeal_approved,
        PriorAuthStatus.appeal_denied: PriorAuthEventType.appeal_denied,
    }.get(new_status)


async def _typical_turnaround(db: AsyncSession, payer_name: str, cpts: list[str]) -> int | None:
    """Look up max typical_turnaround_days across matched payer_rules rows."""
    from app.models import PayerRule

    rows = (
        (
            await db.execute(
                select(PayerRule.typical_turnaround_days).where(
                    PayerRule.payer_name == payer_name,
                    PayerRule.procedure_code.in_(cpts),
                )
            )
        )
        .scalars()
        .all()
    )
    days = [d for d in rows if d is not None]
    return max(days) if days else None


@router.patch("/{prior_auth_id}", response_model=PriorAuthRead)
async def update_status(
    prior_auth_id: UUID,
    body: PriorAuthStatusUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PriorAuthRead:
    prior_auth = await db.get(PriorAuth, prior_auth_id)
    if prior_auth is None:
        raise HTTPException(status_code=404, detail="prior_auth not found")

    now = datetime.now(UTC)
    prior_auth.status = body.status
    if body.auth_number is not None:
        prior_auth.auth_number = body.auth_number

    if body.status == PriorAuthStatus.submitted:
        prior_auth.submitted_at = now
        days = await _typical_turnaround(
            db, prior_auth.payer_name, list(prior_auth.procedure_codes)
        )
        if days is not None:
            prior_auth.follow_up_at = now + timedelta(days=days)
    elif body.status == PriorAuthStatus.approved:
        prior_auth.approved_at = now
        prior_auth.follow_up_at = None
    elif body.status == PriorAuthStatus.denied:
        prior_auth.denied_at = now

    event_type = _event_for_status(body.status)
    if event_type is not None:
        details: dict[str, object] = {"status": body.status.value}
        if body.auth_number:
            details["auth_number_set"] = True
        if body.denial_reason and body.status == PriorAuthStatus.denied:
            details["denial_reason"] = body.denial_reason
        db.add(
            PriorAuthEvent(
                prior_auth_id=prior_auth.id,
                event_type=event_type,
                details=details,
                created_by=user.user_id,
            )
        )

    await db.commit()
    await db.refresh(prior_auth)
    return PriorAuthRead.model_validate(prior_auth)


# ─── POST /{id}/appeal ─────────────────────────────────────────────────


@router.post("/{prior_auth_id}/appeal")
async def appeal(
    prior_auth_id: UUID,
    body: PriorAuthAppealRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    prior_auth = await db.get(PriorAuth, prior_auth_id)
    if prior_auth is None:
        raise HTTPException(status_code=404, detail="prior_auth not found")
    if prior_auth.status not in {
        PriorAuthStatus.denied,
        PriorAuthStatus.appeal_denied,
    }:
        raise HTTPException(
            status_code=409,
            detail=f"can only appeal a denied auth (current status: {prior_auth.status.value})",
        )

    pdf_bytes = await generate_denial_appeal(db, prior_auth.id, body.denial_reason)

    prior_auth.status = PriorAuthStatus.appealing
    db.add(
        PriorAuthEvent(
            prior_auth_id=prior_auth.id,
            event_type=PriorAuthEventType.appeal_submitted,
            details={"denial_reason": body.denial_reason},
            created_by=user.user_id,
        )
    )
    await db.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="appeal-{prior_auth.id}.pdf"',
        },
    )
