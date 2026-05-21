# Synthetic data corpora — patients + referring practices

These JSON files are the structured-record half of the eval corpus.
They are NOT auto-inserted into the database; Module 1's document-upload
pipeline will read them when it lands. The PDFs under `seeds/documents/`
reference patients and practices by `external_id`.

All values are synthetic — see the "No PHI" guarantee at the bottom of
this file and the equivalent section in `seeds/documents/README.md`.

## Files

| File | Records | Schema |
|---|---|---|
| `patients.json` | 20 | `seeds/schemas/patient_record.schema.json` |
| `referring_practices.json` | 10 | `seeds/schemas/referring_practice.schema.json` |

## Reproducibility

```bash
uv --project apps/api run python -m seeds.scripts.generate_patients --seed 42
uv --project apps/api run python -m seeds.scripts.generate_practices --seed 42
```

Same `--seed` produces byte-identical output. Verified post-commit.

## Patient corpus (`patients.json`)

20 records, age 45–80 (DOBs back-calculated from a fixed `2026-01-01`
anchor, so the file is stable across calendar dates).

### City distribution (deterministic at `--seed 42`)

| City | Count |
|---|---|
| Pittsburgh | 4 |
| Butler | 7 |
| Monroeville | 3 |
| Beaver | 2 |
| Washington | 2 |
| Greensburg | 2 |
| Cranberry Twp | 0 (not sampled at this seed; valid in schema) |

### Primary payer distribution

| Payer | Count |
|---|---|
| Highmark BCBS PA | 7 |
| Medicare | 6 |
| Aetna | 3 |
| Cigna | 2 |
| UPMC Health Plan | 1 |
| UnitedHealthcare | 1 |

Patients aged 65+ are placed on Medicare as primary. ~30% have a secondary
policy; 11 of 20 carry one in this seed.

### Intentional data-quality issues

4 of 20 patients (20%) carry one issue from the eval-realism set. These
are NOT model errors — the ground-truth extraction MUST list them under
`missing_fields`.

| Patient ID | Issue |
|---|---|
| PAT-001 | `missing_phone` |
| PAT-004 | `malformed_member_id` (violates payer format) |
| PAT-008 | `partial_address` (street line omitted) |
| PAT-009 | `missing_zip` |

## Referring-practice corpus (`referring_practices.json`)

10 records. The shape mirrors the `Provider` SQLAlchemy model with
`provider_type='referring'`. Module 1's ingest will create one `Provider`
row per record.

### Data-quality tiers

6 "clean" practices (every field populated) + 4 "messy" practices
(1–2 fields null from `{practice_fax, practice_address, specialty}`).
Practice name, provider name, and NPI are NEVER nulled — those are
required for any real-world referral to be actionable.

### Messy practice details (at `--seed 42`)

| Practice ID | Null fields |
|---|---|
| PRAC-003 | `practice_address` |
| PRAC-004 | `specialty` |
| PRAC-008 | `practice_fax` |
| PRAC-009 | `specialty` |

This 60/40 split drives Module 7's referral-source quality scorecard
(due later) — the clean practices should score near 100, the messy
ones in the 60–80 range depending on what's missing.

### Specialty distribution

`Internal Medicine` (~70%) > `Family Medicine` (~20%) > `Hospital Medicine` (~10%),
with 2 null entries from the messy tier.

## No-PHI guarantee

Every value here is synthetic:
- **Names** — Faker en_US Census name corpus.
- **DOBs** — back-calculated from a fixed anchor + seeded random age.
- **Phone numbers** — Pittsburgh-area codes (412/724/878) with the
  NANP-reserved `555` fictional exchange. None are real subscriber
  numbers.
- **Addresses** — Faker-generated street numbers + names. Cities and
  ZIP prefixes are real but the full address is synthetic.
- **NPIs** — Luhn-valid via `seeds/scripts/_npi.py`. Algorithmically
  valid but never validated against the CMS NPI registry.
- **Insurance member IDs** — format-valid per payer pattern, but never
  validated against any real payer's database.
- **MRNs** — practice-internal identifiers with no external significance.

No real patient or provider is targeted or referenced.
