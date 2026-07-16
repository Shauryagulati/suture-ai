"""End-to-end tests for the /api/prior-auth router.

Covers happy paths + tenant isolation. The LLM and embedding providers
are stubbed so the suite runs without Ollama.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import (
    ClinicMembership,
    InsurancePolicy,
    MembershipRole,
    Patient,
    PriorAuth,
    PriorAuthEvent,
    PriorAuthEventType,
    PriorAuthStatus,
    Referral,
    User,
    VerificationStatus,
)
from app.utils.security import hash_password
from tests.prior_auth_helpers import (
    FakeEmbeddingProvider,
    FakeLLMProvider,
    cleanup_prior_auth_tables,
    insert_payer_rule,
    unit_vector,
)

pytestmark = pytest.mark.asyncio

_PASSWORD = "suture_dev_123"


@pytest.fixture
async def _clean() -> None:
    await cleanup_prior_auth_tables(async_session_maker)
    yield
    await cleanup_prior_auth_tables(async_session_maker)


@pytest.fixture
def stub_providers(monkeypatch: pytest.MonkeyPatch) -> FakeLLMProvider:
    """Patch LLM + embedding providers used by determine.py."""
    fake_llm = FakeLLMProvider(
        response_text='{"reasoning": "PA required for LHC.", "confidence": 0.9, "supports_structured_result": true}'
    )
    fake_emb = FakeEmbeddingProvider(vector_fn=lambda _i, _t: unit_vector(0))
    monkeypatch.setattr("app.services.prior_auth.determine.get_llm_provider", lambda: fake_llm)
    monkeypatch.setattr(
        "app.services.prior_auth.determine.get_embedding_provider", lambda: fake_emb
    )
    return fake_llm


async def _login(client: AsyncClient, email: str) -> str:
    resp = await client.post("/api/auth/login", json={"email": email, "password": _PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _make_admin(db: AsyncSession, *, email: str, clinic_id: UUID) -> User:
    user = User(
        id=uuid4(),
        email=email,
        hashed_password=hash_password(_PASSWORD),
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


async def _seed_clinic_data(db: AsyncSession, clinic_id: UUID) -> tuple[UUID, UUID]:
    """Insert payer rule + patient + insurance + referral. Returns (patient_id, referral_id)."""
    await insert_payer_rule(
        db,
        payer_name="Highmark BCBS PA",
        cpt="93458",
        auth_required=True,
        embedding=unit_vector(0),
        guidelines_text="Highmark commercial PPO: 93458 requires PA. Documentation must include prior non-invasive testing.",
        required_documents=["Non-invasive study", "CCS class"],
        common_denial_reasons=["no prior non-invasive testing"],
        typical_turnaround_days=5,
    )

    patient = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name="Test",
        last_name="Patient",
        dob="1960-01-01",
        phone="412-555-0001",
        mrn=f"MRN-{clinic_id.hex[:8]}",
    )
    db.add(patient)
    await db.flush()
    db.add(
        InsurancePolicy(
            clinic_id=clinic_id,
            patient_id=patient.id,
            payer_name="Highmark BCBS PA",
            payer_id="HMK",
            member_id=f"HMK-{clinic_id.hex[:8]}",
            is_primary=True,
            verification_status=VerificationStatus.verified,
        )
    )
    referral = Referral(
        clinic_id=clinic_id,
        patient_id=patient.id,
        procedure_codes=["93458"],
        diagnosis_codes=["I25.10"],
        notes="Stable angina, abnormal stress test.",
    )
    db.add(referral)
    await db.commit()
    return patient.id, referral.id


# ─── /check ────────────────────────────────────────────────────────────


async def test_check_returns_determination(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    stub_providers: FakeLLMProvider,
    _clean: None,
) -> None:
    clinic_a, _ = two_clinics
    await _make_admin(db_session, email="a@x.example.com", clinic_id=clinic_a)
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        await insert_payer_rule(
            db_session,
            payer_name="Highmark BCBS PA",
            cpt="93458",
            auth_required=True,
            embedding=unit_vector(0),
            guidelines_text="Highmark requires PA for 93458.",
            required_documents=["Non-invasive study"],
            common_denial_reasons=["no non-invasive testing"],
            typical_turnaround_days=5,
        )

    token = await _login(client, "a@x.example.com")
    resp = await client.post(
        "/api/prior-auth/check",
        json={
            "payer_name": "Highmark BCBS PA",
            "procedure_codes": ["93458"],
            "diagnosis_codes": ["I25.10"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["auth_required"] is True
    assert body["typical_turnaround_days"] == 5
    assert "Non-invasive study" in body["required_documents"]
    assert len(body["relevant_policy_excerpts"]) >= 1


# ─── /packet ───────────────────────────────────────────────────────────


async def test_packet_creates_prior_auth_row_and_event(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    stub_providers: FakeLLMProvider,
    _clean: None,
) -> None:
    clinic_a, _ = two_clinics
    await _make_admin(db_session, email="a@x.example.com", clinic_id=clinic_a)
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        _patient_id, referral_id = await _seed_clinic_data(db_session, clinic_a)

    token = await _login(client, "a@x.example.com")
    resp = await client.post(
        f"/api/prior-auth/packet/{referral_id}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["referral_id"] == str(referral_id)
    assert body["status"] == "required"
    assert body["auth_required"] is True
    # A packet was generated, but the absolute server path is never exposed.
    assert body["packet_available"] is True
    assert "packet_file_path" not in body
    assert "/var/auth_packets/" not in resp.text

    # Confirm the PriorAuthEvent.created row was emitted.
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        events = (
            (
                await db_session.execute(
                    select(PriorAuthEvent).where(PriorAuthEvent.prior_auth_id == UUID(body["id"]))
                )
            )
            .scalars()
            .all()
        )
    assert len(events) == 1
    assert events[0].event_type == PriorAuthEventType.created


# ─── GET / and tenant isolation ────────────────────────────────────────


async def test_list_only_returns_current_clinic(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    stub_providers: FakeLLMProvider,
    _clean: None,
) -> None:
    clinic_a, clinic_b = two_clinics
    await _make_admin(db_session, email="a@x.example.com", clinic_id=clinic_a)
    await _make_admin(db_session, email="b@x.example.com", clinic_id=clinic_b)

    # Seed one prior_auth per clinic.
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        pa_a = PriorAuth(
            clinic_id=clinic_a,
            patient_id=(await _insert_patient(db_session, clinic_a, "A", "AA")),
            payer_name="Highmark BCBS PA",
            procedure_codes=["93458"],
            diagnosis_codes=["I25.10"],
            auth_required=True,
            status=PriorAuthStatus.required,
        )
        db_session.add(pa_a)
        await db_session.commit()
    with set_clinic_context(clinic_id=clinic_b):  # type: ignore[operator]
        pa_b = PriorAuth(
            clinic_id=clinic_b,
            patient_id=(await _insert_patient(db_session, clinic_b, "B", "BB")),
            payer_name="UPMC Health Plan",
            procedure_codes=["93620"],
            diagnosis_codes=["I47.2"],
            auth_required=True,
            status=PriorAuthStatus.required,
        )
        db_session.add(pa_b)
        await db_session.commit()

    token_a = await _login(client, "a@x.example.com")
    resp = await client.get("/api/prior-auth/", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["payer_name"] == "Highmark BCBS PA"


async def test_tenant_isolation_get_by_id_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    stub_providers: FakeLLMProvider,
    _clean: None,
) -> None:
    """Clinic A's token must NOT be able to read clinic B's prior_auth row by ID."""
    clinic_a, clinic_b = two_clinics
    await _make_admin(db_session, email="a@x.example.com", clinic_id=clinic_a)
    await _make_admin(db_session, email="b@x.example.com", clinic_id=clinic_b)

    with set_clinic_context(clinic_id=clinic_b):  # type: ignore[operator]
        pa_b = PriorAuth(
            clinic_id=clinic_b,
            patient_id=(await _insert_patient(db_session, clinic_b, "B", "BB")),
            payer_name="UPMC Health Plan",
            procedure_codes=["93458"],
            diagnosis_codes=["I25.10"],
            auth_required=True,
            status=PriorAuthStatus.required,
        )
        db_session.add(pa_b)
        await db_session.commit()
        pa_b_id = pa_b.id

    token_a = await _login(client, "a@x.example.com")
    resp = await client.get(
        f"/api/prior-auth/{pa_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404, resp.text


# ─── PATCH /{id} ───────────────────────────────────────────────────────


async def test_patch_status_submitted_sets_follow_up_at(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    stub_providers: FakeLLMProvider,
    _clean: None,
) -> None:
    clinic_a, _ = two_clinics
    await _make_admin(db_session, email="a@x.example.com", clinic_id=clinic_a)
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        _patient_id, referral_id = await _seed_clinic_data(db_session, clinic_a)
    token = await _login(client, "a@x.example.com")
    create = await client.post(
        f"/api/prior-auth/packet/{referral_id}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create.status_code == 201, create.text
    pa_id = create.json()["id"]

    patch = await client.patch(
        f"/api/prior-auth/{pa_id}",
        json={"status": "submitted", "auth_number": "AUTH-1234"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["status"] == "submitted"
    assert body["auth_number"] == "AUTH-1234"
    assert body["submitted_at"] is not None
    assert body["follow_up_at"] is not None  # turnaround = 5 days from the seed

    # Verify a submitted event was appended.
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        events = (
            (
                await db_session.execute(
                    select(PriorAuthEvent).where(PriorAuthEvent.prior_auth_id == UUID(pa_id))
                )
            )
            .scalars()
            .all()
        )
    event_types = {e.event_type for e in events}
    assert PriorAuthEventType.created in event_types
    assert PriorAuthEventType.submitted in event_types


# ─── /{id}/appeal ──────────────────────────────────────────────────────


async def test_appeal_returns_pdf_and_advances_status(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    set_clinic_context: object,
    stub_providers: FakeLLMProvider,
    _clean: None,
) -> None:
    clinic_a, _ = two_clinics
    await _make_admin(db_session, email="a@x.example.com", clinic_id=clinic_a)
    with set_clinic_context(clinic_id=clinic_a):  # type: ignore[operator]
        _patient_id, referral_id = await _seed_clinic_data(db_session, clinic_a)
    token = await _login(client, "a@x.example.com")
    create = await client.post(
        f"/api/prior-auth/packet/{referral_id}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    pa_id = create.json()["id"]
    # Move to denied first — appeal requires it.
    await client.patch(
        f"/api/prior-auth/{pa_id}",
        json={"status": "denied", "denial_reason": "Stable patient — no urgent indication."},
        headers={"Authorization": f"Bearer {token}"},
    )

    appeal_resp = await client.post(
        f"/api/prior-auth/{pa_id}/appeal",
        json={"denial_reason": "Stable patient — no urgent indication."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert appeal_resp.status_code == 200, appeal_resp.text
    assert appeal_resp.headers["content-type"].startswith("application/pdf")
    assert appeal_resp.content.startswith(b"%PDF-")

    # Status advanced to appealing.
    detail = await client.get(
        f"/api/prior-auth/{pa_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert detail.json()["status"] == "appealing"


# ─── helpers ───────────────────────────────────────────────────────────


async def _insert_patient(db: AsyncSession, clinic_id: UUID, first: str, last: str) -> UUID:
    p = Patient(
        id=uuid4(),
        clinic_id=clinic_id,
        first_name=first,
        last_name=last,
        dob="1965-01-01",
        phone="555-0000",
    )
    db.add(p)
    await db.commit()
    return p.id
