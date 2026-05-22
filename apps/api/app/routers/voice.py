"""Voice agent (Ember / Module 6) routes.

Routes:

- GET    /api/voice/calls/active          — list non-terminal calls for the clinic
- GET    /api/voice/calls/{call_id}/transcript — persisted decrypted transcript
- GET    /api/voice/calls/{call_id}/token — fresh patient LiveKit access token
- POST   /api/voice/calls/{call_id}/start — re-dispatch the agent
- POST   /api/voice/calls/{call_id}/end   — force-terminate
- WS     /api/voice/calls/{call_id}/stream — live transcript via Redis pub/sub

All routes are tenant-scoped via `get_current_user` — the SQLAlchemy
guard auto-filters by `current_clinic_id`. Cross-clinic access returns
404 (we never disclose existence of foreign data).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_maker, get_db
from app.dependencies import (
    CurrentUser,
    WebSocketAuthError,
    get_current_user,
    get_current_user_ws,
)
from app.models.call import Call, CallStatus, CallTranscript
from app.models.patient import Patient
from app.schemas.voice import (
    CallListResponse,
    CallResponse,
    CallTokenResponse,
    EndCallResponse,
    StartCallResponse,
    TranscriptResponse,
)
from app.services.voice.livekit_client import LiveKitClient, room_name_for_call
from app.services.voice.transcript_bus import TranscriptBus
from app.utils.audit import track_view

router = APIRouter(prefix="/api/voice", tags=["voice"])

_TERMINAL_STATUSES = (
    CallStatus.completed,
    CallStatus.failed,
    CallStatus.no_answer,
    CallStatus.voicemail,
)


def _livekit_client() -> LiveKitClient:
    settings = get_settings()
    return LiveKitClient(
        url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )


async def _track_view(db: AsyncSession, *, resource_type: str, resource_id: UUID) -> None:
    from sqlalchemy.orm import Session as SyncSession

    def _emit(sync_session: SyncSession) -> None:
        track_view(
            sync_session.connection(),
            resource_type=resource_type,
            resource_id=resource_id,
        )

    await db.run_sync(_emit)


# ── REST ─────────────────────────────────────────────────────────────


@router.get("/calls/active", response_model=CallListResponse)
async def list_active_calls(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CallListResponse:
    rows = (
        (
            await db.execute(
                select(Call)
                .where(Call.status.not_in(_TERMINAL_STATUSES))
                .order_by(Call.started_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return CallListResponse(items=[CallResponse.from_model(c) for c in rows])


@router.get("/calls/{call_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    call_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TranscriptResponse:
    call = await db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="call not found")
    if call.status not in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="transcript not available — call still in progress",
        )
    transcript = (
        await db.execute(select(CallTranscript).where(CallTranscript.call_id == call_id))
    ).scalar_one_or_none()
    if transcript is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="transcript not found",
        )
    await _track_view(db, resource_type="call_transcripts", resource_id=transcript.id)
    return TranscriptResponse(
        call_id=call_id,
        full_transcript=transcript.full_transcript,
        structured_data=transcript.structured_data,
    )


@router.get("/calls/{call_id}/token", response_model=CallTokenResponse)
async def get_patient_token(
    call_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CallTokenResponse:
    """Mint a fresh LiveKit token for the browser caller page."""
    call = await db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="call not found")
    patient = await db.get(Patient, call.patient_id)
    if patient is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="patient not found"
        )
    settings = get_settings()
    client = _livekit_client()
    try:
        token = client.mint_access_token(
            identity=f"patient:{patient.id}",
            room=room_name_for_call(call_id),
            name=patient.first_name,
        )
    finally:
        await client.aclose()
    return CallTokenResponse(
        room_name=room_name_for_call(call_id),
        livekit_url=settings.livekit_url,
        token=token,
        identity=f"patient:{patient.id}",
    )


@router.post("/calls/{call_id}/start", response_model=StartCallResponse)
async def start_call(
    call_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StartCallResponse:
    """Re-dispatch the Ember agent to an existing call's room.

    Idempotent — if the agent is already in the room, LiveKit silently
    accepts the dispatch as a no-op.
    """
    call = await db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="call not found")
    if call.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"call already in terminal state: {call.status.value}",
        )
    script_context = call.outcome.get("script_context", {})
    client = _livekit_client()
    try:
        dispatched = await client.start_call(
            call_id=call_id,
            clinic_id=call.clinic_id,
            patient_id=call.patient_id,
            script_context=script_context,
        )
    finally:
        await client.aclose()
    return StartCallResponse(
        call_id=call_id,
        room_name=dispatched.room_name,
        redispatched=True,
    )


@router.post("/calls/{call_id}/end", response_model=EndCallResponse)
async def end_call(
    call_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EndCallResponse:
    call = await db.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="call not found")
    if call.status not in _TERMINAL_STATUSES:
        ended = datetime.now(UTC)
        call.status = CallStatus.failed
        call.ended_at = ended
        call.outcome = {
            **(call.outcome or {}),
            "terminated_by_user": True,
            "terminated_by_user_id": str(user.user_id),
        }
        if call.duration_seconds is None and call.started_at is not None:
            call.duration_seconds = max(int((ended - call.started_at).total_seconds()), 0)
        await db.commit()

    # Best-effort room cleanup. Don't fail the request if LiveKit is unreachable.
    client = _livekit_client()
    try:
        try:
            await client.delete_room(room_name_for_call(call_id))
        except Exception:
            pass
    finally:
        await client.aclose()

    assert call.ended_at is not None  # set above or by worker
    return EndCallResponse(call_id=call_id, status=call.status, ended_at=call.ended_at)


# ── WebSocket ────────────────────────────────────────────────────────


@router.websocket("/calls/{call_id}/stream")
async def stream_transcript(
    websocket: WebSocket,
    call_id: UUID,
) -> None:
    """Live transcript stream for an active call.

    Auth: bearer JWT passed as `?token=…` query param. Tenant-scoped:
    the call must belong to the same clinic as the authenticated user.
    """
    await websocket.accept()
    try:
        user = await get_current_user_ws(websocket=websocket, token=websocket.query_params.get("token"))
    except WebSocketAuthError as e:
        await websocket.close(code=e.code, reason=e.reason)
        return

    # Verify the call belongs to this user's clinic. Tenant guard makes
    # the SELECT auto-filter; `None` means foreign-clinic or nonexistent
    # — same 4404 close either way (don't leak existence).
    async with async_session_maker() as session:
        call = await session.get(Call, call_id)
        if call is None or call.clinic_id != user.active_clinic_id:
            await websocket.close(code=4404, reason="call not found")
            return

    settings = get_settings()
    bus = TranscriptBus(redis_url=settings.redis_url)
    try:
        async for msg in bus.subscribe(call_id):
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
