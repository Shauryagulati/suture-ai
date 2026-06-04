"""Extraction service + upload integration tests (Phase 1f).

Covers extract_document() in isolation (mocked LLM) and the auto-extract
hook in the upload route. Tenant isolation is enforced via the SQLAlchemy
session guard.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_invocation import AiInvocation, InvocationType
from app.models.document import (
    Document,
    DocumentClassification,
    DocumentStatus,
)
from app.models.document_extraction import DocumentExtraction
from app.services.extraction.service import extract_document
from app.services.llm import factory as llm_factory
from app.services.llm.ollama import OllamaProvider
from app.utils.context import current_clinic_id, current_user_id
from tests._doc_helpers import (
    auth_headers,
    make_user_and_login,
    patch_llm_provider,
    patch_ocr,
    patch_storage_path,
)

pytestmark = pytest.mark.asyncio

_FAKE_PDF = b"%PDF-1.4\nfixture\n"

_REFERRAL_EXTRACTION_JSON = json.dumps(
    {
        "patient": {
            "first_name": "Amy",
            "last_name": "Robinson",
            "dob": "1966-03-13",
            "mrn": "MRN-654235",
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
            "npi": "2423884966",
            "practice_name": "Greater Pittsburgh Primary Care",
            "practice_phone": "878-555-6543",
            "practice_fax": "878-555-7517",
        },
        "diagnosis_codes": ["R07.9"],
        "procedure_codes": ["93015"],
        "urgency": "routine",
        "follow_up_window_days": 22,
        "referral_type": "stress_test",
        "clinical_notes_excerpt": "Patient with exertional chest pain...",
        "missing_fields": ["insurance.primary.group_number", "insurance.secondary"],
    }
)

_DISCHARGE_EXTRACTION_JSON = json.dumps(
    {
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
        "attending_physician": {
            "first_name": "Lena",
            "last_name": "Park",
            "npi": "2423884966",
        },
        "primary_diagnosis": "Acute STEMI",
        "diagnosis_codes": ["I21.09"],
        "procedures_performed": [{"cpt_code": "92928", "description": "PCI with stent"}],
        "medications_changed": [
            {"action": "started", "name": "Aspirin 81 mg daily"},
        ],
        "discharge_type": "post_pci",
        "urgency_tier": "critical",
        "urgent_flags": ["recent_MI", "post-PCI"],
        "recommended_specialist": "Cardiology",
        "follow_up_window_days": 7,
        "missing_fields": ["patient.address_line1"],
    }
)


def _install_recording_extraction_mock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response_text: str,
    captured: list[dict[str, Any]] | None = None,
    raise_on_call: BaseException | None = None,
    model: str = "medgemma1.5",
) -> None:
    """Patch only the extraction service's LLM. Captures system prompts."""

    def handler(request: httpx.Request) -> httpx.Response:
        if raise_on_call is not None:
            raise raise_on_call
        body = json.loads(request.content) if request.content else {}
        if captured is not None:
            captured.append(body)
        return httpx.Response(200, json={"response": response_text})

    transport = httpx.MockTransport(handler)
    provider = OllamaProvider(model=model, base_url="http://mock-llm")
    provider._client = httpx.AsyncClient(base_url="http://mock-llm", transport=transport)

    llm_factory.get_llm_provider.cache_clear()
    monkeypatch.setattr(
        "app.services.extraction.service.get_llm_provider",
        lambda: provider,
    )


async def _seed_classified_document(
    db_session: AsyncSession,
    clinic_id: UUID,
    user_id: UUID,
    *,
    classification: DocumentClassification = DocumentClassification.referral,
    extracted_text: str = "OCR text body for the document under test.",
) -> Document:
    """Insert a Document at status=classified inside the right tenant context."""
    cid_token = current_clinic_id.set(clinic_id)
    uid_token = current_user_id.set(user_id)
    try:
        doc = Document(
            file_path="/tmp/fixture.pdf",
            file_name="fixture.pdf",
            file_size=len(_FAKE_PDF),
            mime_type="application/pdf",
            status=DocumentStatus.classified,
            classification=classification,
            classification_confidence=0.9,
            extracted_text=extracted_text,
            ocr_engine="pypdf",
            uploaded_by=user_id,
        )
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)
        return doc
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)


# ---------------------------- service-level tests ----------------------------


async def test_extract_referral_writes_extraction_and_invocation(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clinic_a, _ = two_clinics
    doc = await _seed_classified_document(db_session, clinic_a, test_user)

    _install_recording_extraction_mock(monkeypatch, response_text=_REFERRAL_EXTRACTION_JSON)

    cid_token = current_clinic_id.set(clinic_a)
    uid_token = current_user_id.set(test_user)
    try:
        extraction = await extract_document(document_id=doc.id, db=db_session)
        await db_session.commit()
        await db_session.refresh(extraction)
        assert extraction.extraction_data["patient"]["mrn"] == "MRN-654235"
        assert extraction.extraction_data["diagnosis_codes"] == ["R07.9"]
        # `missing_fields` from the LLM is stripped from extraction_data.
        assert "missing_fields" not in extraction.extraction_data
        # …but surfaces on the row.
        assert extraction.missing_fields == [
            "insurance.primary.group_number",
            "insurance.secondary",
        ]
        # Confidences computed deterministically.
        assert extraction.field_confidences["patient.dob"] == 0.95
        assert extraction.field_confidences["referring_provider.npi"] == 0.95
        assert extraction.field_confidences["diagnosis_codes"] == 0.95
        assert extraction.field_confidences["insurance.primary.group_number"] == 0.0
        # human_review_required because of missing_fields.
        assert extraction.human_review_required is True
        assert extraction.human_edits == []

        # AiInvocation row written with invocation_type=extraction.
        inv_rows = (
            (
                await db_session.execute(
                    select(AiInvocation).where(AiInvocation.document_id == doc.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(inv_rows) == 1
        inv = inv_rows[0]
        assert inv.invocation_type == InvocationType.extraction
        assert inv.confidence_scores.get("prompt_version") == "v1"
        assert inv.confidence_scores.get("parse_failed") is False
        assert extraction.ai_invocation_id == inv.id
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)


async def test_extract_invalid_json_writes_parse_failure_row(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clinic_a, _ = two_clinics
    doc = await _seed_classified_document(db_session, clinic_a, test_user)

    _install_recording_extraction_mock(
        monkeypatch, response_text="this is not JSON, just rambling prose"
    )

    cid_token = current_clinic_id.set(clinic_a)
    uid_token = current_user_id.set(test_user)
    try:
        extraction = await extract_document(document_id=doc.id, db=db_session)
        await db_session.commit()
        await db_session.refresh(extraction)
        assert extraction.extraction_data == {}
        assert extraction.field_confidences == {}
        assert extraction.missing_fields == ["__parse_failed__"]
        assert extraction.human_review_required is True

        inv_rows = (
            (
                await db_session.execute(
                    select(AiInvocation).where(AiInvocation.document_id == doc.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(inv_rows) == 1
        assert inv_rows[0].invocation_type == InvocationType.extraction
        assert inv_rows[0].confidence_scores.get("parse_failed") is True
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)


async def test_missing_fields_drive_zero_confidence_for_those_paths(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clinic_a, _ = two_clinics
    doc = await _seed_classified_document(db_session, clinic_a, test_user)

    payload = json.loads(_REFERRAL_EXTRACTION_JSON)
    payload["missing_fields"] = ["patient.phone", "referring_provider.npi"]
    # Even though we still include values, missing_fields wins the score.
    _install_recording_extraction_mock(monkeypatch, response_text=json.dumps(payload))

    cid_token = current_clinic_id.set(clinic_a)
    uid_token = current_user_id.set(test_user)
    try:
        extraction = await extract_document(document_id=doc.id, db=db_session)
        await db_session.commit()
        await db_session.refresh(extraction)
        assert extraction.field_confidences["patient.phone"] == 0.0
        assert extraction.field_confidences["referring_provider.npi"] == 0.0
        assert extraction.missing_fields == ["patient.phone", "referring_provider.npi"]
        assert extraction.human_review_required is True
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)


async def test_discharge_uses_the_discharge_prompt(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clinic_a, _ = two_clinics
    doc = await _seed_classified_document(
        db_session,
        clinic_a,
        test_user,
        classification=DocumentClassification.discharge_summary,
    )

    captured: list[dict[str, Any]] = []
    _install_recording_extraction_mock(
        monkeypatch, response_text=_DISCHARGE_EXTRACTION_JSON, captured=captured
    )

    cid_token = current_clinic_id.set(clinic_a)
    uid_token = current_user_id.set(test_user)
    try:
        await extract_document(document_id=doc.id, db=db_session)
        await db_session.commit()
    finally:
        current_clinic_id.reset(cid_token)
        current_user_id.reset(uid_token)

    assert len(captured) == 1
    system_prompt = captured[0]["system"]
    # Snapshot anchors: discharge-specific schema fields appear in the prompt;
    # referral-only fields do not.
    assert "hospital discharge summary" in system_prompt
    assert "discharge_date" in system_prompt
    assert "urgency_tier" in system_prompt
    assert "referring_provider" not in system_prompt


# ---------------------------- upload-integration tests ----------------------------


async def test_upload_auto_triggers_extraction_for_referral(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="Referral text body for cardiology consult.")
    patch_llm_provider(
        monkeypatch,
        response_text=(
            '{"classification": "referral", "confidence": 0.9, "reasoning": "REFERRAL header"}'
        ),
        extraction_response_text=_REFERRAL_EXTRACTION_JSON,
    )
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="upl-1@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )

    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token),
        files={"file": ("ref.pdf", _FAKE_PDF, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    doc_id = UUID(resp.json()["id"])

    # Extraction runs in a background task; read the persisted state.
    tok = current_clinic_id.set(clinic_a)
    try:
        db_session.expire_all()
        doc = await db_session.get(Document, doc_id)
        rows = (
            (
                await db_session.execute(
                    select(DocumentExtraction).where(DocumentExtraction.document_id == doc_id)
                )
            )
            .scalars()
            .all()
        )
    finally:
        current_clinic_id.reset(tok)

    assert doc is not None and doc.status == DocumentStatus.extracted
    assert len(rows) == 1
    extraction = rows[0]
    assert extraction.extraction_data["patient"]["mrn"] == "MRN-654235"
    assert extraction.human_review_required is True  # has missing_fields
    assert extraction.clinic_id == clinic_a


async def test_upload_extraction_failure_keeps_doc_at_classified(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A raising LLM call must NOT bubble into a 500 on upload."""
    clinic_a, _ = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="Referral text body.")

    # Wire classification normally — patch extraction to RAISE.
    patch_llm_provider(
        monkeypatch,
        response_text=('{"classification": "referral", "confidence": 0.9, "reasoning": "r"}'),
    )
    _install_recording_extraction_mock(
        monkeypatch,
        response_text="",  # ignored — handler raises before this is used
        raise_on_call=httpx.ConnectError("simulated outage"),
    )

    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="upl-2@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )
    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token),
        files={"file": ("ref.pdf", _FAKE_PDF, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    doc_id = UUID(resp.json()["id"])

    tok = current_clinic_id.set(clinic_a)
    try:
        db_session.expire_all()
        doc = await db_session.get(Document, doc_id)
        extractions = (
            (
                await db_session.execute(
                    select(DocumentExtraction).where(DocumentExtraction.document_id == doc_id)
                )
            )
            .scalars()
            .all()
        )
    finally:
        current_clinic_id.reset(tok)
    # Extraction raised in the background; doc falls back to `classified`, NOT `error`.
    assert doc is not None and doc.status == DocumentStatus.classified
    assert extractions == []  # nothing was persisted


async def test_extraction_is_tenant_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Clinic B must NOT see clinic A's DocumentExtraction via the session guard."""
    clinic_a, clinic_b = two_clinics
    patch_storage_path(monkeypatch, tmp_path)
    patch_ocr(monkeypatch, text="Referral text body.")
    patch_llm_provider(
        monkeypatch,
        response_text=('{"classification": "referral", "confidence": 0.9, "reasoning": "r"}'),
        extraction_response_text=_REFERRAL_EXTRACTION_JSON,
    )

    token_a = await make_user_and_login(
        client=client,
        db=db_session,
        email=f"a-{uuid4().hex[:6]}@a.example.com",
        password="pw1234567",
        clinic_id=clinic_a,
    )
    resp_a = await client.post(
        "/api/documents/upload",
        headers=auth_headers(token_a),
        files={"file": ("ref.pdf", _FAKE_PDF, "application/pdf")},
    )
    assert resp_a.status_code == 201, resp_a.text

    tok_a = current_clinic_id.set(clinic_a)
    try:
        a_rows = (await db_session.execute(select(DocumentExtraction))).scalars().all()
    finally:
        current_clinic_id.reset(tok_a)
    assert len(a_rows) == 1
    assert a_rows[0].clinic_id == clinic_a

    tok_b = current_clinic_id.set(clinic_b)
    try:
        b_rows = (await db_session.execute(select(DocumentExtraction))).scalars().all()
    finally:
        current_clinic_id.reset(tok_b)
    assert b_rows == []
