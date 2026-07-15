"""End-to-end /api/analytics tests + tenant isolation.

The tenant guard is the load-bearing safety net for these endpoints.
The isolation tests are HIPAA-class — a failure here is a hard stop."""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DocumentStatus,
    OutreachStatus,
    PriorAuthStatus,
    ReferralStatus,
    UrgencyLevel,
)
from tests.analytics_helpers import (
    make_document,
    make_outreach,
    make_patient,
    make_prior_auth,
    make_referral,
)

pytestmark = pytest.mark.asyncio


async def _seed_at_risk_in(
    db_session: AsyncSession, clinic_id: UUID, test_user: UUID, set_clinic_context
) -> UUID:
    """Seed one at-risk patient + referral + 3 failed outreaches in clinic_id."""
    with set_clinic_context(clinic_id=clinic_id, user_id=test_user):
        p = make_patient(clinic_id=clinic_id, phone="", email=None)
        db_session.add(p)
        await db_session.flush()
        db_session.add(
            make_referral(
                clinic_id=clinic_id,
                patient_id=p.id,
                urgency=UrgencyLevel.stat,
                status=ReferralStatus.needs_review,
            )
        )
        for n in range(1, 4):
            db_session.add(
                make_outreach(
                    clinic_id=clinic_id,
                    patient_id=p.id,
                    status=OutreachStatus.failed,
                    attempt_number=n,
                )
            )
        await db_session.commit()
        return p.id


async def test_dashboard_returns_full_payload_shape(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
    authed_client_factory,
):
    clinic_a, _ = two_clinics
    client, headers, _ = await authed_client_factory("a")
    await _seed_at_risk_in(db_session, clinic_a, test_user, set_clinic_context)

    resp = await client.get("/api/analytics/dashboard", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"leakage", "payer_friction", "referral_quality", "roi"}
    assert body["leakage"]["threshold"] == 70
    assert body["leakage"]["at_risk_count"] >= 1
    assert "rows" in body["payer_friction"]
    assert "rows" in body["referral_quality"]
    assert {"from_date", "to_date", "documents_processed", "hours_saved"} <= set(body["roi"].keys())


async def test_leakage_endpoint_orders_by_score_desc(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
    authed_client_factory,
):
    clinic_a, _ = two_clinics
    client, headers, _ = await authed_client_factory("a")
    await _seed_at_risk_in(db_session, clinic_a, test_user, set_clinic_context)
    resp = await client.get("/api/analytics/leakage", headers=headers)
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    assert rows == sorted(rows, key=lambda r: r["score"], reverse=True)


async def test_roi_with_explicit_date_range(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
    authed_client_factory,
):
    client, headers, _ = await authed_client_factory("a")
    resp = await client.get("/api/analytics/roi?from=2026-01-01&to=2026-12-31", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["from_date"] == "2026-01-01"
    assert body["to_date"] == "2026-12-31"


async def test_roi_counts_documents_in_terminal_success_states(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
    authed_client_factory,
):
    """documents_processed counts docs the pipeline completed.

    Regression: the count filtered on DocumentStatus.processed, a status
    nothing ever writes — the ROI card read zero forever. Docs terminate at
    classified / extracted / reviewed (error and in-flight states excluded).
    """
    clinic_a, _ = two_clinics
    client, headers, _ = await authed_client_factory("a")
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        for doc_status in (
            DocumentStatus.classified,
            DocumentStatus.extracted,
            DocumentStatus.reviewed,
            DocumentStatus.error,       # excluded: pipeline failed
            DocumentStatus.classifying,  # excluded: in flight
        ):
            db_session.add(make_document(clinic_id=clinic_a, status=doc_status))
        await db_session.commit()

    resp = await client.get("/api/analytics/roi?from=2026-01-01&to=2026-12-31", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["documents_processed"] == 3
    assert body["hours_saved"] == 0.75  # 3 docs x 15 min


async def test_unauthenticated_request_is_rejected(client: AsyncClient):
    resp = await client.get("/api/analytics/dashboard")
    assert resp.status_code in (401, 403)


# ─── HIPAA-CLASS: tenant isolation ──────────────────────────────────────


async def test_clinic_a_cannot_see_clinic_b_leakage(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
    authed_client_factory,
):
    _clinic_a, clinic_b = two_clinics
    client_a, headers_a, _ = await authed_client_factory("a")
    client_b, headers_b, _ = await authed_client_factory("b")

    b_patient = await _seed_at_risk_in(db_session, clinic_b, test_user, set_clinic_context)

    resp_a = await client_a.get("/api/analytics/leakage", headers=headers_a)
    assert resp_a.status_code == 200
    a_rows = resp_a.json()["rows"]
    assert all(r["patient_id"] != str(b_patient) for r in a_rows), (
        "clinic A leaked a patient_id from clinic B — HIPAA violation"
    )
    assert len(a_rows) == 0

    resp_b = await client_b.get("/api/analytics/leakage", headers=headers_b)
    assert resp_b.status_code == 200
    b_rows = resp_b.json()["rows"]
    assert any(r["patient_id"] == str(b_patient) for r in b_rows)


async def test_clinic_a_cannot_see_clinic_b_payer_friction(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
    authed_client_factory,
):
    _clinic_a, clinic_b = two_clinics
    client_a, headers_a, _ = await authed_client_factory("a")
    _, _, _ = await authed_client_factory("b")

    with set_clinic_context(clinic_id=clinic_b, user_id=test_user):
        p = make_patient(clinic_id=clinic_b)
        db_session.add(p)
        await db_session.flush()
        db_session.add(
            make_prior_auth(
                clinic_id=clinic_b,
                patient_id=p.id,
                payer_name="ClinicB-Only-Payer",
                status=PriorAuthStatus.approved,
            )
        )
        await db_session.commit()

    resp_a = await client_a.get("/api/analytics/payer-friction", headers=headers_a)
    assert resp_a.status_code == 200
    names = [r["payer_name"] for r in resp_a.json()["rows"]]
    assert "ClinicB-Only-Payer" not in names, "payer name leaked across clinics"
