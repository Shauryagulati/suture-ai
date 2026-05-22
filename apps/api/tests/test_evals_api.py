"""Eval-run dashboard API tests (Phase 5a).

Covers list / detail / compare and the basic tenant filter that comes
from EvalRun inheriting ClinicScopedBase.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eval_run import EvalRun, EvalType
from app.utils.context import current_clinic_id, current_user_id
from tests._doc_helpers import auth_headers, make_user_and_login

pytestmark = pytest.mark.asyncio


def _metrics_payload(
    *,
    exact_match: float,
    f1: float,
    per_field: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    return {
        "aggregate": {
            "num_docs": 5,
            "total_field_observations": 80,
            "exact_match_rate": exact_match,
            "f1_macro": f1,
        },
        "per_field": per_field
        or {
            "patient.mrn": {"accuracy": 0.9, "precision": 0.9, "recall": 0.9, "f1": 0.9, "n": 5},
            "diagnosis_codes": {"accuracy": 0.8, "precision": 0.85, "recall": 0.8, "f1": 0.82, "n": 5},
        },
    }


async def _seed_eval_run(
    db: AsyncSession,
    *,
    clinic_id: UUID,
    user_id: UUID,
    prompt_version: str,
    metrics: dict[str, Any],
    model: str = "medgemma1.5",
) -> EvalRun:
    cid_token = current_clinic_id.set(clinic_id)
    uid_token = current_user_id.set(user_id)
    try:
        run = EvalRun(
            eval_type=EvalType.extraction,
            test_set_version="module2-50",
            metrics=metrics,
            num_samples=metrics["aggregate"]["num_docs"],
            run_duration_seconds=42,
            prompt_version=prompt_version,
            model=model,
            notes=f"prompt_version={prompt_version}",
            run_by="test-runner",
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)


async def _login(
    client: AsyncClient, db: AsyncSession, clinic_id: UUID, letter: str = "a"
) -> dict[str, str]:
    from uuid import uuid4

    token = await make_user_and_login(
        client=client,
        db=db,
        email=f"eval-{letter}-{uuid4().hex[:6]}@suture-test.example.com",
        password="eval-test-pw-12",
        clinic_id=clinic_id,
    )
    return auth_headers(token)


async def test_list_returns_all_runs_for_clinic(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
) -> None:
    clinic_a, _ = two_clinics
    headers = await _login(client, db_session, clinic_a)

    await _seed_eval_run(
        db_session,
        clinic_id=clinic_a,
        user_id=test_user,
        prompt_version="v1",
        metrics=_metrics_payload(exact_match=0.78, f1=0.81),
    )
    await _seed_eval_run(
        db_session,
        clinic_id=clinic_a,
        user_id=test_user,
        prompt_version="v2",
        metrics=_metrics_payload(exact_match=0.85, f1=0.88),
    )

    resp = await client.get("/api/evals/", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    # Most-recent first.
    assert body["items"][0]["prompt_version"] == "v2"
    assert body["items"][0]["exact_match_rate"] == pytest.approx(0.85)


async def test_detail_returns_full_metrics(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
) -> None:
    clinic_a, _ = two_clinics
    headers = await _login(client, db_session, clinic_a)
    run = await _seed_eval_run(
        db_session,
        clinic_id=clinic_a,
        user_id=test_user,
        prompt_version="v1",
        metrics=_metrics_payload(exact_match=0.78, f1=0.81),
    )

    resp = await client.get(f"/api/evals/{run.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prompt_version"] == "v1"
    assert body["metrics"]["aggregate"]["exact_match_rate"] == pytest.approx(0.78)
    assert "patient.mrn" in body["metrics"]["per_field"]


async def test_detail_returns_404_for_unknown_id(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    from uuid import uuid4

    clinic_a, _ = two_clinics
    headers = await _login(client, db_session, clinic_a)
    resp = await client.get(f"/api/evals/{uuid4()}", headers=headers)
    assert resp.status_code == 404


async def test_compare_two_runs_yields_per_field_deltas(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
) -> None:
    clinic_a, _ = two_clinics
    headers = await _login(client, db_session, clinic_a)

    run_a = await _seed_eval_run(
        db_session,
        clinic_id=clinic_a,
        user_id=test_user,
        prompt_version="v1",
        metrics=_metrics_payload(
            exact_match=0.70,
            f1=0.72,
            per_field={
                "patient.mrn": {"accuracy": 0.7, "precision": 0.7, "recall": 0.7, "f1": 0.7, "n": 5},
                "diagnosis_codes": {
                    "accuracy": 0.6,
                    "precision": 0.7,
                    "recall": 0.6,
                    "f1": 0.65,
                    "n": 5,
                },
            },
        ),
    )
    run_b = await _seed_eval_run(
        db_session,
        clinic_id=clinic_a,
        user_id=test_user,
        prompt_version="v2",
        metrics=_metrics_payload(
            exact_match=0.85,
            f1=0.87,
            per_field={
                "patient.mrn": {"accuracy": 0.9, "precision": 0.9, "recall": 0.9, "f1": 0.9, "n": 5},
                "diagnosis_codes": {
                    "accuracy": 0.85,
                    "precision": 0.9,
                    "recall": 0.85,
                    "f1": 0.87,
                    "n": 5,
                },
            },
        ),
    )

    resp = await client.get(
        "/api/evals/compare",
        params={"run_a": str(run_a.id), "run_b": str(run_b.id)},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_a_id"] == str(run_a.id)
    assert body["run_b_id"] == str(run_b.id)
    assert body["aggregate_delta"] == pytest.approx(0.15)

    by_field = {f["field"]: f for f in body["fields"]}
    assert by_field["patient.mrn"]["delta"] == pytest.approx(0.2)
    assert by_field["diagnosis_codes"]["delta"] == pytest.approx(0.25)


async def test_compare_returns_404_when_either_run_missing(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
) -> None:
    from uuid import uuid4

    clinic_a, _ = two_clinics
    headers = await _login(client, db_session, clinic_a)
    run = await _seed_eval_run(
        db_session,
        clinic_id=clinic_a,
        user_id=test_user,
        prompt_version="v1",
        metrics=_metrics_payload(exact_match=0.5, f1=0.5),
    )

    resp = await client.get(
        "/api/evals/compare",
        params={"run_a": str(run.id), "run_b": str(uuid4())},
        headers=headers,
    )
    assert resp.status_code == 404


async def test_eval_runs_are_tenant_scoped(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
) -> None:
    """Eval runs created in clinic A are invisible from clinic B."""
    clinic_a, clinic_b = two_clinics
    await _seed_eval_run(
        db_session,
        clinic_id=clinic_a,
        user_id=test_user,
        prompt_version="v1",
        metrics=_metrics_payload(exact_match=0.78, f1=0.81),
    )

    headers_b = await _login(client, db_session, clinic_b, letter="b")
    resp = await client.get("/api/evals/", headers=headers_b)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0
