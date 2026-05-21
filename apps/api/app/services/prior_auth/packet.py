"""Generate a prior-authorization packet PDF for a referral.

The packet bundles:
- cover sheet (practice + patient + payer identifiers)
- insurance + patient demographic blocks
- clinical justification (from the referral's notes + extracted data)
- requested procedures / diagnoses
- required documents checklist (from the structured payer rule)
- supporting policy excerpts (from RAG retrieval, with attribution)
- common denial reasons (so the submitter can pre-empt them)

Returns the PDF as bytes. The router decides whether to persist to
`apps/api/var/auth_packets/{prior_auth_id}.pdf` and update
`PriorAuth.packet_file_path`.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from reportlab.lib.pagesizes import LETTER  # type: ignore[import-untyped]
from reportlab.lib.units import inch  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Clinic, InsurancePolicy, Patient, Referral
from app.services.prior_auth.determine import AuthDetermination
from app.services.prior_auth.pdf_styles import styles, two_col_table


async def _load_packet_context(
    db: AsyncSession, referral_id: UUID
) -> tuple[Referral, Patient, Clinic, InsurancePolicy | None]:
    """Fetch the referral and everything it references for the cover sheet."""
    referral = await db.get(Referral, referral_id)
    if referral is None:
        raise ValueError(f"referral {referral_id} not found")
    patient = await db.get(Patient, referral.patient_id)
    if patient is None:
        raise ValueError(f"patient {referral.patient_id} not found")
    # Clinic is GlobalBase — fetched without the tenant guard.
    clinic = await db.get(Clinic, referral.clinic_id)
    if clinic is None:
        raise ValueError(f"clinic {referral.clinic_id} not found")

    primary = (
        await db.execute(
            select(InsurancePolicy)
            .where(InsurancePolicy.patient_id == patient.id)
            .where(InsurancePolicy.is_primary.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    return referral, patient, clinic, primary


def _patient_address(patient: Patient) -> str:
    parts: list[str] = []
    if patient.address_line1:
        parts.append(patient.address_line1)
    locality = ", ".join(p for p in [patient.city, patient.state, patient.zip_code] if p)
    if locality:
        parts.append(locality)
    return "<br/>".join(parts)


async def generate_auth_packet(
    db: AsyncSession,
    referral_id: UUID,
    determination: AuthDetermination,
) -> bytes:
    """Render the auth packet PDF for `referral_id`. Returns bytes."""
    referral, patient, clinic, primary_policy = await _load_packet_context(db, referral_id)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        invariant=True,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        title=f"Prior Authorization Packet — {referral.id}",
        author=clinic.name,
    )
    s = styles()
    elements: list[Any] = []

    # ── Cover sheet header ─────────────────────────────────────────────
    elements.append(Paragraph("PRIOR AUTHORIZATION REQUEST", s["h1"]))
    elements.append(
        Paragraph(
            f"Submitted by <b>{clinic.name}</b> &nbsp;&nbsp; "
            f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            s["small"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))

    # ── Payer + procedure summary ──────────────────────────────────────
    payer_name = primary_policy.payer_name if primary_policy else "(payer on file)"
    elements.append(Paragraph("Request Summary", s["h2"]))
    elements.append(
        two_col_table(
            [
                ("Payer", payer_name),
                ("Procedure CPT(s)", ", ".join(referral.procedure_codes) or "—"),
                ("Diagnosis ICD-10(s)", ", ".join(referral.diagnosis_codes) or "—"),
                ("Auth Required", "Yes" if determination.auth_required else "No"),
                (
                    "Typical Turnaround",
                    f"{determination.typical_turnaround_days} business days"
                    if determination.typical_turnaround_days is not None
                    else "—",
                ),
            ]
        )
    )
    elements.append(Spacer(1, 0.15 * inch))

    # ── Patient block ──────────────────────────────────────────────────
    elements.append(Paragraph("Patient", s["h2"]))
    elements.append(
        two_col_table(
            [
                ("Name", f"{patient.first_name} {patient.last_name}"),
                ("Date of Birth", patient.dob),
                ("MRN", patient.mrn or ""),
                ("Phone", patient.phone),
                ("Address", _patient_address(patient)),
            ]
        )
    )
    elements.append(Spacer(1, 0.1 * inch))

    # ── Insurance block ────────────────────────────────────────────────
    if primary_policy is not None:
        elements.append(Paragraph("Insurance (Primary)", s["h2"]))
        elements.append(
            two_col_table(
                [
                    ("Payer", primary_policy.payer_name),
                    ("Payer ID", primary_policy.payer_id or ""),
                    ("Member ID", primary_policy.member_id),
                    ("Group #", primary_policy.group_number or ""),
                    ("Plan Type", primary_policy.plan_type or ""),
                ]
            )
        )
        elements.append(Spacer(1, 0.15 * inch))

    # ── Clinical justification ─────────────────────────────────────────
    elements.append(Paragraph("Clinical Justification", s["h2"]))
    elements.append(Paragraph(determination.reasoning, s["body"]))
    if referral.notes:
        elements.append(Spacer(1, 0.05 * inch))
        elements.append(Paragraph(f"<i>Referral notes:</i> {referral.notes}", s["body"]))
    elements.append(Spacer(1, 0.15 * inch))

    # ── Required documents checklist ───────────────────────────────────
    if determination.required_documents:
        elements.append(Paragraph("Required Documents (per payer policy)", s["h2"]))
        items = [
            ListItem(Paragraph(f"☐ {doc}", s["body"]), leftIndent=10)
            for doc in determination.required_documents
        ]
        elements.append(ListFlowable(items, bulletType="bullet", leftIndent=8))
        elements.append(Spacer(1, 0.15 * inch))

    # ── Supporting policy excerpts ─────────────────────────────────────
    if determination.relevant_policy_excerpts:
        elements.append(Paragraph("Supporting Policy Excerpts", s["h2"]))
        for exc in determination.relevant_policy_excerpts:
            elements.append(
                Paragraph(
                    f"<b>{exc.payer_name}, CPT {exc.procedure_code}</b>",
                    s["body"],
                )
            )
            # Trim the excerpt aggressively — packet PDFs should be scannable.
            snippet = exc.text.replace("\n\n", "<br/><br/>").replace("\n", " ")
            elements.append(Paragraph(snippet, s["quote"]))
            elements.append(Spacer(1, 0.05 * inch))
        elements.append(Spacer(1, 0.1 * inch))

    # ── Common denial reasons ──────────────────────────────────────────
    if determination.common_denial_reasons:
        elements.append(Paragraph("Common Denial Reasons (pre-empt these)", s["h2"]))
        items = [
            ListItem(Paragraph(reason, s["body"]), leftIndent=10)
            for reason in determination.common_denial_reasons
        ]
        elements.append(ListFlowable(items, bulletType="bullet", leftIndent=8))

    doc.build(elements)
    return buf.getvalue()
