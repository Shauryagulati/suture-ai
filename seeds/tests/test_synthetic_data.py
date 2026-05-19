"""Structural tests for the committed synthetic-data corpus.

These tests are DB-free and DO NOT exercise extraction quality (that's
Module 2's eval harness). They check counts, file pairing, schema
validity, and PDF parseability.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from seeds.scripts._validate_gt import (
    parse_pdf_text,
    validate_discharge_gt,
    validate_referral_gt,
)

ROOT = Path(__file__).resolve().parent.parent
REFERRALS = ROOT / "documents" / "referrals"
DISCHARGES = ROOT / "documents" / "discharges"
DATA = ROOT / "data"
SCHEMAS = ROOT / "schemas"
PAYER_RULES = ROOT / "payer_rules"


# ─── Counts + pairing ──────────────────────────────────────────────────────


def test_referral_pdf_count() -> None:
    pdfs = sorted(REFERRALS.glob("REF-*.pdf"))
    assert len(pdfs) == 30, f"expected 30 referral PDFs, found {len(pdfs)}"


def test_referral_ground_truth_count() -> None:
    gts = sorted(REFERRALS.glob("REF-*.ground-truth.json"))
    assert len(gts) == 30


def test_referral_pdf_gt_pairing() -> None:
    pdfs = {p.stem for p in REFERRALS.glob("REF-*.pdf")}
    gt_stems = {p.name.replace(".ground-truth.json", "") for p in REFERRALS.glob("REF-*.ground-truth.json")}
    assert pdfs == gt_stems, f"unpaired: pdfs-only={pdfs - gt_stems}, gts-only={gt_stems - pdfs}"


def test_discharge_pdf_count() -> None:
    assert len(list(DISCHARGES.glob("DIS-*.pdf"))) == 20


def test_discharge_ground_truth_count() -> None:
    assert len(list(DISCHARGES.glob("DIS-*.ground-truth.json"))) == 20


def test_discharge_pdf_gt_pairing() -> None:
    pdfs = {p.stem for p in DISCHARGES.glob("DIS-*.pdf")}
    gt_stems = {p.name.replace(".ground-truth.json", "") for p in DISCHARGES.glob("DIS-*.ground-truth.json")}
    assert pdfs == gt_stems


# ─── Patients + practices JSON ─────────────────────────────────────────────


def test_patients_json_schema() -> None:
    schema = json.loads((SCHEMAS / "patient_record.schema.json").read_text(encoding="utf-8"))
    data = json.loads((DATA / "patients.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)
    assert len(data) == 20

    # Exactly 4 patients should carry an intentional data-quality issue.
    issues = [p for p in data if p["data_quality_issues"]]
    assert len(issues) == 4, f"expected 4 patients with data_quality_issues, found {len(issues)}"


def test_practices_json_schema() -> None:
    schema = json.loads((SCHEMAS / "referring_practice.schema.json").read_text(encoding="utf-8"))
    data = json.loads((DATA / "referring_practices.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)
    assert len(data) == 10
    clean = sum(1 for r in data if r["data_quality_tier"] == "clean")
    messy = sum(1 for r in data if r["data_quality_tier"] == "messy")
    assert clean == 6 and messy == 4, f"expected 6 clean + 4 messy, got {clean} + {messy}"


# ─── Per-document ground-truth validity ────────────────────────────────────


@pytest.mark.parametrize(
    "gt_path", sorted(REFERRALS.glob("REF-*.ground-truth.json")), ids=lambda p: p.stem
)
def test_each_referral_gt_valid(gt_path: Path) -> None:
    data = validate_referral_gt(gt_path)
    assert data["diagnosis_codes"], "diagnosis_codes must be non-empty"
    assert data["procedure_codes"], "procedure_codes must be non-empty"
    assert data["clinical_notes_excerpt"], "clinical_notes_excerpt must be non-empty"


@pytest.mark.parametrize(
    "gt_path", sorted(DISCHARGES.glob("DIS-*.ground-truth.json")), ids=lambda p: p.stem
)
def test_each_discharge_gt_valid(gt_path: Path) -> None:
    data = validate_discharge_gt(gt_path)
    assert data["diagnosis_codes"], "diagnosis_codes must be non-empty"
    assert data["primary_diagnosis"], "primary_diagnosis must be non-empty"


# ─── PDF parseability ──────────────────────────────────────────────────────
#
# Degraded PDFs have a noisy overlay on top of the original text layer.
# Reportlab text underneath survives the overlay, so even degraded PDFs
# should produce some text via pypdf.


_ALL_PDFS = sorted(REFERRALS.glob("REF-*.pdf")) + sorted(DISCHARGES.glob("DIS-*.pdf"))


@pytest.mark.parametrize("pdf_path", _ALL_PDFS, ids=lambda p: p.stem)
def test_pdf_parseable(pdf_path: Path) -> None:
    """Every PDF must yield non-trivial text via pypdf — clean or degraded."""
    text = parse_pdf_text(pdf_path)
    assert len(text.strip()) > 100, f"{pdf_path.name} produced < 100 chars of text"


# ─── Payer rules ───────────────────────────────────────────────────────────


def test_payer_rule_count() -> None:
    md_files = [p for p in PAYER_RULES.glob("*.md") if p.name != "README.md"]
    json_files = [p for p in PAYER_RULES.glob("*.json") if p.name != "payer_rule.schema.json"]
    assert len(md_files) == 5
    assert len(json_files) == 5


def test_payer_rules_schema_valid() -> None:
    schema = json.loads((PAYER_RULES / "payer_rule.schema.json").read_text(encoding="utf-8"))
    for json_file in PAYER_RULES.glob("*.json"):
        if json_file.name == "payer_rule.schema.json":
            continue
        data = json.loads(json_file.read_text(encoding="utf-8"))
        jsonschema.validate(data, schema)


# ─── Cross-corpus invariants ───────────────────────────────────────────────


def test_referral_patient_ids_reference_patients_json() -> None:
    """Every referral GT's patient.external_id must exist in patients.json."""
    patients = json.loads((DATA / "patients.json").read_text(encoding="utf-8"))
    patient_ids = {p["external_id"] for p in patients}
    for gt_path in REFERRALS.glob("REF-*.ground-truth.json"):
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        assert gt["patient"]["external_id"] in patient_ids, (
            f"{gt_path.name} references unknown patient {gt['patient']['external_id']}"
        )


def test_discharge_patient_ids_reference_patients_json() -> None:
    patients = json.loads((DATA / "patients.json").read_text(encoding="utf-8"))
    patient_ids = {p["external_id"] for p in patients}
    for gt_path in DISCHARGES.glob("DIS-*.ground-truth.json"):
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        assert gt["patient"]["external_id"] in patient_ids, (
            f"{gt_path.name} references unknown patient {gt['patient']['external_id']}"
        )


def test_referral_practice_ids_reference_practices_json() -> None:
    practices = json.loads((DATA / "referring_practices.json").read_text(encoding="utf-8"))
    practice_ids = {p["external_id"] for p in practices}
    for gt_path in REFERRALS.glob("REF-*.ground-truth.json"):
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        assert gt["referring_provider"]["external_id"] in practice_ids
