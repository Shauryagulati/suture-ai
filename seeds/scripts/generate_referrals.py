"""Generate 30 synthetic cardiology referral PDFs + ground-truth JSON.

Distribution (fixed, asserted at import):
    stress_test: 10
    echo:         8
    cath:         7
    ep_study:     5

For each document:
    1. Build a scenario from `_clinical.REFERRAL_SCENARIOS`, sampling
       an ICD-10 combination + urgency + follow-up window.
    2. Pick a patient (round-robin by index over patients.json).
    3. Pick a referring practice (round-robin by index over practices.json).
    4. ~15% of docs get one intentional missing field (insurance.secondary
       or patient.mrn) — recorded in ground-truth `missing_fields`.
    5. ~30% of docs are flagged for fax-style degradation.
    6. Ask Claude Haiku 4.5 to produce the clinical narrative for the
       scenario (NOT the structured fields — those come from the scenario).
    7. Render PDF via reportlab; apply degradation if flagged.
    8. Write REF-NNN.pdf + REF-NNN.ground-truth.json.

Determinism: seed --> stable rng --> stable scenario choices.
Claude responses are cached under seeds/scripts/llm_fixtures/; re-runs
with the same prompts read cache, never call the API.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

import jsonschema

from seeds.scripts._claude import FixtureBackedClaude
from seeds.scripts._clinical import REFERRAL_COUNTS, REFERRAL_SCENARIOS
from seeds.scripts._pdf import ReferralPayload, degrade_to_fax, render_referral_pdf
from seeds.scripts._utils import (
    DATA_DIR,
    DOCUMENTS_DIR,
    GENERATION_LOG,
    LLM_FIXTURES_DIR,
    REPO_ROOT,
    SCHEMAS_DIR,
    assert_no_phi_keywords,
    run_log,
    write_bytes,
    write_json,
)


REFERRAL_SYSTEM_PROMPT = (
    "You are a primary-care physician writing the clinical narrative section of a "
    "referral letter to a cardiologist. Use realistic physician-to-physician "
    "language and common cardiology abbreviations (HTN, DM2, CAD, NYHA, etc.). "
    "Produce 2-3 short paragraphs covering: relevant history, current symptoms, "
    "exam findings that prompted the referral, and what you want the cardiologist "
    "to evaluate. Around 200-260 words total. "
    "STRICT: do NOT include structured fields with labels — no lines like "
    "'MRN: 12345', 'NPI: ...', 'CPT: ...', 'ICD-10: ...', 'SSN: ...', 'DOB: ...', "
    "'Member ID: ...'. Those fields appear in a separate structured section of "
    "the letter. Focus only on the narrative."
)


def _build_prompt(
    scenario_key: str,
    age: int,
    sex: str,
    chief_complaint: str,
    icd10_codes: list[str],
    urgency: str,
) -> str:
    scenario = REFERRAL_SCENARIOS[scenario_key]
    return (
        f"Write the clinical narrative for a referral letter requesting a "
        f"{scenario.label} (CPT {scenario.cpt_code}).\n\n"
        f"Patient context: {age}-year-old {sex} with chief complaint of {chief_complaint}.\n"
        f"Working diagnoses (ICD-10): {', '.join(icd10_codes)}.\n"
        f"Urgency level: {urgency}.\n\n"
        f"Write only the narrative paragraphs. No bullet points, no labels, "
        f"no signature line. Just the prose body."
    )


# Fixed reference date so the letter date string + admit/discharge dates are
# stable across calendar dates.
GENERATION_ANCHOR = date(2026, 5, 19)


def _letter_date(rng: random.Random) -> str:
    """A date string like 'May 12, 2026', within 14 days of the anchor."""
    offset = rng.randint(-14, 0)
    d = GENERATION_ANCHOR + timedelta(days=offset)
    return d.strftime("%B %-d, %Y")


def _weighted_choice(rng: random.Random, choices: list[tuple[str, float]]) -> str:
    r = rng.random()
    acc = 0.0
    for label, weight in choices:
        acc += weight
        if r <= acc:
            return label
    return choices[-1][0]


def _patient_index_for_doc(doc_index: int, num_patients: int) -> int:
    """Round-robin patient assignment, stable per doc index."""
    return (doc_index - 1) % num_patients


def _practice_index_for_doc(doc_index: int, num_practices: int) -> int:
    """Skewed round-robin so all 10 practices are used but not uniformly."""
    return (doc_index * 3 + 1) % num_practices


def _age_from_dob(dob: str) -> int:
    """Compute integer age at the generation anchor."""
    dob_d = date.fromisoformat(dob)
    age = GENERATION_ANCHOR.year - dob_d.year
    if (GENERATION_ANCHOR.month, GENERATION_ANCHOR.day) < (dob_d.month, dob_d.day):
        age -= 1
    return age


def _sex_for_patient(patient: dict, rng: random.Random) -> str:
    """Coin a deterministic sex per patient external_id.

    Faker doesn't tag first-names by sex, so we derive one from the patient's
    stable external_id. Uses hashlib (not Python's `hash()`, which is salted
    per-process and would break reproducibility across runs).
    """
    import hashlib

    h = int(hashlib.sha256(patient["external_id"].encode("utf-8")).hexdigest(), 16)
    return "male" if (h % 2 == 0) else "female"


def _apply_missing_field(
    doc_index: int,
    ground_truth: dict,
    payload_overrides: dict,
) -> list[str]:
    """Mutate ground-truth + render payload to reflect an intentional gap.

    ~15% of docs (every 7th by index) get one gap. The eval expects the
    extractor to flag this exact path in its missing_fields output.
    """
    if doc_index % 7 != 0:  # 0, 7, 14, 21, 28 — 5 of 30 → 16.7%
        return []
    # Alternate between the two gap types so we exercise both.
    gap = "insurance.secondary" if (doc_index // 7) % 2 == 0 else "patient.mrn"
    if gap == "insurance.secondary":
        ground_truth["insurance"]["secondary"] = None
        payload_overrides["insurance_secondary_payer"] = None
        payload_overrides["insurance_secondary_member_id"] = None
    else:  # patient.mrn
        ground_truth["patient"]["mrn"] = None
        payload_overrides["patient_mrn"] = None
    return [gap]


def _is_degraded(doc_index: int) -> bool:
    """3 of every 10 docs are degraded (positions 1, 4, 7 in each block of 10)."""
    return (doc_index % 10) in (1, 4, 7)


def generate(seed: int, limit: int | None = None) -> None:
    rng = random.Random(seed)

    patients = json.loads((DATA_DIR / "patients.json").read_text(encoding="utf-8"))
    practices = json.loads(
        (DATA_DIR / "referring_practices.json").read_text(encoding="utf-8")
    )

    schema = json.loads(
        (SCHEMAS_DIR / "referral_ground_truth.schema.json").read_text(encoding="utf-8")
    )

    claude = FixtureBackedClaude(fixtures_dir=LLM_FIXTURES_DIR)
    referrals_dir = DOCUMENTS_DIR / "referrals"

    doc_index = 0
    with run_log(GENERATION_LOG, "generate_referrals") as log:
        for referral_type, count in REFERRAL_COUNTS.items():
            scenario = REFERRAL_SCENARIOS[referral_type]
            for _ in range(count):
                doc_index += 1
                if limit is not None and doc_index > limit:
                    print(f"--limit {limit} reached; stopping early")
                    return
                doc_external_id = f"REF-{doc_index:03d}"

                # Patient + practice selection.
                patient = patients[_patient_index_for_doc(doc_index, len(patients))]
                practice = practices[_practice_index_for_doc(doc_index, len(practices))]

                age = _age_from_dob(patient["dob"])
                sex = _sex_for_patient(patient, rng)

                # Scenario choices.
                icd10 = list(rng.choice(scenario.icd10_combinations))
                urgency = _weighted_choice(rng, scenario.urgency_choices)
                fu_low, fu_high = scenario.follow_up_window_days_range
                follow_up_window_days = rng.randint(fu_low, fu_high)
                chief_complaint = rng.choice(scenario.chief_complaints)

                # Generate narrative via Claude (cache-hit on re-runs).
                prompt = _build_prompt(
                    referral_type, age, sex, chief_complaint, icd10, urgency
                )
                result = claude.generate(
                    system=REFERRAL_SYSTEM_PROMPT,
                    prompt=prompt,
                    max_tokens=900,
                )
                log.api_calls += 0 if result.from_fixture else 1
                log.input_tokens += result.input_tokens
                log.output_tokens += result.output_tokens
                if not result.from_fixture:
                    log.usd_cost += result.usd_cost

                narrative = result.content
                assert_no_phi_keywords(narrative, where=doc_external_id)
                clinical_excerpt = narrative[:200]

                # Initial ground truth (before missing-field application).
                ground_truth: dict = {
                    "document_external_id": doc_external_id,
                    "classification": "referral",
                    "referral_type": referral_type,
                    "patient": {
                        "external_id": patient["external_id"],
                        "first_name": patient["first_name"],
                        "last_name": patient["last_name"],
                        "dob": patient["dob"],
                        "phone": patient["phone"],
                        "address_line1": patient["address_line1"],
                        "city": patient["city"],
                        "state": patient["state"],
                        "zip_code": patient["zip_code"],
                        "mrn": patient["mrn"],
                    },
                    "referring_provider": {
                        "external_id": practice["external_id"],
                        "first_name": practice["first_name"],
                        "last_name": practice["last_name"],
                        "npi": practice["npi"],
                        "practice_name": practice["practice_name"],
                        "practice_phone": practice["practice_phone"],
                        "practice_fax": practice["practice_fax"],
                    },
                    "insurance": json.loads(json.dumps(patient["insurance"])),  # deep copy
                    "diagnosis_codes": icd10,
                    "procedure_codes": [scenario.cpt_code],
                    "urgency": urgency,
                    "follow_up_window_days": follow_up_window_days,
                    "clinical_notes_excerpt": clinical_excerpt,
                    "missing_fields": [],
                    "is_degraded": _is_degraded(doc_index),
                }

                # Patient-level data-quality issues from patients.json carry
                # forward as missing_fields (the eval should not penalize
                # the extractor for legitimately absent values).
                for issue in patient.get("data_quality_issues", []):
                    if issue == "missing_phone":
                        ground_truth["missing_fields"].append("patient.phone")
                    elif issue == "partial_address":
                        ground_truth["missing_fields"].append("patient.address_line1")
                    elif issue == "missing_zip":
                        ground_truth["missing_fields"].append("patient.zip_code")
                    elif issue == "malformed_member_id":
                        # Not "missing" — it's present but invalid. The eval
                        # can flag this separately. Not in missing_fields.
                        pass

                # Practice-level (messy tier) carries forward similarly.
                if practice["practice_fax"] is None:
                    ground_truth["missing_fields"].append("referring_provider.practice_fax")
                if practice["practice_address"] is None:
                    # Practice address doesn't appear in ground_truth (the schema
                    # lacks a field for it) so this is not a missing_fields entry.
                    pass

                # Apply doc-level intentional gaps.
                payload_overrides: dict = {}
                added = _apply_missing_field(doc_index, ground_truth, payload_overrides)
                ground_truth["missing_fields"].extend(added)
                # Deduplicate + sort for deterministic output.
                ground_truth["missing_fields"] = sorted(set(ground_truth["missing_fields"]))

                # Build PDF payload.
                # Address fields for the practice — use practice_address if present;
                # otherwise fall back to a stub so reportlab has something to render.
                practice_addr = practice["practice_address"] or "Address on file"
                # Insurance fields for payload
                primary = ground_truth["insurance"]["primary"]
                secondary = ground_truth["insurance"]["secondary"]
                payload = ReferralPayload(
                    document_external_id=doc_external_id,
                    referral_type_label=scenario.label,
                    cpt_code=scenario.cpt_code,
                    icd10_codes=icd10,
                    urgency=urgency,
                    follow_up_window_days=follow_up_window_days,
                    practice_name=practice["practice_name"],
                    practice_address=practice_addr,
                    practice_phone=practice["practice_phone"] or "Phone on file",
                    practice_fax=practice["practice_fax"] or "Fax on file",
                    referring_provider_name=f"{practice['first_name']} {practice['last_name']}, MD",
                    referring_provider_npi=practice["npi"],
                    recipient_practice_name="Steel City Cardiology Associates",
                    recipient_practice_address="200 Smithfield St, Pittsburgh, PA 15222",
                    patient_first_name=ground_truth["patient"]["first_name"],
                    patient_last_name=ground_truth["patient"]["last_name"],
                    patient_dob=ground_truth["patient"]["dob"],
                    patient_phone=payload_overrides.get(
                        "patient_phone", ground_truth["patient"]["phone"]
                    ),
                    patient_address_line1=ground_truth["patient"]["address_line1"],
                    patient_city=ground_truth["patient"]["city"],
                    patient_state=ground_truth["patient"]["state"],
                    patient_zip=ground_truth["patient"]["zip_code"],
                    patient_mrn=payload_overrides.get(
                        "patient_mrn", ground_truth["patient"]["mrn"]
                    ),
                    insurance_primary_payer=primary["payer"],
                    insurance_primary_member_id=primary["member_id"],
                    insurance_secondary_payer=(
                        secondary["payer"] if secondary else
                        payload_overrides.get("insurance_secondary_payer", None)
                    ),
                    insurance_secondary_member_id=(
                        secondary["member_id"] if secondary else
                        payload_overrides.get("insurance_secondary_member_id", None)
                    ),
                    clinical_narrative=narrative,
                    letter_date=_letter_date(rng),
                )

                pdf_bytes = render_referral_pdf(payload)
                if ground_truth["is_degraded"]:
                    pdf_bytes = degrade_to_fax(pdf_bytes, seed=seed + doc_index)

                pdf_path = referrals_dir / f"{doc_external_id}.pdf"
                gt_path = referrals_dir / f"{doc_external_id}.ground-truth.json"
                write_bytes(pdf_path, pdf_bytes)

                # Validate ground truth against schema BEFORE writing.
                jsonschema.validate(ground_truth, schema)
                write_json(gt_path, ground_truth)

                log.items += 1
                print(
                    f"  {doc_external_id} ({referral_type:<11}) "
                    f"degraded={'Y' if ground_truth['is_degraded'] else 'N'} "
                    f"missing={ground_truth['missing_fields'] or '[]'} "
                    f"{'[fixture]' if result.from_fixture else f'[api ${result.usd_cost:.4f}]'}"
                )

        print(
            f"\nAPI calls: {log.api_calls}  "
            f"input_tokens: {log.input_tokens}  "
            f"output_tokens: {log.output_tokens}  "
            f"cost: ${log.usd_cost:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic referral PDFs + ground truth.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after N documents (for dry-runs / inspection)",
    )
    args = parser.parse_args()
    generate(seed=args.seed, limit=args.limit)


if __name__ == "__main__":
    main()
