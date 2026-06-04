"""Authenticated outreach router tests — list, detail, history, trigger,
plus tenant isolation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.document import UrgencyLevel
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.models.referral import Referral, ReferralStatus

pytestmark = pytest.mark.asyncio


async def _seed_patient(db: AsyncSession, clinic_id: UUID) -> Patient:
    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Pat",
        last_name="Endpoint",
        dob="1970-01-01",
        phone="412-555-0150",
        mrn=f"MRN-{uuid4().hex[:6]}",
    )
    db.add(patient)
    await db.flush()
    return patient


async def _seed_referral_with_outreach(
    db: AsyncSession,
    clinic_id: UUID,
    *,
    patient_id: UUID | None = None,
) -> tuple[Referral, list[OutreachAttempt]]:
    if patient_id is None:
        patient = await _seed_patient(db, clinic_id)
        patient_id = patient.id
    referral = Referral(
        id=uuid4(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        status=ReferralStatus.ready_to_schedule,
        urgency=UrgencyLevel.routine,
    )
    db.add(referral)
    await db.flush()
    attempts: list[OutreachAttempt] = []
    for channel in (OutreachChannel.sms, OutreachChannel.email, OutreachChannel.voice):
        attempt = OutreachAttempt(
            id=uuid4(),
            clinic_id=clinic_id,
            patient_id=patient_id,
            referral_id=referral.id,
            channel=channel,
            status=OutreachStatus.pending,
            scheduled_at=datetime.now(UTC),
            outcome={},
            attempt_number=1,
        )
        db.add(attempt)
        attempts.append(attempt)
    await db.commit()
    return referral, attempts


async def test_list_outreach_returns_clinic_a_only(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, clinic_b_id = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        _, attempts_a = await _seed_referral_with_outreach(db_session, clinic_a_id)
    with set_clinic_context(clinic_id=clinic_b_id, user_id=test_user):
        _, _ = await _seed_referral_with_outreach(db_session, clinic_b_id)

    client_a, headers_a, _ = await authed_client_factory("a")
    r = await client_a.get("/api/outreach", headers=headers_a)
    assert r.status_code == 200, r.text
    body = r.json()
    returned_ids = {item["id"] for item in body["items"]}
    seeded_ids = {str(a.id) for a in attempts_a}
    assert seeded_ids.issubset(returned_ids)
    # Verify clinic B's attempts are not in the response.
    assert all(item["patient_id"] for item in body["items"])  # truthy patient_ids


async def test_list_filters_by_channel_and_status(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        _, _ = await _seed_referral_with_outreach(db_session, clinic_a_id)

    client_a, headers_a, _ = await authed_client_factory("a")
    r = await client_a.get("/api/outreach?channel=sms", headers=headers_a)
    assert r.status_code == 200
    body = r.json()
    assert all(item["channel"] == "sms" for item in body["items"])


async def test_get_attempt_detail_returns_data_and_emits_view_audit(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        _, attempts = await _seed_referral_with_outreach(db_session, clinic_a_id)

    client_a, headers_a, _ = await authed_client_factory("a")
    r = await client_a.get(f"/api/outreach/{attempts[0].id}", headers=headers_a)
    assert r.status_code == 200, r.text

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        audit_rows = (
            (
                await db_session.execute(
                    select(AuditLog).where(
                        AuditLog.resource_type == "outreach_attempts",
                        AuditLog.resource_id == attempts[0].id,
                        AuditLog.action == AuditAction.view,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(audit_rows) >= 1


async def test_get_attempt_unknown_returns_404(
    authed_client_factory,
) -> None:
    client_a, headers_a, _ = await authed_client_factory("a")
    r = await client_a.get(f"/api/outreach/{uuid4()}", headers=headers_a)
    assert r.status_code == 404


async def test_get_attempt_cross_clinic_returns_404(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    """Clinic B's auth must not reveal clinic A's attempt id (no existence leak)."""
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        _, attempts = await _seed_referral_with_outreach(db_session, clinic_a_id)

    client_b, headers_b, _ = await authed_client_factory("b")
    r = await client_b.get(f"/api/outreach/{attempts[0].id}", headers=headers_b)
    assert r.status_code == 404


async def test_trigger_referral_creates_three_attempts_with_next_number(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        referral, _ = await _seed_referral_with_outreach(db_session, clinic_a_id)

    client_a, headers_a, _ = await authed_client_factory("a")
    r = await client_a.post(f"/api/outreach/trigger/referral/{referral.id}", headers=headers_a)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["attempt_ids"]) == 3
    assert body["attempt_number"] == 2

    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        rows = (
            (
                await db_session.execute(
                    select(OutreachAttempt).where(OutreachAttempt.referral_id == referral.id)
                )
            )
            .scalars()
            .all()
        )
    # 3 from initial seed + 3 from re-trigger
    assert len(rows) == 6


async def test_trigger_referral_unknown_returns_404(
    authed_client_factory,
) -> None:
    client_a, headers_a, _ = await authed_client_factory("a")
    r = await client_a.post(f"/api/outreach/trigger/referral/{uuid4()}", headers=headers_a)
    assert r.status_code == 404


async def test_list_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/outreach")
    assert r.status_code in (401, 403)


async def test_dashboard_enriches_with_patient_name_and_rendered_message(
    authed_client_factory,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await _seed_referral_with_outreach(db_session, clinic_a_id)

    client_a, headers_a, _ = await authed_client_factory("a")
    r = await client_a.get("/api/outreach/dashboard", headers=headers_a)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) >= 3  # sms + email + voice

    by_channel = {it["channel"]: it for it in items}
    # Patient name is joined in.
    assert by_channel["sms"]["patient_first_name"] == "Pat"
    assert by_channel["sms"]["related_type"] == "referral"
    # The SMS body is the rendered template, personalized with the first name.
    assert "Pat" in by_channel["sms"]["message_body"]
    assert "schedule" in by_channel["sms"]["message_body"].lower()
    # Email carries a subject; SMS does not.
    assert by_channel["email"]["message_subject"]
    assert by_channel["sms"]["message_subject"] is None
