"""Driver for the structured-extraction eval harness.

Runs OCR + extract_document over a directory of ground-truth-paired PDFs,
compares predictions to truth, and writes both a timestamped JSON file
under ``ai/evals/results/`` and an EvalRun row.

Run with::

    PYTHONPATH=apps/api uv --project apps/api run \
      python -m ai.evals.eval_extraction --limit 50

Every run lives in the synthetic eval clinic (constant UUID below) so
real clinics' rows aren't polluted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from ai.evals.compare import aggregate_runs, compare
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.clinic import Clinic
from app.models.document import Document, DocumentClassification, DocumentStatus
from app.models.eval_run import EvalRun, EvalType
from app.services.extraction.service import extract_document
from app.services.llm.factory import get_llm_provider
from app.services.ocr import extract_text
from app.utils.context import current_clinic_id, current_user_id

EVAL_CLINIC_ID = UUID("00000000-0000-0000-0000-000000000eaa")
_RESULTS_DIR = Path(__file__).resolve().parent / "results"


CLASSIFICATION_BY_DIR = {
    "referrals": DocumentClassification.referral,
    "discharges": DocumentClassification.discharge_summary,
}


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


async def _ensure_eval_clinic(db: AsyncSession) -> None:
    """Idempotent: insert the synthetic eval clinic if it doesn't exist."""
    existing = (
        await db.execute(select(Clinic).where(Clinic.id == EVAL_CLINIC_ID))
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        Clinic(
            id=EVAL_CLINIC_ID,
            name="Eval Harness (synthetic)",
            slug="eval-harness",
        )
    )
    await db.commit()


_DEMO_CLINIC_SLUG = "steel-city-cardiology"


async def _resolve_eval_run_clinic(db: AsyncSession) -> UUID:
    """Owner clinic for the EvalRun summary row: the demo seed clinic if it
    exists (so the demo login sees the metrics), else the synthetic eval clinic."""
    demo = (
        await db.execute(select(Clinic).where(Clinic.slug == _DEMO_CLINIC_SLUG))
    ).scalar_one_or_none()
    return demo.id if demo is not None else EVAL_CLINIC_ID


def _find_pairs(seed_dir: Path, limit: int) -> list[tuple[Path, Path, DocumentClassification]]:
    """Walk seed_dir/{referrals,discharges} and pair each PDF with its ground-truth JSON."""
    pairs: list[tuple[Path, Path, DocumentClassification]] = []
    for subdir, classification in CLASSIFICATION_BY_DIR.items():
        root = seed_dir / subdir
        if not root.exists():
            continue
        for pdf in sorted(root.glob("*.pdf")):
            truth = pdf.with_suffix("").with_suffix(".ground-truth.json")
            if not truth.exists():
                continue
            pairs.append((pdf, truth, classification))
            if len(pairs) >= limit:
                return pairs
    return pairs


async def _run_one(
    db: AsyncSession,
    pdf_path: Path,
    truth_path: Path,
    classification: DocumentClassification,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """OCR + extract one document, return (prediction, truth) or None on failure."""
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    try:
        text, engine = await extract_text(pdf_path)
    except Exception as exc:
        print(f"  ! OCR failed for {pdf_path.name}: {exc}")
        return None

    doc = Document(
        file_path=str(pdf_path),
        file_name=pdf_path.name,
        file_size=pdf_path.stat().st_size,
        mime_type="application/pdf",
        status=DocumentStatus.classified,
        classification=classification,
        classification_confidence=1.0,
        extracted_text=text,
        ocr_engine=engine,
    )
    db.add(doc)
    await db.flush()

    try:
        extraction = await extract_document(document_id=doc.id, db=db)
        await db.commit()
    except Exception as exc:
        print(f"  ! extract_document failed for {pdf_path.name}: {exc}")
        await db.rollback()
        return None

    return extraction.extraction_data, truth


async def main(limit: int, seed_dir: Path, out_dir: Path) -> None:
    pairs = _find_pairs(seed_dir, limit)
    if not pairs:
        raise SystemExit(f"no ground-truth/PDF pairs found under {seed_dir}")
    print(f"Found {len(pairs)} eval cases under {seed_dir}")

    provider = get_llm_provider()
    started_at = datetime.now(UTC)
    started_perf = time.perf_counter()
    per_doc: list[dict[str, Any]] = []

    async with async_session_maker() as db:
        # Set context up front. The clinic insert uses GlobalBase so no
        # tenant guard, then everything else runs under the eval clinic.
        cid_token = current_clinic_id.set(EVAL_CLINIC_ID)
        uid_token = current_user_id.set(None)
        try:
            await _ensure_eval_clinic(db)
            for pdf_path, truth_path, classification in pairs:
                print(f"  → {pdf_path.name}")
                result = await _run_one(db, pdf_path, truth_path, classification)
                if result is None:
                    continue
                prediction, truth = result
                per_doc.append(
                    {
                        "document": pdf_path.name,
                        "classification": classification.value,
                        **compare(prediction, truth),
                    }
                )
        finally:
            current_clinic_id.reset(cid_token)
            current_user_id.reset(uid_token)

    finished_at = datetime.now(UTC)
    duration_seconds = int(time.perf_counter() - started_perf)
    rolled = aggregate_runs(per_doc)

    metrics_payload: dict[str, Any] = {
        "aggregate": rolled["aggregate"],
        "per_field": rolled["per_field"],
        "per_document": [
            {
                "document": d["document"],
                "classification": d["classification"],
                "exact_match_rate": d["aggregate"]["exact_match_rate"],
                "f1_macro": d["aggregate"]["f1_macro"],
            }
            for d in per_doc
        ],
        "provider": os.getenv("LLM_PROVIDER", "ollama"),
        "git_sha": _git_sha(),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }

    # Write JSON file.
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = started_at.strftime("%Y%m%dT%H%M%SZ")
    safe_model = provider.model.replace("/", "_").replace(":", "_")
    out_path = out_dir / f"extraction_{ts}_v1_{safe_model}.json"
    out_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
    print(f"\nResults JSON: {out_path}")

    # EvalRun row. The eval *documents* stay in the synthetic eval clinic
    # (so they never pollute a real inbox), but the run-summary row is written
    # to the demo clinic when seeded — eval_runs is tenant-scoped, so this is
    # what lets the demo login actually see the metrics. Falls back to the eval
    # clinic when no demo seed exists (CI / standalone).
    async with async_session_maker() as db:
        owner_clinic_id = await _resolve_eval_run_clinic(db)
        cid_token = current_clinic_id.set(owner_clinic_id)
        try:
            await db.execute(
                insert(EvalRun).values(
                    clinic_id=owner_clinic_id,
                    eval_type=EvalType.extraction,
                    test_set_version=f"module2-{len(pairs)}",
                    metrics=metrics_payload,
                    num_samples=len(per_doc),
                    run_duration_seconds=duration_seconds,
                    prompt_version="v1",
                    model=provider.model,
                    notes=f"git_sha={metrics_payload['git_sha']}",
                    run_by=os.getenv("USER", "unknown"),
                )
            )
            await db.commit()
        finally:
            current_clinic_id.reset(cid_token)

    print(
        "\nAggregate:"
        f"\n  docs               {rolled['aggregate']['num_docs']}"
        f"\n  field observations {rolled['aggregate']['total_field_observations']}"
        f"\n  exact-match rate   {rolled['aggregate']['exact_match_rate']:.3f}"
        f"\n  macro F1           {rolled['aggregate']['f1_macro']:.3f}"
        f"\n  duration           {duration_seconds}s"
    )


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50, help="max documents to evaluate")
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "seeds" / "documents",
        help="root dir containing referrals/ and discharges/ subdirs",
    )
    parser.add_argument("--out", type=Path, default=_RESULTS_DIR, help="results JSON output dir")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit, seed_dir=args.seed_dir, out_dir=args.out))


if __name__ == "__main__":
    cli()
