"""Extraction service: LLM → JSON → deterministic confidence → DocumentExtraction row.

Called inline from the upload route after classification (decision #1 of the
Module 2 plan). On JSON-parse failure the row is still persisted with
``human_review_required=True`` so the document is recoverable via re-run.
"""

from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_invocation import AiInvocation, InvocationType
from app.models.document import Document, DocumentClassification
from app.models.document_extraction import DocumentExtraction
from app.services.extraction.confidence import compute_field_confidences
from app.services.llm.base import JSONExtractionError
from app.services.llm.factory import get_llm_provider

logger = structlog.get_logger(__name__)

_PROMPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    / "ai"
    / "prompts"
    / "module2"
)
_PROMPT_FILES: dict[DocumentClassification, str] = {
    DocumentClassification.referral: "extract_referral_v1.md",
    DocumentClassification.discharge_summary: "extract_discharge_v1.md",
}
_TEXT_BUDGET_CHARS = 12000
_INPUT_SUMMARY_CHARS = 200
_OUTPUT_SUMMARY_CHARS = 200
_MAX_TOKENS = 1500


class ExtractionNotSupportedError(ValueError):
    """The document's classification has no extraction prompt configured."""


@lru_cache(maxsize=4)
def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _prompt_version_from_filename(filename: str) -> str:
    # extract_referral_v1.md → "v1"
    stem = Path(filename).stem
    return stem.rsplit("_", 1)[-1]


async def extract_document(
    *,
    document_id: UUID,
    db: AsyncSession,
) -> DocumentExtraction:
    """Run extraction for a referral/discharge document.

    Returns the persisted (but not committed) ``DocumentExtraction``. The
    caller is responsible for ``db.commit()`` — typically the upload route.
    """
    doc = await db.get(Document, document_id)
    if doc is None:
        raise ExtractionNotSupportedError(f"document {document_id} not found")

    prompt_file = _PROMPT_FILES.get(doc.classification)
    if prompt_file is None:
        raise ExtractionNotSupportedError(
            f"no extraction prompt configured for classification={doc.classification.value}"
        )

    if not doc.extracted_text:
        raise ExtractionNotSupportedError(
            f"document {document_id} has no extracted_text — run OCR first"
        )

    system = _load_prompt(prompt_file)
    prompt_version = _prompt_version_from_filename(prompt_file)
    truncated = doc.extracted_text[:_TEXT_BUDGET_CHARS]
    user_prompt = f"Extract the following document:\n\n{truncated}"

    provider = get_llm_provider()
    started = time.perf_counter()
    parsed: dict[str, Any] | None = None
    parse_error: str | None = None
    try:
        parsed = await provider.extract_json(
            system=system,
            prompt=user_prompt,
            max_tokens=_MAX_TOKENS,
        )
    except JSONExtractionError as exc:
        parse_error = type(exc).__name__
        logger.warning(
            "extraction.parse_failed",
            document_id=str(document_id),
            error_type=parse_error,
        )
    latency_ms = int((time.perf_counter() - started) * 1000)

    if parsed is None:
        extraction_data: dict[str, Any] = {}
        missing_fields: list[str] = ["__parse_failed__"]
        field_confidences: dict[str, float] = {}
        needs_review = True
        output_summary: str | None = None
    else:
        # The LLM may include `missing_fields` inside the payload; strip it
        # out of the structured data so reviewers don't see it as a field.
        raw_missing = parsed.pop("missing_fields", []) or []
        missing_fields = [str(m) for m in raw_missing if isinstance(m, str)]
        extraction_data = parsed
        field_confidences, needs_review = compute_field_confidences(extraction_data, missing_fields)
        output_summary = json.dumps(extraction_data)[:_OUTPUT_SUMMARY_CHARS]

    invocation = AiInvocation(
        invocation_type=InvocationType.extraction,
        model=provider.model,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        latency_ms=latency_ms,
        estimated_cost_usd=0.0,
        input_summary=user_prompt[:_INPUT_SUMMARY_CHARS],
        output_summary=output_summary,
        confidence_scores={"prompt_version": prompt_version, "parse_failed": parsed is None},
        document_id=document_id,
    )
    db.add(invocation)
    await db.flush()

    extraction = DocumentExtraction(
        document_id=document_id,
        extraction_data=extraction_data,
        field_confidences=field_confidences,
        missing_fields=missing_fields,
        human_edits=[],
        human_review_required=needs_review,
        extraction_version=1,
        ai_invocation_id=invocation.id,
    )
    db.add(extraction)
    await db.flush()
    return extraction
