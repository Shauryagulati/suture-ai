"""Extraction review API tests (Phase 2c).

Covers list / detail / PATCH / approve, tenant isolation, and audit-row
side-effects for the new endpoints in `app.routers.extractions`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_invocation import AiInvocation, InvocationType
from app.models.audit_log import AuditLog
from app.models.discharge_summary import DischargeStatus, DischargeSummary
from app.models.document import (
    Document,
    DocumentClassification,
    DocumentStatus,
)
from app.models.document_extraction import DocumentExtraction
from app.models.patient import Patient
from app.models.referral import Referral, ReferralStatus
from app.utils.context import current_clinic_id, current_user_id
from tests._doc_helpers import auth_headers, make_user_and_login

pytestmark = pytest.mark.asyncio


def _ref_payload(mrn: str = "MRN-654235", npi: str = "2423884966") -> dict[str, Any]:
    return {
        "patient": {
            "first_name": "Amy",
            "last_name": "Robinson",
            "dob": "1966-03-13",
            "mrn": mrn,
            "phone": "412-555-1234",
            "address_line1": "33890 Jennifer Squares",
            "city": "Pittsburgh",
            "state": "PA",
            "zip_code": "15222",
        },
        "insurance": {
            "primary": {
                "payer": "Highmark BCBS PA",
                "member_id": "LBC104332181",
                "group_number": None,
            },
            "secondary": None,
        },
        "referring_provider": {
            "first_name": "Shawn",
            "last_name": "Flowers",
            "npi": npi,
            "practice_name": "Greater Pittsburgh Primary Care",
            "practice_phone": "878-555-6543",
            "practice_fax": "878-555-7517",
        },
        "diagnosis_codes": ["R07.9"],
        "procedure_codes": ["93015"],
        "urgency": "routine",
        "follow_up_window_days": 22,
        "referral_type": "stress_test",
        "clinical_notes_excerpt": "Patient with exertional chest pain.",
    }


def _discharge_payload() -> dict[str, Any]:
    return {
        "patient": {
            "first_name": "Carl",
            "last_name": "Nguyen",
            "dob": "1955-07-04",
            "mrn": "MRN-300100",
            "phone": "412-555-0160",
            "address_line1": None,
            "city": "Pittsburgh",
            "state": "PA",
            "zip_code": "15201",
        },
        "admit_date": "2026-05-15",
        "discharge_date": "2026-05-20",
        "discharging_hospital": "UPMC Presbyterian",
        "attending_physician": {"first_name": "Lena", "last_name": "Park", "npi": "2423884966"},
        "primary_diagnosis": "Acute STEMI",
        "diagnosis_codes": ["I21.09"],
        "procedures_performed": [],
        "medications_changed": [],
        "discharge_type": "post_pci",
        "urgency_tier": "critical",
        "urgent_flags": ["recent_MI"],
        "recommended_specialist": "Cardiology",
        "follow_up_window_days": 7,
    }


async def _seed_extraction(
    db: AsyncSession,
    *,
    clinic_id: UUID,
    user_id: UUID,
    classification: DocumentClassification,
    payload: dict[str, Any],
    missing_fields: list[str] | None = None,
    human_review_required: bool = True,
    field_confidences: dict[str, float] | None = None,
    file_name: str = "ref.pdf",
) -> tuple[DocumentExtraction, Document]:
    """Insert a Document + AiInvocation + DocumentExtraction inside the right tenant context."""
    cid_token = current_clinic_id.set(clinic_id)
    uid_token = current_user_id.set(user_id)
    try:
        doc = Document(
            file_path=f"/tmp/{file_name}",
            file_name=file_name,
            file_size=128,
            mime_type="application/pdf",
            status=DocumentStatus.extracted,
            classification=classification,
            classification_confidence=0.9,
            extracted_text="OCR text body",
            ocr_engine="pypdf",
            uploaded_by=user_id,
        )
        db.add(doc)
        await db.flush()

        inv = AiInvocation(
            invocation_type=InvocationType.extraction,
            model="medgemma1.5",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=10,
            estimated_cost_usd=0.0,
            input_summary="extract...",
            output_summary=None,
            confidence_scores={"prompt_version": "v1", "parse_failed": False},
            document_id=doc.id,
        )
        db.add(inv)
        await db.flush()

        ext = DocumentExtraction(
            document_id=doc.id,
            extraction_data=payload,
            field_confidences=field_confidences or {},
            missing_fields=list(missing_fields or []),
            human_edits=[],
            human_review_required=human_review_required,
            extraction_version=1,
            ai_invocation_id=inv.id,
        )
        db.add(ext)
        await db.commit()
        await db.refresh(ext)
        await db.refresh(doc)
        return ext, doc
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)


async def _login_clinic_user(
    client: AsyncClient, db: AsyncSession, clinic_id: UUID, letter: str = "a"
) -> tuple[dict[str, str], UUID]:
    email = f"reviewer-{letter}-{uuid4().hex[:6]}@suture-test.example.com"
    token = await make_user_and_login(
        client=client,
        db=db,
        email=email,
        password="reviewer-pw-1234",
        clinic_id=clinic_id,
    )
    user_row = (
        await db.execute(
            select(__import__("app.models.user", fromlist=["User"]).User).where(
                __import__("app.models.user", fromlist=["User"]).User.email == email
            )
        )
    ).scalar_one()
    return auth_headers(token), user_row.id


# ---------------------------- list ----------------------------


async def test_list_filters_by_needs_review(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)

    # Two extractions: one needs review, one doesn't.
    await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=_ref_payload(),
        missing_fields=["patient.phone"],
        human_review_required=True,
        file_name="needs.pdf",
    )
    await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=_ref_payload(mrn="MRN-other"),
        missing_fields=[],
        human_review_required=False,
        file_name="clean.pdf",
    )

    # Default: returns both, needs-review first.
    resp = await client.get("/api/extractions/", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0]["document_file_name"] == "needs.pdf"
    assert body["items"][0]["human_review_required"] is True

    # Filter: only needs_review=true.
    resp = await client.get("/api/extractions/?needs_review=true", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["document_file_name"] == "needs.pdf"
    assert body["items"][0]["missing_fields_count"] == 1


# ---------------------------- detail ----------------------------


async def test_detail_returns_full_payload_and_writes_audit(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)
    ext, _ = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=_ref_payload(),
        field_confidences={"patient.dob": 0.95},
        missing_fields=["patient.phone"],
    )

    resp = await client.get(f"/api/extractions/{ext.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["extraction_data"]["patient"]["mrn"] == "MRN-654235"
    assert body["model"] == "medgemma1.5"
    assert body["prompt_version"] == "v1"
    assert body["missing_fields"] == ["patient.phone"]
    assert body["human_edits"] == []

    # Audit row for the view.
    tok = current_clinic_id.set(clinic_a)
    try:
        rows = (
            (
                await db_session.execute(
                    select(AuditLog).where(
                        AuditLog.resource_type == "document_extractions",
                        AuditLog.action == "view",
                    )
                )
            )
            .scalars()
            .all()
        )
    finally:
        current_clinic_id.reset(tok)
    assert len(rows) == 1
    assert rows[0].resource_id == ext.id


async def test_detail_returns_404_for_unknown_id(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, _ = await _login_clinic_user(client, db_session, clinic_a)
    resp = await client.get(f"/api/extractions/{uuid4()}", headers=headers)
    assert resp.status_code == 404


# ---------------------------- PATCH ----------------------------


async def test_patch_appends_to_human_edits_and_updates_data(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)
    ext, _ = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=_ref_payload(),
        missing_fields=["patient.phone"],
        field_confidences={"patient.last_name": 0.85, "patient.phone": 0.0},
    )

    resp = await client.patch(
        f"/api/extractions/{ext.id}",
        headers=headers,
        json={"field_path": "patient.last_name", "new_value": "Smith"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["extraction_data"]["patient"]["last_name"] == "Smith"
    assert len(body["human_edits"]) == 1
    edit = body["human_edits"][0]
    assert edit["field"] == "patient.last_name"
    assert edit["old"] == "Robinson"
    assert edit["new"] == "Smith"
    assert edit["edited_by"] == str(user_id)


async def test_patch_fills_missing_field_bumps_confidence(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    """Editing a path that was on missing_fields should remove it and re-score."""
    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)
    payload = _ref_payload()
    payload["patient"]["phone"] = None
    ext, _ = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=payload,
        missing_fields=["patient.phone"],
        field_confidences={"patient.phone": 0.0},
    )

    resp = await client.patch(
        f"/api/extractions/{ext.id}",
        headers=headers,
        json={"field_path": "patient.phone", "new_value": "412-555-9999"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "patient.phone" not in body["missing_fields"]
    # Validator-passing value → 0.95.
    assert body["field_confidences"]["patient.phone"] == 0.95


async def test_patch_on_approved_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    from datetime import UTC, datetime

    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)
    ext, _ = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=_ref_payload(),
    )
    # Mark approved.
    cid_token = current_clinic_id.set(clinic_a)
    uid_token = current_user_id.set(user_id)
    try:
        ext.human_reviewed_at = datetime.now(UTC)
        ext.human_reviewed_by = user_id
        ext.human_review_required = False
        await db_session.commit()
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)

    resp = await client.patch(
        f"/api/extractions/{ext.id}",
        headers=headers,
        json={"field_path": "patient.last_name", "new_value": "Smith"},
    )
    assert resp.status_code == 409, resp.text


async def test_patch_invalid_path_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)
    ext, _ = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=_ref_payload(),
    )

    resp = await client.patch(
        f"/api/extractions/{ext.id}",
        headers=headers,
        json={"field_path": "no_such_root.deep.path", "new_value": "x"},
    )
    assert resp.status_code == 400, resp.text


# ---------------------------- APPROVE — referral ----------------------------


async def test_approve_referral_creates_referral_and_patient(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)
    ext, doc = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=_ref_payload(),
    )

    resp = await client.post(f"/api/extractions/{ext.id}/approve", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["referral_id"] is not None
    assert body["patient_created"] is True
    assert body["provider_created"] is True

    from app.models.insurance_policy import InsurancePolicy
    from app.models.outreach_attempt import OutreachAttempt
    from app.models.referral_task import ReferralTask

    tok = current_clinic_id.set(clinic_a)
    try:
        referrals = (await db_session.execute(select(Referral))).scalars().all()
        patients = (await db_session.execute(select(Patient))).scalars().all()
        ref = referrals[0]
        tasks = (
            (
                await db_session.execute(
                    select(ReferralTask).where(ReferralTask.referral_id == ref.id)
                )
            )
            .scalars()
            .all()
        )
        outreach = (
            (
                await db_session.execute(
                    select(OutreachAttempt).where(OutreachAttempt.referral_id == ref.id)
                )
            )
            .scalars()
            .all()
        )
        policies = (
            (
                await db_session.execute(
                    select(InsurancePolicy).where(InsurancePolicy.patient_id == ref.patient_id)
                )
            )
            .scalars()
            .all()
        )
    finally:
        current_clinic_id.reset(tok)
    assert len(referrals) == 1
    # Approval engages the workflow: advance through needs_review to
    # ready_to_schedule, which generates tasks and schedules outreach.
    assert ref.status == ReferralStatus.ready_to_schedule
    assert len(tasks) > 0, "referral approval should generate tasks"
    assert len(outreach) > 0, "referral approval should schedule outreach"
    # Extracted primary insurance is persisted so prior-auth packets work.
    assert len(policies) == 1
    assert policies[0].is_primary is True
    assert policies[0].payer_name == "Highmark BCBS PA"
    assert policies[0].member_id == "LBC104332181"  # decrypts via EncryptedString
    assert ref.diagnosis_codes == ["R07.9"]
    assert ref.procedure_codes == ["93015"]

    assert len(patients) == 1
    pat = patients[0]
    assert pat.mrn == "MRN-654235"
    # Encrypted column round-trips via EncryptedString.
    assert pat.dob == "1966-03-13"

    # Extraction is now marked reviewed; document is reviewed.
    await db_session.refresh(ext)
    await db_session.refresh(doc)
    assert ext.human_review_required is False
    assert ext.human_reviewed_by == user_id
    assert ext.human_reviewed_at is not None
    assert doc.status == DocumentStatus.reviewed
    # ai_invocation_id chain stays intact.
    assert ext.ai_invocation_id is not None


async def test_approve_referral_reuses_existing_patient_by_mrn(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)

    # Pre-seed a patient with the MRN we'll use.
    cid_token = current_clinic_id.set(clinic_a)
    uid_token = current_user_id.set(user_id)
    try:
        existing_patient = Patient(
            first_name="Amy",
            last_name="Robinson",
            dob="1966-03-13",
            phone="412-555-1234",
            mrn="MRN-654235",
        )
        db_session.add(existing_patient)
        await db_session.commit()
        existing_id = existing_patient.id
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)

    ext, _ = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=_ref_payload(),
    )

    resp = await client.post(f"/api/extractions/{ext.id}/approve", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["patient_id"] == str(existing_id)
    assert body["patient_created"] is False

    tok = current_clinic_id.set(clinic_a)
    try:
        patients = (await db_session.execute(select(Patient))).scalars().all()
    finally:
        current_clinic_id.reset(tok)
    assert len(patients) == 1  # no new patient row


# ---------------------------- APPROVE — discharge ----------------------------


async def test_approve_discharge_creates_summary_and_advances_to_patient_contacted(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    """Approval auto-engages the workflow: the new DischargeSummary
    transitions to patient_contacted, which spawns tasks + outreach."""
    from app.models.outreach_attempt import OutreachAttempt
    from app.models.referral_task import ReferralTask

    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)
    ext, _ = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.discharge_summary,
        payload=_discharge_payload(),
        file_name="dc.pdf",
    )

    resp = await client.post(f"/api/extractions/{ext.id}/approve", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["discharge_summary_id"] is not None
    assert body["referral_id"] is None
    assert body["patient_created"] is True

    tok = current_clinic_id.set(clinic_a)
    try:
        discharges = (await db_session.execute(select(DischargeSummary))).scalars().all()
        assert len(discharges) == 1
        dis = discharges[0]
        assert dis.status == DischargeStatus.patient_contacted
        assert dis.urgent_flags == ["recent_MI"]
        assert dis.urgency_tier.value == "critical"

        tasks = (
            (
                await db_session.execute(
                    select(ReferralTask).where(ReferralTask.discharge_summary_id == dis.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 4

        attempts = (
            (
                await db_session.execute(
                    select(OutreachAttempt).where(OutreachAttempt.discharge_summary_id == dis.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(attempts) == 3
    finally:
        current_clinic_id.reset(tok)


async def test_approve_already_approved_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)
    ext, _ = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=_ref_payload(),
    )

    first = await client.post(f"/api/extractions/{ext.id}/approve", headers=headers)
    assert first.status_code == 200, first.text
    second = await client.post(f"/api/extractions/{ext.id}/approve", headers=headers)
    assert second.status_code == 409


# ---------------------------- tenant isolation ----------------------------


async def test_tenant_isolation_on_list_detail_patch_approve(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    """Clinic B must not see / mutate clinic A's extraction across any endpoint."""
    clinic_a, clinic_b = two_clinics
    _, user_a = await _login_clinic_user(client, db_session, clinic_a, letter="a")
    headers_b, _ = await _login_clinic_user(client, db_session, clinic_b, letter="b")

    ext_a, _ = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_a,
        classification=DocumentClassification.referral,
        payload=_ref_payload(),
    )

    # B's list is empty.
    resp = await client.get("/api/extractions/", headers=headers_b)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0

    # B's detail → 404.
    resp = await client.get(f"/api/extractions/{ext_a.id}", headers=headers_b)
    assert resp.status_code == 404

    # B's PATCH → 404.
    resp = await client.patch(
        f"/api/extractions/{ext_a.id}",
        headers=headers_b,
        json={"field_path": "patient.last_name", "new_value": "Smith"},
    )
    assert resp.status_code == 404

    # B's approve → 404.
    resp = await client.post(f"/api/extractions/{ext_a.id}/approve", headers=headers_b)
    assert resp.status_code == 404


# ---------------------------- audit ----------------------------


async def test_patch_writes_update_audit_row(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
) -> None:
    clinic_a, _ = two_clinics
    headers, user_id = await _login_clinic_user(client, db_session, clinic_a)
    ext, _ = await _seed_extraction(
        db_session,
        clinic_id=clinic_a,
        user_id=user_id,
        classification=DocumentClassification.referral,
        payload=_ref_payload(),
    )

    resp = await client.patch(
        f"/api/extractions/{ext.id}",
        headers=headers,
        json={"field_path": "patient.last_name", "new_value": "Smith"},
    )
    assert resp.status_code == 200, resp.text

    tok = current_clinic_id.set(clinic_a)
    try:
        rows = (
            (
                await db_session.execute(
                    select(AuditLog).where(
                        AuditLog.resource_type == "document_extractions",
                        AuditLog.action == "update",
                        AuditLog.resource_id == ext.id,
                    )
                )
            )
            .scalars()
            .all()
        )
    finally:
        current_clinic_id.reset(tok)
    assert len(rows) >= 1
    # PHI safety: details JSONB must NOT contain raw field values.
    details = rows[-1].details or {}
    flat = str(details)
    assert "Smith" not in flat
    assert "Robinson" not in flat
