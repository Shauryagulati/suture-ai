"""Generate a denial-appeal letter PDF for a prior-auth record.

Loads the PriorAuth + Patient + Clinic, re-runs the determination so we
have fresh policy excerpts, and renders a letter that:

- identifies the patient and the original auth submission
- quotes the specific denial reason verbatim
- cites the matching payer policy excerpt
- restates the clinical justification

Returns bytes. The router persists status changes; this function is
side-effect-free other than the LLM/embedding calls inside the
determination step.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from reportlab.lib.pagesizes import LETTER  # type: ignore[import-untyped]
from reportlab.lib.units import inch  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Clinic, Patient, PriorAuth
from app.services.prior_auth.determine import AuthCheckRequest, check_prior_auth
from app.services.prior_auth.pdf_styles import styles, two_col_table


async def generate_denial_appeal(
    db: AsyncSession,
    prior_auth_id: UUID,
    denial_reason: str,
) -> bytes:
    """Render the appeal letter for the denied prior_auth. Returns bytes."""
    prior_auth = await db.get(PriorAuth, prior_auth_id)
    if prior_auth is None:
        raise ValueError(f"prior_auth {prior_auth_id} not found")
    patient = await db.get(Patient, prior_auth.patient_id)
    if patient is None:
        raise ValueError(f"patient {prior_auth.patient_id} not found")
    clinic = await db.get(Clinic, prior_auth.clinic_id)
    if clinic is None:
        raise ValueError(f"clinic {prior_auth.clinic_id} not found")

    # Re-derive the policy context so the appeal cites the same excerpts
    # the original determination used.
    determination = await check_prior_auth(
        db,
        AuthCheckRequest(
            payer_name=prior_auth.payer_name,
            procedure_codes=list(prior_auth.procedure_codes),
            diagnosis_codes=list(prior_auth.diagnosis_codes),
            clinical_summary=prior_auth.auth_required_reasoning,
        ),
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        invariant=True,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        title=f"Appeal of Prior Authorization Denial — {prior_auth.id}",
        author=clinic.name,
    )
    s = styles()
    elements: list[Any] = []

    # Header — clinic letterhead + date
    elements.append(Paragraph(clinic.name, s["h1"]))
    elements.append(
        Paragraph(
            datetime.now(UTC).strftime("%B %d, %Y"),
            s["body"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(
        Paragraph(
            f"<b>Re: Appeal of Prior Authorization Denial</b><br/>"
            f"Payer: {prior_auth.payer_name}<br/>"
            f"Patient: {patient.first_name} {patient.last_name} "
            f"(DOB {patient.dob}, MRN {patient.mrn or '—'})<br/>"
            f"Original Auth Number: {prior_auth.auth_number or '(not assigned)'}",
            s["body"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(Paragraph("Dear Medical Review,", s["body"]))
    elements.append(Spacer(1, 0.1 * inch))

    elements.append(
        Paragraph(
            f"We are submitting a formal appeal of the prior-authorization denial "
            f"for {patient.first_name} {patient.last_name}. The denial reason on "
            f"record was:",
            s["body"],
        )
    )
    elements.append(Spacer(1, 0.05 * inch))
    elements.append(Paragraph(f"<i>“{denial_reason}”</i>", s["quote"]))
    elements.append(Spacer(1, 0.1 * inch))

    elements.append(Paragraph("Procedure(s) under appeal:", s["body"]))
    elements.append(
        two_col_table(
            [
                ("CPT Code(s)", ", ".join(prior_auth.procedure_codes) or "—"),
                ("ICD-10 Diagnosis", ", ".join(prior_auth.diagnosis_codes) or "—"),
            ]
        )
    )
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(Paragraph("Basis for Appeal", s["h2"]))
    elements.append(
        Paragraph(
            f"Per {prior_auth.payer_name}'s own published medical policy, "
            f"the procedure meets the documented coverage criteria. "
            f"{determination.reasoning}",
            s["body"],
        )
    )
    elements.append(Spacer(1, 0.1 * inch))

    if determination.relevant_policy_excerpts:
        elements.append(Paragraph("Citation from Payer Policy", s["h2"]))
        # Quote the single most relevant excerpt — the appeal should be tight.
        top = determination.relevant_policy_excerpts[0]
        elements.append(
            Paragraph(
                f"<b>{top.payer_name}, CPT {top.procedure_code}:</b>",
                s["body"],
            )
        )
        snippet = top.text.replace("\n\n", "<br/><br/>").replace("\n", " ")
        elements.append(Paragraph(snippet, s["quote"]))
        elements.append(Spacer(1, 0.1 * inch))

    elements.append(
        Paragraph(
            "We respectfully request reconsideration of this determination. "
            "Supporting clinical documentation accompanies this appeal. "
            "Please direct any questions to our office at your convenience.",
            s["body"],
        )
    )
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(
        Paragraph(
            f"Sincerely,<br/><br/>{clinic.name} — Prior Authorization Team",
            s["body"],
        )
    )

    doc.build(elements)
    return buf.getvalue()
