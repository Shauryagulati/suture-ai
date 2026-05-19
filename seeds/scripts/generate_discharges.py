"""Generate 20 synthetic cardiology discharge-summary PDFs + ground-truth JSON.

Distribution (fixed, asserted at import in _clinical):
    post_mi:         8
    post_chf:        5
    post_cath:       4
    post_ablation:   3

For each document:
    1. Build a scenario from `_clinical.DISCHARGE_SCENARIOS`.
    2. Pick a patient (round-robin by doc index — different stride than
       referrals so the two corpora aren't trivially co-located).
    3. Pick a hospital from the Western-PA pool.
    4. Coin an attending hospitalist (NOT pulled from referring-practice
       providers — different role).
    5. Sample admit/discharge dates relative to the generation anchor.
    6. Sample 2–4 medication changes from the scenario pool.
    7. Ask Claude Haiku 4.5 for the hospital-course narrative.
    8. ~30% degraded; same 1-4-7-of-each-10 pattern as referrals.
    9. Validate + write ground-truth JSON, render + write PDF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

import jsonschema

from seeds.scripts._claude import FixtureBackedClaude
from seeds.scripts._clinical import (
    DISCHARGE_COUNTS,
    DISCHARGE_SCENARIOS,
    WESTERN_PA_HOSPITALS,
)
from seeds.scripts._npi import generate_npi
from seeds.scripts._pdf import DischargePayload, degrade_to_fax, render_discharge_pdf
from seeds.scripts._utils import (
    DATA_DIR,
    DOCUMENTS_DIR,
    GENERATION_LOG,
    LLM_FIXTURES_DIR,
    SCHEMAS_DIR,
    assert_no_phi_keywords,
    make_faker,
    run_log,
    write_bytes,
    write_json,
)


DISCHARGE_SYSTEM_PROMPT = (
    "You are a hospitalist physician dictating the hospital-course section of "
    "a discharge summary. Use realistic clinical language with cardiology "
    "abbreviations (EF, NSTEMI, PCI, LV, BNP, etc.). Cover: reason for "
    "admission, key clinical events during the stay, response to treatment, "
    "and discharge planning rationale. Around 250-320 words across 2-3 short "
    "paragraphs. "
    "STRICT: do NOT include structured fields with labels — no lines like "
    "'MRN: 12345', 'NPI: ...', 'CPT: ...', 'ICD-10: ...', 'SSN: ...', 'DOB: ...', "
    "'Member ID: ...'. Those fields are in a separate structured section. "
    "Focus only on the prose hospital course."
)


GENERATION_ANCHOR = date(2026, 5, 19)


def _sex_for_patient(patient: dict) -> str:
    h = int(hashlib.sha256(patient["external_id"].encode("utf-8")).hexdigest(), 16)
    return "male" if (h % 2 == 0) else "female"


def _age_from_dob(dob: str) -> int:
    dob_d = date.fromisoformat(dob)
    age = GENERATION_ANCHOR.year - dob_d.year
    if (GENERATION_ANCHOR.month, GENERATION_ANCHOR.day) < (dob_d.month, dob_d.day):
        age -= 1
    return age


def _weighted_choice(rng: random.Random, choices: list[tuple[str, float]]) -> str:
    r = rng.random()
    acc = 0.0
    for label, weight in choices:
        acc += weight
        if r <= acc:
            return label
    return choices[-1][0]


def _patient_index_for_doc(doc_index: int, num_patients: int) -> int:
    """Stride of 4 + offset, so discharge docs don't trivially share patients with referrals."""
    return (doc_index * 4 + 3) % num_patients


def _hospital_for_doc(doc_index: int) -> str:
    return WESTERN_PA_HOSPITALS[(doc_index - 1) % len(WESTERN_PA_HOSPITALS)]


def _hospital_address(hospital_name: str) -> str:
    """Static address per hospital so reportlab output is deterministic."""
    # Hand-picked plausible (publicly-known) hospital addresses.
    addresses = {
        "UPMC Presbyterian": "200 Lothrop St, Pittsburgh, PA 15213",
        "UPMC Shadyside": "5230 Centre Ave, Pittsburgh, PA 15232",
        "UPMC Mercy": "1400 Locust St, Pittsburgh, PA 15219",
        "UPMC Passavant": "9100 Babcock Blvd, Pittsburgh, PA 15237",
        "AHN Allegheny General Hospital": "320 East North Ave, Pittsburgh, PA 15212",
        "AHN West Penn Hospital": "4800 Friendship Ave, Pittsburgh, PA 15224",
        "AHN Forbes Hospital": "2570 Haymaker Rd, Monroeville, PA 15146",
        "St. Clair Hospital": "1000 Bower Hill Rd, Pittsburgh, PA 15243",
        "Excela Health Westmoreland Hospital": "532 W Pittsburgh St, Greensburg, PA 15601",
        "Heritage Valley Beaver": "1000 Dutch Ridge Rd, Beaver, PA 15009",
    }
    return addresses[hospital_name]


def _is_degraded(doc_index: int) -> bool:
    """3 of every 10 docs are degraded; for the 20-doc corpus this is 6 of 20."""
    return (doc_index % 10) in (2, 5, 8)


def _build_prompt(
    scenario_key: str,
    age: int,
    sex: str,
    primary_diagnosis: str,
    icd10_codes: list[str],
    los_days: int,
) -> str:
    scenario = DISCHARGE_SCENARIOS[scenario_key]
    return (
        f"Write the hospital course for a {scenario.label} discharge summary.\n\n"
        f"Patient: {age}-year-old {sex}.\n"
        f"Length of stay: {los_days} days.\n"
        f"Primary discharge diagnosis: {primary_diagnosis}.\n"
        f"Working ICD-10: {', '.join(icd10_codes)}.\n\n"
        f"Write only the hospital-course prose paragraphs. No bullet points, "
        f"no headers, no signature. Just the body."
    )


def generate(seed: int, limit: int | None = None) -> None:
    rng = random.Random(seed)
    fake = make_faker(seed + 1)  # offset from patient/practice seeds to vary attending names

    patients = json.loads((DATA_DIR / "patients.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (SCHEMAS_DIR / "discharge_ground_truth.schema.json").read_text(encoding="utf-8")
    )

    claude = FixtureBackedClaude(fixtures_dir=LLM_FIXTURES_DIR)
    discharges_dir = DOCUMENTS_DIR / "discharges"

    doc_index = 0
    with run_log(GENERATION_LOG, "generate_discharges") as log:
        for discharge_type, count in DISCHARGE_COUNTS.items():
            scenario = DISCHARGE_SCENARIOS[discharge_type]
            for _ in range(count):
                doc_index += 1
                if limit is not None and doc_index > limit:
                    print(f"--limit {limit} reached; stopping early")
                    return
                doc_external_id = f"DIS-{doc_index:03d}"

                patient = patients[_patient_index_for_doc(doc_index, len(patients))]
                age = _age_from_dob(patient["dob"])
                sex = _sex_for_patient(patient)
                hospital = _hospital_for_doc(doc_index)
                hospital_addr = _hospital_address(hospital)

                # Coin attending name + NPI deterministically per doc.
                attending_first = fake.first_name()
                attending_last = fake.last_name()
                attending_npi = generate_npi(rng)

                # Sample admit + discharge dates: 3-7 day stays, discharge within 1-30 days of anchor.
                discharge_offset = rng.randint(-30, -1)
                los_days = rng.randint(3, 7)
                discharge_d = GENERATION_ANCHOR + timedelta(days=discharge_offset)
                admit_d = discharge_d - timedelta(days=los_days)

                # Diagnosis + ICD
                primary_diagnosis = rng.choice(scenario.primary_diagnosis_options)
                icd10 = list(rng.choice(scenario.icd10_combinations))

                # Procedures (deep copy so we don't mutate the scenario)
                procedures_raw = list(rng.choice(scenario.typical_procedures))
                procedures = [
                    {"description": desc, "cpt_code": cpt}
                    for (desc, cpt) in procedures_raw
                ]

                # Medications: 2-4 from the pool, no duplicates.
                med_count = rng.randint(2, 4)
                med_pool = list(scenario.medication_change_pool)
                rng.shuffle(med_pool)
                medications_changed = [
                    {"name": name, "action": action}
                    for (name, action) in med_pool[:med_count]
                ]

                # Urgency tier
                urgency_tier = _weighted_choice(rng, scenario.urgency_tier_choices)

                # Urgent flags: 1-3 from the scenario pool
                flag_count = rng.randint(1, min(3, len(scenario.urgent_flag_options)))
                flag_pool = list(scenario.urgent_flag_options)
                rng.shuffle(flag_pool)
                urgent_flags = flag_pool[:flag_count]

                # Follow-up
                fu_low, fu_high = scenario.follow_up_window_days_range
                follow_up_window_days = rng.randint(fu_low, fu_high)

                # Narrative via Claude
                prompt = _build_prompt(
                    discharge_type, age, sex, primary_diagnosis, icd10, los_days
                )
                result = claude.generate(
                    system=DISCHARGE_SYSTEM_PROMPT,
                    prompt=prompt,
                    max_tokens=1100,
                )
                log.api_calls += 0 if result.from_fixture else 1
                log.input_tokens += result.input_tokens
                log.output_tokens += result.output_tokens
                if not result.from_fixture:
                    log.usd_cost += result.usd_cost
                narrative = result.content
                assert_no_phi_keywords(narrative, where=doc_external_id)

                # Build ground truth
                missing_fields: list[str] = []
                for issue in patient.get("data_quality_issues", []):
                    if issue == "missing_phone":
                        missing_fields.append("patient.phone")
                    elif issue == "partial_address":
                        missing_fields.append("patient.address_line1")
                    elif issue == "missing_zip":
                        missing_fields.append("patient.zip_code")
                missing_fields = sorted(set(missing_fields))

                ground_truth = {
                    "document_external_id": doc_external_id,
                    "classification": "discharge_summary",
                    "discharge_type": discharge_type,
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
                    "discharging_hospital": hospital,
                    "attending_physician": {
                        "first_name": attending_first,
                        "last_name": attending_last,
                        "npi": attending_npi,
                    },
                    "admit_date": admit_d.isoformat(),
                    "discharge_date": discharge_d.isoformat(),
                    "primary_diagnosis": primary_diagnosis,
                    "diagnosis_codes": icd10,
                    "procedures_performed": procedures,
                    "medications_changed": medications_changed,
                    "follow_up_window_days": follow_up_window_days,
                    "recommended_specialist": "Cardiology",
                    "urgent_flags": urgent_flags,
                    "urgency_tier": urgency_tier,
                    "missing_fields": missing_fields,
                    "is_degraded": _is_degraded(doc_index),
                }
                jsonschema.validate(ground_truth, schema)

                # Build PDF payload
                primary_ins = patient["insurance"]["primary"]
                payload = DischargePayload(
                    document_external_id=doc_external_id,
                    discharge_type_label=scenario.label,
                    discharging_hospital=hospital,
                    hospital_address=hospital_addr,
                    attending_first_name=attending_first,
                    attending_last_name=attending_last,
                    attending_npi=attending_npi,
                    patient_first_name=patient["first_name"],
                    patient_last_name=patient["last_name"],
                    patient_dob=patient["dob"],
                    patient_phone=patient["phone"],
                    patient_address_line1=patient["address_line1"],
                    patient_city=patient["city"],
                    patient_state=patient["state"],
                    patient_zip=patient["zip_code"],
                    patient_mrn=patient["mrn"],
                    insurance_primary_payer=primary_ins["payer"],
                    insurance_primary_member_id=primary_ins["member_id"],
                    admit_date=admit_d.isoformat(),
                    discharge_date=discharge_d.isoformat(),
                    primary_diagnosis=primary_diagnosis,
                    icd10_codes=icd10,
                    procedures=procedures_raw,
                    medications=[(m["name"], "", m["action"]) for m in medications_changed],
                    follow_up_window_days=follow_up_window_days,
                    recommended_specialist="Cardiology",
                    urgency_tier=urgency_tier,
                    urgent_flags=urgent_flags,
                    hospital_course=narrative,
                )
                pdf_bytes = render_discharge_pdf(payload)
                if ground_truth["is_degraded"]:
                    pdf_bytes = degrade_to_fax(pdf_bytes, seed=seed + 1000 + doc_index)

                pdf_path = discharges_dir / f"{doc_external_id}.pdf"
                gt_path = discharges_dir / f"{doc_external_id}.ground-truth.json"
                write_bytes(pdf_path, pdf_bytes)
                write_json(gt_path, ground_truth)

                log.items += 1
                print(
                    f"  {doc_external_id} ({discharge_type:<13}) "
                    f"degraded={'Y' if ground_truth['is_degraded'] else 'N'} "
                    f"tier={urgency_tier} "
                    f"{'[fixture]' if result.from_fixture else f'[api ${result.usd_cost:.4f}]'}"
                )

        print(
            f"\nAPI calls: {log.api_calls}  "
            f"input_tokens: {log.input_tokens}  "
            f"output_tokens: {log.output_tokens}  "
            f"cost: ${log.usd_cost:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic discharge PDFs + ground truth.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    generate(seed=args.seed, limit=args.limit)


if __name__ == "__main__":
    main()
