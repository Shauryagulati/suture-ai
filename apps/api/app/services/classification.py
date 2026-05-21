"""Classify a document via the configured LLM provider and log the call.

Returns a ``ClassificationResult`` even when the LLM response cannot be parsed —
in that case the document is marked ``unclassified`` with ``confidence=0.0``
and a reasoning string explaining the parse failure. The upload route stays
2xx so the document is still saved and viewable.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_invocation import AiInvocation, InvocationType
from app.models.document import DocumentClassification
from app.services.llm.base import JSONExtractionError
from app.services.llm.factory import get_llm_provider

logger = structlog.get_logger(__name__)

_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "ai"
    / "prompts"
    / "module1"
    / "classify.md"
)
_TEXT_BUDGET_CHARS = 8000
_INPUT_SUMMARY_CHARS = 200
_OUTPUT_SUMMARY_CHARS = 200
_MAX_TOKENS = 400


class ClassificationResult(BaseModel):
    classification: DocumentClassification
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

    @field_validator("classification", mode="before")
    @classmethod
    def _coerce_classification(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return DocumentClassification(value.strip().lower())
            except ValueError:
                return DocumentClassification.unclassified
        return value


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


async def classify_document(
    *,
    text: str,
    document_id: UUID,
    db: AsyncSession,
) -> ClassificationResult:
    """Classify a document. Always returns a result; logs an ai_invocations row."""
    system = _load_system_prompt()
    truncated = text[:_TEXT_BUDGET_CHARS]
    user_prompt = f"Classify the following document:\n\n{truncated}"

    provider = get_llm_provider()
    started = time.perf_counter()
    raw: dict[str, Any] | None = None
    result: ClassificationResult
    try:
        raw = await provider.extract_json(
            system=system,
            prompt=user_prompt,
            max_tokens=_MAX_TOKENS,
        )
        result = ClassificationResult.model_validate(raw)
    except (JSONExtractionError, ValidationError) as exc:
        logger.warning(
            "classification.parse_failed",
            document_id=str(document_id),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        result = ClassificationResult(
            classification=DocumentClassification.unclassified,
            confidence=0.0,
            reasoning=f"LLM response failed schema validation: {type(exc).__name__}",
        )
    latency_ms = int((time.perf_counter() - started) * 1000)

    output_summary = json.dumps(raw)[:_OUTPUT_SUMMARY_CHARS] if raw is not None else None

    invocation = AiInvocation(
        invocation_type=InvocationType.classification,
        model=provider.model,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        latency_ms=latency_ms,
        estimated_cost_usd=0.0,
        input_summary=user_prompt[:_INPUT_SUMMARY_CHARS],
        output_summary=output_summary,
        confidence_scores={"classification": result.confidence},
        document_id=document_id,
    )
    db.add(invocation)
    return result
