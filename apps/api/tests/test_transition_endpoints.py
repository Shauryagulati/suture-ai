"""Phase 6 — transition endpoints for referrals + discharges."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.referral_task import ReferralTask


@pytest.mark.asyncio
async def test_post_transition_valid_creates_tasks(
    authed_client_factory, db_session, seeded_referral_a, two_clinics, set_clinic_context
):
    clinic_a_id, _ = two_clinics
    client_a, headers_a, _ = await authed_client_factory("a")

    resp = await client_a.post(
        f"/api/referrals/{seeded_referral_a.id}/transition",
        headers=headers_a,
        json={"target": "ready_to_schedule"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ready_to_schedule"

    with set_clinic_context(clinic_id=clinic_a_id):
        tasks = (
            (
                await db_session.execute(
                    select(ReferralTask).where(ReferralTask.referral_id == seeded_referral_a.id)
                )
            )
            .scalars()
            .all()
        )
    assert len(tasks) == 4


@pytest.mark.asyncio
async def test_post_transition_invalid_returns_409(authed_client_factory, seeded_referral_a):
    client_a, headers_a, _ = await authed_client_factory("a")
    resp = await client_a.post(
        f"/api/referrals/{seeded_referral_a.id}/transition",
        headers=headers_a,
        json={"target": "completed"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_post_transition_other_clinic_returns_404(authed_client_factory, seeded_referral_a):
    # User is in clinic B; referral is in clinic A.
    _, headers_b, _ = await authed_client_factory("b")
    client_b, _, _ = await authed_client_factory("b")
    resp = await client_b.post(
        f"/api/referrals/{seeded_referral_a.id}/transition",
        headers=headers_b,
        json={"target": "ready_to_schedule"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_discharge_transition_valid(authed_client_factory, seeded_discharge_a):
    client_a, headers_a, _ = await authed_client_factory("a")
    resp = await client_a.post(
        f"/api/discharges/{seeded_discharge_a.id}/transition",
        headers=headers_a,
        json={"target": "patient_contacted"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "patient_contacted"
