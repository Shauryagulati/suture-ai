"""Phase 6 — timeline aggregation endpoint."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_timeline_includes_referral_and_task_events(
    authed_client_factory, seeded_referral_a
):
    client_a, headers_a, _ = await authed_client_factory("a")
    # Trigger transition so tasks are created (and audit rows emitted).
    transition_resp = await client_a.post(
        f"/api/referrals/{seeded_referral_a.id}/transition",
        headers=headers_a,
        json={"target": "ready_to_schedule"},
    )
    assert transition_resp.status_code == 200

    resp = await client_a.get(
        f"/api/referrals/{seeded_referral_a.id}/timeline", headers=headers_a
    )
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    resource_types = {e["resource_type"] for e in events}
    assert "referrals" in resource_types or "referral_tasks" in resource_types
    # Sorted ascending by timestamp.
    timestamps = [e["at"] for e in events]
    assert timestamps == sorted(timestamps)
