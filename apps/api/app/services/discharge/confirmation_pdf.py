"""Generate a one-page confirmation-fax PDF for a completed discharge follow-up.

The PDF is what the discharging hospital reads to confirm we (the receiving
cardiology practice) caught the discharge and have the patient on the calendar.
It bundles:
- patient + discharge identifiers
- when + how we contacted the patient
- the booked follow-up appointment (date, provider, type)
- our practice's contact info

Reused: `prior_auth.pdf_styles.styles()` and `two_col_table()` — deliberately
not extracting a shared module yet; promote if a third caller appears.
Returns bytes. The orchestrator (`confirmation.py`) decides persistence.
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.clinic import Clinic
from app.models.discharge_summary import DischargeSummary
from app.models.outreach_attempt import OutreachAttempt, OutreachStatus
from app.models.patient import Patient
from app.models.provider import Provider
from app.services.prior_auth.pdf_styles import styles, two_col_table


async def _load_context(
    db: AsyncSession, discharge_id: UUID
) -> tuple[
    DischargeSummary,
    Patient,
    Clinic,
    Appointment | None,
    Provider | None,
    OutreachAttempt | None,
]:
    discharge = await db.get(DischargeSummary, discharge_id)
    if discharge is None:
        raise ValueError(f"discharge {discharge_id} not found")
    patient = await db.get(Patient, discharge.patient_id)
    if patient is None:
        raise ValueError(f"patient {discharge.patient_id} not found")
    # Clinic is GlobalBase — fetched without the tenant guard.
    clinic = await db.get(Clinic, discharge.clinic_id)
    if clinic is None:
        raise ValueError(f"clinic {discharge.clinic_id} not found")

    appt = (
        await db.execute(
            select(Appointment)
            .where(Appointment.discharge_summary_id == discharge.id)
            .order_by(Appointment.appointment_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    provider: Provider | None = None
    if appt is not None:
        provider = await db.get(Provider, appt.provider_id)

    contact = (
        await db.execute(
            select(OutreachAttempt)
            .where(OutreachAttempt.discharge_summary_id == discharge.id)
            .where(OutreachAttempt.status == OutreachStatus.responded)
            .order_by(OutreachAttempt.sent_at.asc().nulls_last())
            .limit(1)
        )
    ).scalar_one_or_none()

    return discharge, patient, clinic, appt, provider, contact


async def generate_confirmation_pdf(db: AsyncSession, discharge_id: UUID) -> bytes:
    """Render the confirmation-fax PDF for `discharge_id`. Returns bytes."""
    discharge, patient, clinic, appt, provider, contact = await _load_context(db, discharge_id)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        invariant=True,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        title=f"Discharge Follow-Up Confirmation - {discharge.id}",
        author=clinic.name,
    )
    s = styles()
    elements: list[Any] = []

    elements.append(Paragraph("DISCHARGE FOLLOW-UP CONFIRMATION", s["h1"]))
    elements.append(
        Paragraph(
            f"Issued by <b>{clinic.name}</b> &nbsp;&nbsp; "
            f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            s["small"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(
        Paragraph(
            "This letter confirms receipt of the patient discharge summary and "
            "the cardiology follow-up arrangements made on the patient's behalf.",
            s["body"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))

    # ── Patient block ─────────────────────────────────────────────────
    elements.append(Paragraph("Patient", s["h2"]))
    elements.append(
        two_col_table(
            [
                ("Name", f"{patient.first_name} {patient.last_name}"),
                ("Date of Birth", patient.dob or "—"),
                ("Discharge Date", discharge.discharge_date.isoformat()),
                ("Primary Diagnosis", discharge.primary_diagnosis or "—"),
            ]
        )
    )
    elements.append(Spacer(1, 0.15 * inch))

    # ── Contact made ──────────────────────────────────────────────────
    elements.append(Paragraph("Patient Contact", s["h2"]))
    if contact is not None and contact.sent_at is not None:
        contact_rows = [
            ("Contact Date", contact.sent_at.strftime("%Y-%m-%d")),
            ("Channel", contact.channel.value.upper()),
            ("Outcome", "Patient responded — appointment scheduled"),
        ]
    else:
        contact_rows = [
            ("Contact Date", "—"),
            ("Channel", "—"),
            ("Outcome", "—"),
        ]
    elements.append(two_col_table(contact_rows))
    elements.append(Spacer(1, 0.15 * inch))

    # ── Appointment ───────────────────────────────────────────────────
    elements.append(Paragraph("Follow-Up Appointment", s["h2"]))
    if appt is not None:
        provider_line = (
            f"{provider.first_name} {provider.last_name}, {provider.specialty or 'Cardiology'}"
            if provider is not None
            else "—"
        )
        appt_rows = [
            ("Date / Time", appt.appointment_at.strftime("%Y-%m-%d %H:%M %Z").strip()),
            ("Provider", provider_line),
            ("Appointment Type", appt.appointment_type or "Cardiology follow-up"),
        ]
    else:
        appt_rows = [
            ("Date / Time", "—"),
            ("Provider", "—"),
            ("Appointment Type", "—"),
        ]
    elements.append(two_col_table(appt_rows))
    elements.append(Spacer(1, 0.15 * inch))

    # ── Practice contact ──────────────────────────────────────────────
    # Pulled from the booked provider's practice_* fields rather than the
    # Clinic row (Clinic carries no phone/address columns in v1).
    elements.append(Paragraph("Practice Contact", s["h2"]))
    elements.append(
        two_col_table(
            [
                (
                    "Practice",
                    (
                        provider.practice_name
                        if provider and provider.practice_name
                        else clinic.name
                    ),
                ),
                (
                    "Phone",
                    (provider.practice_phone if provider and provider.practice_phone else "—"),
                ),
                (
                    "Address",
                    (provider.practice_address if provider and provider.practice_address else "—"),
                ),
            ]
        )
    )

    doc.build(elements)
    return buf.getvalue()
