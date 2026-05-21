# Synthetic referral + discharge corpus

> **All names, addresses, phone numbers, NPIs, member IDs, and clinical
> narratives in this corpus are synthetic. No real patient data appears
> anywhere.**

50 PDFs (30 referrals + 20 discharge summaries) plus a matching
ground-truth JSON per PDF. The PDFs are the input to Module 2's
extraction harness; the ground-truth files are what the harness asserts
against. Together they ARE the eval signal — do NOT regenerate without
intent.

## Layout

```
seeds/documents/
├── referrals/
│   ├── REF-001.pdf
│   ├── REF-001.ground-truth.json
│   ├── ...
│   ├── REF-030.pdf
│   └── REF-030.ground-truth.json
└── discharges/
    ├── DIS-001.pdf
    ├── DIS-001.ground-truth.json
    ├── ...
    ├── DIS-020.pdf
    └── DIS-020.ground-truth.json
```

## Generation cost (one-time, first run)

| Step | API calls | Input tokens | Output tokens | USD cost |
|---|---|---|---|---|
| `generate_patients` (no API) | 0 | 0 | 0 | $0.00 |
| `generate_practices` (no API) | 0 | 0 | 0 | $0.00 |
| `generate_referrals` (30 Claude Haiku 4.5 calls) | 30 | 8,882 | 10,304 | $0.0604 |
| `generate_discharges` (20 Claude Haiku 4.5 calls) | 20 | 5,458 | 8,794 | $0.0494 |
| **Total** | **50** | **14,340** | **19,098** | **$0.1098** |

Cost cap: $5.00 (hard stop in `_claude.py`).

Subsequent runs of `make seed-synthetic` read from the committed
`seeds/scripts/llm_fixtures/` and make **zero API calls** — output is
byte-identical to the committed corpus.

## Referral catalog

Distribution (asserted): 10 stress_test / 8 echo / 7 cath / 5 ep_study.
Urgency distribution observed at `--seed 42`: 18 routine / 8 urgent /
4 stat. Degraded (faxed-scan overlay): 9 of 30.

| ID | Type | Urgency | Degraded | Missing fields (intentional) |
|---|---|---|---|---|
| REF-001 | stress_test | routine | Y | patient.phone |
| REF-002 | stress_test | urgent  | N | referring_provider.practice_fax |
| REF-003 | stress_test | routine | N | — |
| REF-004 | stress_test | routine | Y | — |
| REF-005 | stress_test | routine | N | — |
| REF-006 | stress_test | routine | N | — |
| REF-007 | stress_test | stat    | Y | patient.mrn |
| REF-008 | stress_test | routine | N | patient.address_line1 |
| REF-009 | stress_test | urgent  | N | patient.zip_code |
| REF-010 | stress_test | routine | N | — |
| REF-011 | echo        | routine | Y | — |
| REF-012 | echo        | stat    | N | referring_provider.practice_fax |
| REF-013 | echo        | routine | N | — |
| REF-014 | echo        | routine | Y | insurance.secondary |
| REF-015 | echo        | routine | N | — |
| REF-016 | echo        | routine | N | — |
| REF-017 | echo        | routine | Y | — |
| REF-018 | echo        | routine | N | — |
| REF-019 | cath        | urgent  | N | — |
| REF-020 | cath        | urgent  | N | — |
| REF-021 | cath        | urgent  | Y | patient.mrn, patient.phone |
| REF-022 | cath        | routine | N | referring_provider.practice_fax |
| REF-023 | cath        | urgent  | N | — |
| REF-024 | cath        | routine | Y | — |
| REF-025 | cath        | routine | N | — |
| REF-026 | ep_study    | urgent  | N | — |
| REF-027 | ep_study    | stat    | Y | — |
| REF-028 | ep_study    | routine | N | insurance.secondary, patient.address_line1 |
| REF-029 | ep_study    | urgent  | N | patient.zip_code |
| REF-030 | ep_study    | stat    | N | — |

## Discharge catalog

Distribution (asserted): 8 post_mi / 5 post_chf / 4 post_cath / 3 post_ablation.
Urgency-tier distribution observed at `--seed 42`: 3 critical / 5 high /
9 medium / 3 routine. Degraded: 6 of 20.

| ID | Type | Urgency tier | Degraded | Missing fields (intentional) |
|---|---|---|---|---|
| DIS-001 | post_mi       | critical | N | patient.address_line1 |
| DIS-002 | post_mi       | high     | Y | — |
| DIS-003 | post_mi       | high     | N | — |
| DIS-004 | post_mi       | high     | N | — |
| DIS-005 | post_mi       | high     | Y | — |
| DIS-006 | post_mi       | critical | N | patient.address_line1 |
| DIS-007 | post_mi       | medium   | N | — |
| DIS-008 | post_mi       | medium   | Y | — |
| DIS-009 | post_chf      | medium   | N | — |
| DIS-010 | post_chf      | critical | N | — |
| DIS-011 | post_chf      | medium   | N | patient.address_line1 |
| DIS-012 | post_chf      | high     | Y | — |
| DIS-013 | post_chf      | medium   | N | — |
| DIS-014 | post_cath     | medium   | N | — |
| DIS-015 | post_cath     | routine  | Y | — |
| DIS-016 | post_cath     | routine  | N | patient.address_line1 |
| DIS-017 | post_cath     | medium   | N | — |
| DIS-018 | post_ablation | medium   | Y | — |
| DIS-019 | post_ablation | routine  | N | — |
| DIS-020 | post_ablation | medium   | N | — |

## Intentional "missing fields" explained

`missing_fields` is the eval's contract for what the extractor is
NOT expected to find. Three sources:

1. **Patient-level data-quality issues from `patients.json`** —
   PAT-001 lacks a phone; PAT-008 lacks a street; PAT-009 lacks a
   ZIP. Any document referencing those patients carries the matching
   field path in its ground truth.
2. **Practice-level "messy" tier** — PRAC-003/004/008/009 each have
   1-2 nulled fields. Referrals from a messy practice carry the
   matching field path (currently only `referring_provider.practice_fax`).
3. **Doc-level intentional gaps** — every 7th referral (1, 7, 14, 21, 28)
   has one of `insurance.secondary` or `patient.mrn` blanked at the PDF
   layer. The ground truth records the gap so the eval doesn't
   over-penalize the model for legitimately-absent values.

## Why ARE the PDFs committed?

The same reason the LLM fixtures are committed: these are the
**reference inputs** to the eval, not regenerable artifacts. The
extraction model is evaluated against the byte-exact corpus that
shipped with this commit. Regenerating with a different seed, or
with different prompts, would shift the corpus under the eval and
make accuracy numbers across runs incomparable.

If the corpus genuinely needs to evolve (new scenarios, new code
combinations), make the change deliberately: edit the generators,
re-run `make seed-synthetic`, eyeball the diff in `git status`, and
commit the new corpus together with the prompt/code change that
produced it. The PDF binary diffs are large but the JSON ground truth
makes the actual semantic change reviewable.

## No-PHI guarantee

See `seeds/data/README.md` for the field-by-field breakdown. Hospital
names (UPMC Presbyterian, AHN Allegheny General, etc.) are real
institutions — naming a real hospital as the discharging facility on
a synthetic patient is standard for cardiology test corpora and
carries no PHI risk. Every identifier attached to the synthetic
patient is also synthetic.
