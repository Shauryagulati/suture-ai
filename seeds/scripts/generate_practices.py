"""Generate seeds/data/referring_practices.json — 10 synthetic Western-PA referring practices.

Deterministic given --seed.

Distribution:
- 6 "clean" practices: every field populated.
- 4 "messy" practices: 1–2 fields nulled from {practice_fax, practice_address, specialty}.
  Never NPI, never practice_name, never provider name — those are required.
- Specialties: ~70% Internal Medicine / 20% Family Medicine / 10% Hospital Medicine.

Run with:
    uv --project apps/api run python -m seeds.scripts.generate_practices --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import jsonschema

from seeds.scripts._geo import western_pa_address, western_pa_phone
from seeds.scripts._npi import generate_npi
from seeds.scripts._utils import (
    DATA_DIR,
    GENERATION_LOG,
    SCHEMAS_DIR,
    make_faker,
    run_log,
    write_json,
)

# Hand-coined practice name templates that read like real PCP offices in the
# Pittsburgh footprint. The template + city combo yields varied output.
PRACTICE_NAME_TEMPLATES = [
    "{neighborhood} Internal Medicine",
    "{neighborhood} Primary Care Associates",
    "{neighborhood} Family Practice",
    "{neighborhood} Medical Group",
    "{neighborhood} Health Partners",
    "{neighborhood} Community Health",
]

NEIGHBORHOOD_POOL = [
    "North Hills",
    "South Hills",
    "Mon Valley",
    "Highland Park",
    "Greater Pittsburgh",
    "Allegheny",
    "Murrysville",
    "Squirrel Hill",
    "Greentree",
    "Robinson",
    "Wexford",
    "Sewickley",
]

SPECIALTY_WEIGHTS = [
    ("Internal Medicine", 0.7),
    ("Family Medicine", 0.2),
    ("Hospital Medicine", 0.1),
]


def _weighted_choice(rng: random.Random, choices: list[tuple[str, float]]) -> str:
    r = rng.random()
    acc = 0.0
    for label, weight in choices:
        acc += weight
        if r <= acc:
            return label
    return choices[-1][0]


def generate(seed: int) -> list[dict]:
    fake = make_faker(seed)
    rng = random.Random(seed)

    # Pick which 4 indices are "messy" (after the 6 clean).
    indices = list(range(10))
    rng.shuffle(indices)
    messy_indices = set(indices[:4])

    # Track used names to avoid duplicates.
    used_names: set[str] = set()
    used_neighborhoods: list[str] = list(NEIGHBORHOOD_POOL)
    rng.shuffle(used_neighborhoods)

    records: list[dict] = []
    for i in range(10):
        # Pick a non-duplicate practice name.
        name = None
        for _ in range(20):
            neighborhood = used_neighborhoods[i % len(used_neighborhoods)]
            template = rng.choice(PRACTICE_NAME_TEMPLATES)
            candidate = template.format(neighborhood=neighborhood)
            if candidate not in used_names:
                name = candidate
                used_names.add(candidate)
                break
            # If collision, rotate neighborhood and retry.
            used_neighborhoods[i % len(used_neighborhoods)] = rng.choice(NEIGHBORHOOD_POOL)
        assert name is not None, "exhausted practice name templates"

        addr = western_pa_address(fake, rng)
        full_address = f"{addr['address_line1']}, {addr['city']}, {addr['state']} {addr['zip_code']}"

        tier = "messy" if i in messy_indices else "clean"

        specialty: str | None = _weighted_choice(rng, SPECIALTY_WEIGHTS)
        practice_fax: str | None = western_pa_phone(rng)
        practice_address: str | None = full_address

        # Apply messy-tier omissions: pick 1–2 of the three optional fields to null.
        if tier == "messy":
            droppable = ["practice_fax", "practice_address", "specialty"]
            num_to_drop = rng.choice([1, 2])
            to_drop = rng.sample(droppable, k=num_to_drop)
            if "practice_fax" in to_drop:
                practice_fax = None
            if "practice_address" in to_drop:
                practice_address = None
            if "specialty" in to_drop:
                specialty = None

        record = {
            "external_id": f"PRAC-{i + 1:03d}",
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "npi": generate_npi(rng),
            "practice_name": name,
            "practice_phone": western_pa_phone(rng),
            "practice_fax": practice_fax,
            "practice_address": practice_address,
            "provider_type": "referring",
            "specialty": specialty,
            "data_quality_tier": tier,
        }
        records.append(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic referring-practice corpus.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "referring_practices.json",
    )
    args = parser.parse_args()

    schema_path = SCHEMAS_DIR / "referring_practice.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    with run_log(GENERATION_LOG, "generate_practices") as log:
        records = generate(args.seed)
        log.items = len(records)
        jsonschema.validate(records, schema)
        write_json(args.output, records)

    clean = sum(1 for r in records if r["data_quality_tier"] == "clean")
    messy = len(records) - clean
    print(f"wrote {len(records)} practices ({clean} clean, {messy} messy) → {args.output}")


if __name__ == "__main__":
    main()
