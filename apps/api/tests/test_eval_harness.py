"""Eval harness tests (Phase 4b).

Covers the pure comparator/normalizer/flatten code and the eval_extraction
driver against a mocked LLM + tmp-path ground-truth files.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from ai.evals import eval_extraction
from ai.evals.compare import compare
from ai.evals.flatten import flatten
from ai.evals.normalizers import normalize_code, normalize_name, normalize_phone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_invocation import AiInvocation, InvocationType
from app.models.eval_run import EvalRun, EvalType
from app.services.llm import factory as llm_factory
from app.services.llm.ollama import OllamaProvider
from app.utils.context import current_clinic_id

# ---------------------------- normalizers ----------------------------


def test_normalize_name_lowercases_and_strips_punctuation() -> None:
    assert normalize_name("AMY ROBINSON") == "amy robinson"
    assert normalize_name("Amy Robinson") == "amy robinson"
    assert normalize_name("  Amy   Robinson, MD ") == "amy robinson md"


def test_normalize_phone_canonicalizes() -> None:
    assert normalize_phone("(412) 555-1234") == "+14125551234"
    assert normalize_phone("412-555-1234") == "+14125551234"
    assert normalize_phone("nope") is None


def test_normalize_code_uppercases_and_strips_spaces() -> None:
    assert normalize_code(" i25.10 ") == "I25.10"


# ---------------------------- flatten ----------------------------


def test_flatten_keeps_code_arrays_whole() -> None:
    out = flatten(
        {
            "patient": {"mrn": "A1", "dob": "2000-01-01"},
            "diagnosis_codes": ["I25.10", "R07.9"],
        }
    )
    assert out == {
        "patient.mrn": "A1",
        "patient.dob": "2000-01-01",
        "diagnosis_codes": ["I25.10", "R07.9"],
    }


def test_flatten_expands_object_arrays_with_indices() -> None:
    out = flatten(
        {
            "procedures_performed": [
                {"cpt_code": "93306", "description": "echo"},
                {"cpt_code": "92928", "description": "PCI"},
            ]
        }
    )
    assert out == {
        "procedures_performed[0].cpt_code": "93306",
        "procedures_performed[0].description": "echo",
        "procedures_performed[1].cpt_code": "92928",
        "procedures_performed[1].description": "PCI",
    }


# ---------------------------- compare ----------------------------


def test_compare_exact_match_scores_1() -> None:
    pred = {"patient": {"first_name": "Amy", "last_name": "Robinson", "dob": "1966-03-13"}}
    truth = pred
    result = compare(pred, truth)
    for path in ("patient.first_name", "patient.last_name", "patient.dob"):
        assert result["per_field"][path]["accuracy"] == 1.0
    assert result["aggregate"]["exact_match_rate"] == 1.0


def test_compare_normalizes_names_and_phones() -> None:
    pred = {"patient": {"first_name": "AMY", "last_name": "Robinson", "phone": "(412) 555-1234"}}
    truth = {"patient": {"first_name": "Amy", "last_name": "robinson", "phone": "412-555-1234"}}
    result = compare(pred, truth)
    assert result["per_field"]["patient.first_name"]["accuracy"] == 1.0
    assert result["per_field"]["patient.last_name"]["accuracy"] == 1.0
    assert result["per_field"]["patient.phone"]["accuracy"] == 1.0


def test_compare_code_arrays_are_set_equal() -> None:
    pred = {"diagnosis_codes": ["R07.9", "I25.10"]}
    truth = {"diagnosis_codes": ["I25.10", "R07.9"]}
    result = compare(pred, truth)
    assert result["per_field"]["diagnosis_codes"]["precision"] == 1.0
    assert result["per_field"]["diagnosis_codes"]["recall"] == 1.0
    assert result["per_field"]["diagnosis_codes"]["f1"] == 1.0
    assert result["per_field"]["diagnosis_codes"]["accuracy"] == 1.0


def test_compare_partial_set_overlap_scores_partial() -> None:
    pred = {"diagnosis_codes": ["I25.10", "Z00.0"]}
    truth = {"diagnosis_codes": ["I25.10", "R07.9"]}
    result = compare(pred, truth)
    m = result["per_field"]["diagnosis_codes"]
    assert m["tp"] == 1
    assert m["fp"] == 1
    assert m["fn"] == 1
    assert m["precision"] == pytest.approx(0.5)
    assert m["recall"] == pytest.approx(0.5)
    assert m["f1"] == pytest.approx(0.5)
    assert m["accuracy"] == 0.0


def test_compare_missing_in_prediction_counts_fn() -> None:
    pred: dict[str, Any] = {"patient": {"first_name": "Amy"}}
    truth = {"patient": {"first_name": "Amy", "last_name": "Robinson"}}
    result = compare(pred, truth)
    assert result["per_field"]["patient.last_name"]["fn"] == 1
    assert result["per_field"]["patient.last_name"]["accuracy"] == 0.0


# ---------------------------- driver integration ----------------------------


def _install_mock_llm(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response_text: str,
    model: str = "medgemma1.5",
) -> None:
    """Wire extraction's LLM to a httpx.MockTransport-backed stub."""

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": response_text})

    transport = httpx.MockTransport(handler)
    provider = OllamaProvider(model=model, base_url="http://mock-llm")
    provider._client = httpx.AsyncClient(base_url="http://mock-llm", transport=transport)

    llm_factory.get_llm_provider.cache_clear()
    monkeypatch.setattr(
        "app.services.extraction.service.get_llm_provider",
        lambda: provider,
    )
    # The driver also calls get_llm_provider() at top-level to report model name.
    monkeypatch.setattr("ai.evals.eval_extraction.get_llm_provider", lambda: provider)


def _patch_ocr(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    async def _fake(_path: Any) -> tuple[str, str]:
        return text, "pypdf"

    monkeypatch.setattr("ai.evals.eval_extraction.extract_text", _fake)


def _write_pair(
    base: Path,
    classification: str,
    name: str,
    truth: dict[str, Any],
) -> None:
    """Write a paired PDF + ground-truth JSON for the harness to pick up."""
    sub = base / classification
    sub.mkdir(parents=True, exist_ok=True)
    (sub / f"{name}.pdf").write_bytes(b"%PDF-1.4\nfixture\n")
    (sub / f"{name}.ground-truth.json").write_text(
        json.dumps(truth), encoding="utf-8"
    )


@pytest.mark.asyncio
async def test_driver_writes_eval_run_and_results_file(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    truth = {
        "patient": {
            "first_name": "Amy",
            "last_name": "Robinson",
            "dob": "1966-03-13",
            "mrn": "MRN-1",
            "phone": "412-555-1234",
            "address_line1": "33890 Jennifer Squares",
            "city": "Pittsburgh",
            "state": "PA",
            "zip_code": "15222",
        },
        "diagnosis_codes": ["R07.9"],
        "procedure_codes": ["93015"],
        "referring_provider": {
            "first_name": "Shawn",
            "last_name": "Flowers",
            "npi": "2423884966",
        },
        "urgency": "routine",
        "follow_up_window_days": 22,
    }
    seed_dir = tmp_path / "seeds"
    out_dir = tmp_path / "out"
    _write_pair(seed_dir, "referrals", "REF-001", truth)
    _write_pair(seed_dir, "referrals", "REF-002", truth)
    _write_pair(seed_dir, "referrals", "REF-003", truth)

    _patch_ocr(monkeypatch, text="ocr body")
    # Mock LLM returns the same prediction as the truth so the run scores 1.0.
    _install_mock_llm(monkeypatch, response_text=json.dumps({**truth, "missing_fields": []}))

    await eval_extraction.main(limit=10, seed_dir=seed_dir, out_dir=out_dir)

    # Results JSON exists.
    result_files = list(out_dir.glob("extraction_*.json"))
    assert len(result_files) == 1
    payload = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert payload["aggregate"]["num_docs"] == 3
    assert payload["aggregate"]["exact_match_rate"] == pytest.approx(1.0)

    # EvalRun row in DB. Use the eval clinic context to read it back since
    # EvalRun is ClinicScopedBase.
    tok = current_clinic_id.set(eval_extraction.EVAL_CLINIC_ID)
    try:
        runs = (
            await db_session.execute(
                select(EvalRun).where(EvalRun.eval_type == EvalType.extraction)
            )
        ).scalars().all()
    finally:
        current_clinic_id.reset(tok)
    assert len(runs) == 1
    run = runs[0]
    assert run.num_samples == 3
    assert run.prompt_version == "v1"
    assert run.metrics["aggregate"]["exact_match_rate"] == pytest.approx(1.0)
    assert run.test_set_version == "module2-3"

    # AiInvocation rows logged for each extraction.
    tok = current_clinic_id.set(eval_extraction.EVAL_CLINIC_ID)
    try:
        invs = (
            await db_session.execute(
                select(AiInvocation).where(
                    AiInvocation.invocation_type == InvocationType.extraction
                )
            )
        ).scalars().all()
    finally:
        current_clinic_id.reset(tok)
    assert len(invs) == 3


def test_aggregate_runs_handles_empty_input() -> None:
    """Belt-and-suspenders: zero docs should not crash the rollup."""
    from ai.evals.compare import aggregate_runs

    rolled = aggregate_runs([])
    assert rolled["aggregate"]["num_docs"] == 0
    assert rolled["aggregate"]["exact_match_rate"] == 0.0
    assert rolled["per_field"] == {}


def test_driver_with_no_pairs_raises(tmp_path: Path) -> None:
    """Empty seed dir → SystemExit so make targets fail loudly."""
    with pytest.raises(SystemExit):
        asyncio.run(eval_extraction.main(limit=1, seed_dir=tmp_path, out_dir=tmp_path))
