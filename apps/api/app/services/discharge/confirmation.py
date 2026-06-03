"""End-to-end confirmation-fax pipeline.

generate PDF -> persist on disk -> insert auditable Fax row -> send via
FaxProvider -> update Fax row + discharge columns. Idempotent on
`discharge.confirmation_fax_path`. Caller is responsible for committing
the session (the state machine commits at the end of the transition).

Delivery failures do NOT raise: the Fax row is left at status=failed and
the discharge already advanced to confirmation_sent (the transition that
brought us here has already mutated the status). Staff can re-trigger
via POST /api/discharges/{id}/confirm — the orchestrator is idempotent
on confirmation_fax_path, so a successful re-trigger requires clearing
the path first (v2: an explicit retry endpoint).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.discharge_summary import DischargeSummary
from app.models.fax import Fax, FaxDirection, FaxStatus, FaxType
from app.services.discharge.confirmation_pdf import generate_confirmation_pdf
from app.services.fax.base import FaxRequest
from app.services.fax.factory import get_fax_provider
from app.utils.logging import get_logger

log = get_logger(__name__)

# Confirmations live alongside the document storage root, not inside it,
# so a docs-bucket sync doesn't accidentally pick them up.
_PERSIST_ROOT = (
    Path(get_settings().document_storage_path).resolve().parent / "discharge_confirmations"
)

# v2 gap: the discharging hospital's fax number is not yet captured during
# extraction. Until then, the stub records a send to this placeholder so the
# pipeline can be exercised end-to-end without lying about delivery.
_PLACEHOLDER_RECIPIENT_FAX = "555-000-0000"


async def send_confirmation_fax(db: AsyncSession, discharge: DischargeSummary) -> Path:
    """Generate, persist, and send the confirmation fax. Returns the local
    PDF path. Idempotent on `discharge.confirmation_fax_path`. Caller commits."""
    if discharge.confirmation_fax_path:
        return Path(discharge.confirmation_fax_path)

    pdf_bytes = await generate_confirmation_pdf(db, discharge.id)

    out_dir = _PERSIST_ROOT / str(discharge.clinic_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{discharge.id}.pdf"
    out_path.write_bytes(pdf_bytes)

    fax_row = Fax(
        clinic_id=discharge.clinic_id,
        direction=FaxDirection.outbound,
        fax_type=FaxType.confirmation,
        patient_id=discharge.patient_id,
        document_id=discharge.document_id,
        file_path=str(out_path),
        recipient_fax_number=_PLACEHOLDER_RECIPIENT_FAX,
        recipient_name="Discharging Hospital",
        status=FaxStatus.sending,
    )
    db.add(fax_row)
    await db.flush()

    result = await get_fax_provider().send_fax(
        FaxRequest(
            to_number=_PLACEHOLDER_RECIPIENT_FAX,
            pdf_bytes=pdf_bytes,
            subject=f"Discharge Follow-Up Confirmation - {discharge.id}",
            discharge_summary_id=discharge.id,
            metadata={"clinic_id": str(discharge.clinic_id)},
        )
    )

    now = datetime.now(UTC)
    if result.delivered:
        fax_row.status = FaxStatus.sent
        fax_row.sent_at = now
    else:
        fax_row.status = FaxStatus.failed
        log.error(
            "discharge.confirmation.send_failed",
            discharge_summary_id=str(discharge.id),
            fax_id=str(fax_row.id),
            error=result.error,
        )

    discharge.confirmation_fax_path = str(out_path)
    discharge.confirmation_fax_sent_at = now
    return out_path
