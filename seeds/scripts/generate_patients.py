"""Generate seeds/data/patients.json — 20 synthetic Western-PA patients.

Deterministic given --seed. Re-runs produce byte-identical output.

Distribution:
- Ages 45-80 (DOBs back-calculated from a fixed 2026-01-01 anchor for
  reproducibility — never `datetime.now()`).
- 6 payers: Highmark, UPMC, Aetna, UnitedHealthcare, Cigna, Medicare.
  - 65+ → Medicare is the primary payer.
  - <65 → uniformly sampled from the other 5.
- ~30% have a secondary policy.
- 4 of 20 (20%) carry intentional data_quality_issues for eval realism:
  missing_phone, malformed_member_id, partial_address, missing_zip.

Run with:
    uv --project apps/api run python -m seeds.scripts.generate_patients --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

import jsonschema
from faker import Faker

from seeds.scripts._geo import western_pa_address, western_pa_phone
from seeds.scripts._utils import (
    DATA_DIR,
    GENERATION_LOG,
    SCHEMAS_DIR,
    make_faker,
    run_log,
    write_json,
)

# Fixed reference date so age→DOB is deterministic across calendar dates.
AGE_ANCHOR = date(2026, 1, 1)

PAYERS_NON_MEDICARE = [
    "Highmark BCBS PA",
    "UPMC Health Plan",
    "Aetna",
    "UnitedHealthcare",
    "Cigna",
]

# Per-payer member-ID generator. Patterns are illustrative — format-valid
# but never validated against any real payer's database.
PAYER_MEMBER_ID_PATTERNS = {
    "Highmark BCBS PA": "???#########",  # 3 letters + 9 digits
    "UPMC Health Plan": "U########",  # U + 8 digits
    "Aetna": "W#########",  # W + 9 digits
    "UnitedHealthcare": "##########",  # 10 digits
    "Cigna": "U#########",  # U + 9 digits
    "Medicare": "#???-##?-####",  # MBI format: 11 chars
}


def _dob_for_age(age: int, rng: random.Random) -> str:
    """Return YYYY-MM-DD for a given age relative to the anchor date."""
    days_offset = rng.randint(0, 364)
    dob = AGE_ANCHOR.replace(year=AGE_ANCHOR.year - age - 1) + timedelta(days=days_offset)
    return dob.isoformat()


def _member_id(payer: str, fake: Faker) -> str:
    pattern = PAYER_MEMBER_ID_PATTERNS[payer]
    return fake.bothify(pattern).upper()


def _malformed_member_id(payer: str, fake: Faker, rng: random.Random) -> str:
    """Return a member ID that VIOLATES the payer's expected format."""
    # Strategy: too short, or includes a space, or wrong prefix letter.
    bad = _member_id(payer, fake)
    flip = rng.choice(["truncate", "insert_space", "wrong_prefix"])
    if flip == "truncate":
        return bad[: max(3, len(bad) // 2)]
    if flip == "insert_space":
        mid = len(bad) // 2
        return bad[:mid] + " " + bad[mid:]
    # wrong_prefix: prepend a digit even if payer expects letter (or vice versa)
    return "Z" + bad


def generate(seed: int) -> list[dict]:
    fake = make_faker(seed)
    rng = random.Random(seed)

    # Pick 4 of 20 patient indices to carry intentional data-quality issues.
    quality_issue_indices = sorted(rng.sample(range(20), k=4))
    quality_issue_map = {
        quality_issue_indices[0]: "missing_phone",
        quality_issue_indices[1]: "malformed_member_id",
        quality_issue_indices[2]: "partial_address",
        quality_issue_indices[3]: "missing_zip",
    }

    records: list[dict] = []
    for i in range(20):
        age = rng.randint(45, 80)
        dob = _dob_for_age(age, rng)

        # Insurance
        primary_payer = (
            "Medicare" if age >= 65 else rng.choice(PAYERS_NON_MEDICARE)
        )
        # 30% have a secondary; 65+ Medicare patients lean toward a Medigap-style secondary.
        has_secondary = rng.random() < 0.30
        secondary_payer = (
            rng.choice([p for p in PAYERS_NON_MEDICARE if p != primary_payer])
            if has_secondary
            else None
        )

        issue = quality_issue_map.get(i)

        # Member IDs
        if issue == "malformed_member_id":
            primary_member_id = _malformed_member_id(primary_payer, fake, rng)
        else:
            primary_member_id = _member_id(primary_payer, fake)
        primary_group = fake.bothify("GRP-####") if rng.random() < 0.7 else None

        secondary_policy = None
        if secondary_payer is not None:
            secondary_policy = {
                "payer": secondary_payer,
                "member_id": _member_id(secondary_payer, fake),
                "group_number": fake.bothify("GRP-####") if rng.random() < 0.6 else None,
            }

        # Address (apply partial_address / missing_zip issue if assigned)
        addr = western_pa_address(fake, rng)
        if issue == "partial_address":
            addr["address_line1"] = ""  # missing street
        if issue == "missing_zip":
            addr["zip_code"] = ""  # missing zip

        # Phone (apply missing_phone if assigned)
        phone = western_pa_phone(rng) if issue != "missing_phone" else None

        record = {
            "external_id": f"PAT-{i + 1:03d}",
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "dob": dob,
            "phone": phone,
            "ssn": None,  # rarely populated; left null for v1 corpus
            "email": fake.safe_email(),
            "address_line1": addr["address_line1"] or None,
            "address_line2": None,
            "city": addr["city"],
            "state": addr["state"],
            "zip_code": addr["zip_code"] or None,
            "mrn": f"MRN-{fake.unique.numerify('######')}",
            "insurance": {
                "primary": {
                    "payer": primary_payer,
                    "member_id": primary_member_id,
                    "group_number": primary_group,
                },
                "secondary": secondary_policy,
            },
            "data_quality_issues": [issue] if issue else [],
        }
        records.append(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic patient corpus.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "patients.json",
    )
    args = parser.parse_args()

    schema_path = SCHEMAS_DIR / "patient_record.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    with run_log(GENERATION_LOG, "generate_patients") as log:
        records = generate(args.seed)
        log.items = len(records)
        jsonschema.validate(records, schema)
        write_json(args.output, records)

    print(f"wrote {len(records)} patients → {args.output}")


if __name__ == "__main__":
    main()
