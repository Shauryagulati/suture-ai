"""Prior-auth determination service — the RAG pipeline.

Three steps for every check:

1. **Structured lookup** — exact match on `(payer_name, procedure_code)`.
   For multi-CPT orders, `auth_required` is true if ANY listed procedure
   requires it; `required_documents` and `common_denial_reasons` are
   unioned; `typical_turnaround_days` is the max.

2. **Vector retrieval** — embed the natural-language query, ORDER BY
   cosine distance against `payer_rules.embedding`, limit 3. The
   `guidelines_text` of the retrieved rows becomes the excerpts surfaced
   to the LLM and the caller.

3. **LLM synthesis** — the LLM writes the human-readable `reasoning` and
   adjusts `confidence` based on whether the structured rule and the
   retrieved excerpts agree. The structured rule is authoritative for
   `auth_required`; the LLM does not override it.

Every call logs to `ai_invocations` with model + latency + estimated token
counts (the LLM provider abstraction returns only response text, so tokens
are estimated at ~4 chars/token and the row is flagged `tokens_estimated`).
Surfacing exact provider usage is a follow-up that widens the abstraction.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiInvocation, InvocationType, PayerRule
from app.services.embedding import get_embedding_provider
from app.services.llm import get_llm_provider
from app.services.llm.base import JSONExtractionError, estimate_tokens
from app.services.llm.pricing import estimate_cost_usd

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PROMPT_DIR = _REPO_ROOT / "ai" / "prompts" / "prior_auth"
_SYSTEM_PROMPT = (_PROMPT_DIR / "determine_v1.system.txt").read_text(encoding="utf-8")
_USER_TEMPLATE = (_PROMPT_DIR / "determine_v1.user.txt").read_text(encoding="utf-8")


class AuthCheckRequest(BaseModel):
    payer_name: str = Field(min_length=1, max_length=128)
    procedure_codes: list[str] = Field(min_length=1)
    diagnosis_codes: list[str] = Field(default_factory=list)
    clinical_summary: str | None = None


class PolicyExcerpt(BaseModel):
    payer_name: str
    procedure_code: str
    text: str
    distance: float | None = None


class AuthDetermination(BaseModel):
    auth_required: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    required_documents: list[str]
    typical_turnaround_days: int | None
    relevant_policy_excerpts: list[PolicyExcerpt]
    common_denial_reasons: list[str]


@dataclass(slots=True)
class _StructuredResult:
    auth_required: bool = False
    required_documents: list[str] = field(default_factory=list)
    common_denial_reasons: list[str] = field(default_factory=list)
    typical_turnaround_days: int | None = None
    matched_cpts: list[str] = field(default_factory=list)


async def _structured_lookup(
    db: AsyncSession,
    payer_name: str,
    procedure_codes: list[str],
) -> tuple[list[PayerRule], list[str]]:
    """Exact-match lookup. Returns (matched_rows, missing_cpts)."""
    stmt = select(PayerRule).where(
        PayerRule.payer_name == payer_name,
        PayerRule.procedure_code.in_(procedure_codes),
    )
    matched = list((await db.execute(stmt)).scalars().all())
    found_cpts = {row.procedure_code for row in matched}
    missing = [cpt for cpt in procedure_codes if cpt not in found_cpts]
    return matched, missing


def _aggregate_structured(matched: list[PayerRule]) -> _StructuredResult:
    """Roll up multiple matching rows into one structured result.

    OR for auth_required, union for the list fields, max for turnaround.
    """
    if not matched:
        return _StructuredResult()
    documents: list[str] = []
    seen_docs: set[str] = set()
    denials: list[str] = []
    seen_denials: set[str] = set()
    turnarounds: list[int] = []
    for row in matched:
        for doc in row.required_documents:
            if doc not in seen_docs:
                seen_docs.add(doc)
                documents.append(doc)
        for reason in row.common_denial_reasons:
            if reason not in seen_denials:
                seen_denials.add(reason)
                denials.append(reason)
        if row.typical_turnaround_days is not None:
            turnarounds.append(row.typical_turnaround_days)
    return _StructuredResult(
        auth_required=any(row.auth_required for row in matched),
        required_documents=documents,
        common_denial_reasons=denials,
        typical_turnaround_days=max(turnarounds) if turnarounds else None,
        matched_cpts=sorted({row.procedure_code for row in matched}),
    )


async def _retrieve_excerpts(
    db: AsyncSession,
    query_text: str,
    limit: int = 3,
) -> list[PolicyExcerpt]:
    """Cosine-distance search over payer_rules.embedding."""
    query_vec = await get_embedding_provider().embed_query(query_text)
    distance_col = PayerRule.embedding.cosine_distance(query_vec).label("dist")
    stmt = (
        select(PayerRule, distance_col)
        .where(PayerRule.embedding.is_not(None))
        .order_by(distance_col)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    excerpts: list[PolicyExcerpt] = []
    for row, dist in rows:
        excerpts.append(
            PolicyExcerpt(
                payer_name=row.payer_name,
                procedure_code=row.procedure_code,
                text=row.guidelines_text or "",
                distance=float(dist) if dist is not None else None,
            )
        )
    return excerpts


def _format_retrieved_chunks(excerpts: list[PolicyExcerpt]) -> str:
    if not excerpts:
        return "(no relevant excerpts retrieved)"
    parts: list[str] = []
    for i, exc in enumerate(excerpts, start=1):
        parts.append(
            f"[{i}] {exc.payer_name}, CPT {exc.procedure_code} "
            f"(distance={exc.distance:.4f}):\n{exc.text}"
            if exc.distance is not None
            else f"[{i}] {exc.payer_name}, CPT {exc.procedure_code}:\n{exc.text}"
        )
    return "\n\n".join(parts)


def _build_query_text(request: AuthCheckRequest) -> str:
    parts = [f"Prior authorization for {request.payer_name}"]
    parts.append(f"procedures {', '.join(request.procedure_codes)}")
    if request.diagnosis_codes:
        parts.append(f"diagnoses {', '.join(request.diagnosis_codes)}")
    if request.clinical_summary:
        parts.append(request.clinical_summary)
    return ". ".join(parts)


async def check_prior_auth(db: AsyncSession, request: AuthCheckRequest) -> AuthDetermination:
    """Run the three-step pipeline and return the determination."""
    matched, _missing = await _structured_lookup(db, request.payer_name, request.procedure_codes)
    structured = _aggregate_structured(matched)

    query_text = _build_query_text(request)
    excerpts = await _retrieve_excerpts(db, query_text, limit=3)

    user_prompt = _USER_TEMPLATE.format(
        payer=request.payer_name,
        cpts=", ".join(request.procedure_codes),
        icds=", ".join(request.diagnosis_codes) or "(none provided)",
        clinical_summary=request.clinical_summary or "(none provided)",
        structured_result_json=json.dumps(
            {
                "auth_required": structured.auth_required,
                "required_documents": structured.required_documents,
                "common_denial_reasons": structured.common_denial_reasons,
                "typical_turnaround_days": structured.typical_turnaround_days,
                "matched_cpts": structured.matched_cpts,
            },
            indent=2,
        ),
        retrieved_chunks=_format_retrieved_chunks(excerpts),
    )

    provider = get_llm_provider()
    start = time.monotonic()
    try:
        llm_out = await provider.extract_json(
            system=_SYSTEM_PROMPT,
            prompt=user_prompt,
            max_tokens=600,
        )
    except JSONExtractionError:
        # Fall back to the structured result with a low-confidence reasoning.
        # We still want the caller to get a usable answer if the LLM misbehaves.
        llm_out = {
            "reasoning": (
                f"Fallback determination based on structured rule for {request.payer_name} "
                f"and procedures {request.procedure_codes}."
            ),
            "confidence": 0.5 if matched else 0.2,
            "supports_structured_result": True,
        }
    latency_ms = int((time.monotonic() - start) * 1000)

    # Token counts are estimated (~4 chars/token): the provider interface returns
    # only text, not exact usage. Flagged `tokens_estimated` so cost reporting can
    # tell estimates from exact provider usage. See module docstring.
    prompt_tokens = estimate_tokens(_SYSTEM_PROMPT + user_prompt)
    completion_tokens = estimate_tokens(json.dumps(llm_out))
    db.add(
        AiInvocation(
            invocation_type=InvocationType.auth_check,
            model=provider.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
            estimated_cost_usd=estimate_cost_usd(provider.model, prompt_tokens, completion_tokens),
            confidence_scores={
                "auth_check": float(llm_out.get("confidence", 0.0)),
                "tokens_estimated": True,
            },
            input_summary=(
                f"prior_auth_check payer={request.payer_name} "
                f"cpts={request.procedure_codes} "
                f"matched_cpts={structured.matched_cpts} "
                f"excerpts={len(excerpts)}"
            ),
            output_summary=f"auth_required={structured.auth_required}",
        )
    )
    await db.commit()

    confidence = float(llm_out.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    return AuthDetermination(
        auth_required=structured.auth_required,
        confidence=confidence,
        reasoning=str(llm_out.get("reasoning", "")).strip()
        or f"Structured rule match for {request.payer_name}.",
        required_documents=list(structured.required_documents),
        typical_turnaround_days=structured.typical_turnaround_days,
        relevant_policy_excerpts=excerpts,
        common_denial_reasons=list(structured.common_denial_reasons),
    )
