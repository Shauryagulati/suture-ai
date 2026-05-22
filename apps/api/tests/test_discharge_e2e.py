"""End-to-end discharge pipeline: upload → classify → extract → review →
approve → outreach scheduled → patient books → mark seen → confirm fax.

This is the canary test: if any seam in the discharge loop regresses,
this test fails.

Mocks at three seams: OCR (pypdf), LLM (classification + extraction),
fax storage roots. All other layers run real.
"""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.discharge_summary import (
    DischargeStatus,
    DischargeSummary,
)
from app.models.document_extraction import DocumentExtraction
from app.models.fax import Fax, FaxStatus
from app.models.outreach_attempt import OutreachAttempt, OutreachStatus
from app.models.patient import Patient
from app.models.provider import Provider, ProviderType
from app.models.referral_task import ReferralTask
from app.services.discharge import confirmation as confirmation_mod
from app.services.fax import factory as fax_factory
from app.services.fax import stub as fax_stub_mod
from app.utils.context import current_clinic_id, current_user_id
from app.utils.security import encode_scheduling_token
from tests._doc_helpers import (
    auth_headers,
    make_user_and_login,
    patch_llm_provider,
    patch_ocr,
    patch_storage_path,
)

pytestmark = pytest.mark.asyncio


_FAKE_PDF = b"%PDF-1.4\nfixture-discharge\n"

_DISCHARGE_EXTRACTION_JSON = json.dumps(
    {
        "patient": {
            "first_name": "Carl",
            "last_name": "Nguyen",
            "dob": "1955-07-04",
            "mrn": "MRN-E2E-001",
            "phone": "412-555-0160",
            "city": "Pittsburgh",
            "state": "PA",
            "zip_code": "15201",
        },
        "admit_date": "2026-05-15",
        "discharge_date": "2026-05-20",
        "discharging_hospital": "UPMC Presbyterian",
        "primary_diagnosis": "Acute STEMI",
        "diagnosis_codes": ["I21.09"],
        "urgency_tier": "critical",
        "urgent_flags": ["recent_MI", "post-PCI"],
        "recommended_specialist": "Cardiology",
        "follow_up_window_days": 7,
        "missing_fields": [],
    }
)


async def test_full_discharge_loop_walks_every_seam(
    client: AsyncClient,
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    clinic_a, _ = two_clinics

    # Isolate side-effect roots so the test doesn't leak files.
    patch_storage_path(monkeypatch, tmp_path)
    monkeypatch.setattr(confirmation_mod, "_PERSIST_ROOT", tmp_path / "confirmations")
    monkeypatch.setattr(fax_stub_mod, "_OUTBOX_ROOT", tmp_path / "fax_outbox")
    fax_factory.reset_fax_provider_cache()

    patch_ocr(monkeypatch, text="UPMC Presbyterian DISCHARGE SUMMARY for STEMI")
    patch_llm_provider(
        monkeypatch,
        response_text=(
            '{"classification": "discharge_summary", "confidence": 0.95, '
            '"reasoning": "DISCHARGE SUMMARY header"}'
        ),
        extraction_response_text=_DISCHARGE_EXTRACTION_JSON,
    )

    # Need an internal provider for the booking step to pick.
    cid = current_clinic_id.set(clinic_a)
    try:
        provider = Provider(
            clinic_id=clinic_a,
            first_name="Renee",
            last_name="Wexler",
            npi="1234567890",
            provider_type=ProviderType.internal,
            practice_name="Steel City Cardiology",
            practice_phone="412-555-0190",
            practice_address="500 Forbes Ave, Pittsburgh, PA",
            specialty="Cardiology",
        )
        db_session.add(provider)
        await db_session.commit()
    finally:
        current_clinic_id.reset(cid)

    # 1. Log in.
    token = await make_user_and_login(
        client=client,
        db=db_session,
        email="e2e@a.example.com",
        password="e2e-pw-1234",
        clinic_id=clinic_a,
    )
    headers = auth_headers(token)

    # 2. Upload the discharge PDF. The route classifies + extracts inline.
    r = await client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": ("dc.pdf", _FAKE_PDF, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    document_id = UUID(r.json()["id"])

    # Look up the extraction id by document_id (response shape doesn't include it).
    cid = current_clinic_id.set(clinic_a)
    try:
        ext = (
            await db_session.execute(
                select(DocumentExtraction).where(
                    DocumentExtraction.document_id == document_id
                )
            )
        ).scalar_one()
        extraction_id = ext.id
    finally:
        current_clinic_id.reset(cid)

    # 3. Approve the extraction → discharge auto-transitions to patient_contacted.
    r = await client.post(
        f"/api/extractions/{extraction_id}/approve", headers=headers
    )
    assert r.status_code == 200, r.text
    discharge_id = UUID(r.json()["discharge_summary_id"])

    # 4. The discharge GET shows patient_contacted, and tasks + outreach exist.
    r = await client.get(f"/api/discharges/{discharge_id}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "patient_contacted"

    cid = current_clinic_id.set(clinic_a)
    try:
        tasks = (
            await db_session.execute(
                select(ReferralTask).where(
                    ReferralTask.discharge_summary_id == discharge_id
                )
            )
        ).scalars().all()
        attempts = (
            await db_session.execute(
                select(OutreachAttempt)
                .where(OutreachAttempt.discharge_summary_id == discharge_id)
                .order_by(OutreachAttempt.attempt_number)
            )
        ).scalars().all()
    finally:
        current_clinic_id.reset(cid)
    assert len(tasks) == 4
    assert len(attempts) == 3
    sms_attempt = next(a for a in attempts if a.attempt_number == 1)
    patient_id = sms_attempt.patient_id

    # 5. Patient "clicks the scheduling link" — build a token mirroring what
    #    the SMS dispatcher would mint, then POST /book.
    schedule_token, _ = encode_scheduling_token(
        patient_id=patient_id,
        clinic_id=clinic_a,
        outreach_attempt_id=sms_attempt.id,
        discharge_summary_id=discharge_id,
    )
    r = await client.post(
        f"/api/schedule/{schedule_token}/book",
        json={
            "slot": "2026-06-01T14:00:00+00:00",
            "appointment_type": "cardiology_followup",
        },
    )
    assert r.status_code == 200, r.text
    appointment_id = UUID(r.json()["appointment_id"])

    # 6. Discharge advanced to scheduled.
    r = await client.get(f"/api/discharges/{discharge_id}", headers=headers)
    assert r.json()["status"] == "scheduled"

    # 7. Staff marks the appointment completed → discharge → seen.
    r = await client.post(
        f"/api/appointments/{appointment_id}/complete", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["discharge_status"] == "seen"

    # 8. Confirm the discharge → fires fax.
    r = await client.post(
        f"/api/discharges/{discharge_id}/confirm", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmation_sent"
    assert r.json()["confirmation_fax_sent_at"] is not None
    assert r.json()["fax_available"] is True

    # 9. Download the PDF.
    r = await client.get(f"/api/discharges/{discharge_id}/fax", headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) > 100  # not an empty stub

    # 10. Stub fax provider recorded exactly one send for this discharge.
    provider_inst = fax_factory.get_fax_provider()
    matching = [
        req for req in provider_inst.sent if req.discharge_summary_id == discharge_id
    ]
    assert len(matching) == 1

    # 11. Auditable Fax row at status=sent.
    cid = current_clinic_id.set(clinic_a)
    try:
        fax_rows = (
            await db_session.execute(
                select(Fax).where(Fax.patient_id == patient_id)
            )
        ).scalars().all()
    finally:
        current_clinic_id.reset(cid)
    assert len(fax_rows) == 1
    assert fax_rows[0].status == FaxStatus.sent

    fax_factory.reset_fax_provider_cache()
