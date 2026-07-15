# ADR 009 — Deterministic per-field confidence scoring

**Status:** Accepted (2026-05-21) — amended 2026-07-14 (missing_fields precedence)
**Author:** Shaurya

## Context

Module 2's review UI is built around per-field confidence: green badges
on fields the reviewer can trust, red on fields they need to verify.
Two ways to produce those scores:

1. **LLM self-report.** Ask the model to return a `confidence` field per
   extracted value, the way the classification step does.
2. **Deterministic, post-hoc.** The LLM only reports `missing_fields`;
   we compute confidence ourselves from validator passes.

The classification step does (1) and it works fine there — one decision,
one score. But extraction returns ~20 fields per document. LLM
self-confidence is famously poorly-calibrated on structured outputs,
especially on small local models (medgemma1.5 4B), and per-field scoring
makes the prompt longer and noisier.

We also wanted confidence to mean the *same thing* for every reviewer:
"the system validated this value against its format" is verifiable.
"The LLM felt 78% sure" is not.

## Decision

LLM emits `missing_fields[]` (a list of dot-path strings) and nothing
else about confidence. The extraction service computes per-field scores
via `compute_field_confidences()` (
`apps/api/app/services/extraction/confidence.py`) with four fixed bands:

| Value state                       | Score |
|-----------------------------------|-------|
| Present + validator pass          | 0.95  |
| Present + no validator configured | 0.85  |
| Present + validator fail          | 0.40  |
| Value absent (null, or path not in payload) | 0.0 |

**Amendment (2026-07-14).** The table originally scored 0.0 for any path in
`missing_fields`, even when the payload carried a value at that path. That
let the model zero out a validator-passing value — the model grading the
work through a side channel, which is exactly what this ADR exists to
prevent (observed in the field: REF-001 scored five correctly-extracted,
ground-truth-matching fields at 0.0). The sharpened invariant:

> A field's score is a function of its extracted value and its validator,
> nothing else. `missing_fields` is advisory: it surfaces paths absent from
> the payload in the confidence map (score 0.0 — validator-truth, since the
> value is absent) and it forces `needs_review = True`. It never overrides
> the score of a present value. The asymmetry is deliberate: the model may
> demand MORE human review, never less.

Validators (
`apps/api/app/services/extraction/validators.py`):

- `is_valid_icd10` — regex `^[A-Z]\d{2}(\.\d{1,4})?$`
- `is_valid_cpt` — `^\d{5}$`
- `is_valid_npi` — 10 digits + Luhn-mod-10 with `80840` prefix
- `is_valid_phone` / `normalize_phone` — E.164-ish `+1XXXXXXXXXX`
- `is_valid_zip` — `^\d{5}(-\d{4})?$`
- `is_valid_date` — `datetime.fromisoformat`
- `is_valid_state` — 2-letter uppercase

`needs_review` (the row-level flag) is `True` when either
`missing_fields` is non-empty OR any score is below 0.85 — i.e., any
validator failure or any missing value forces a human pass.

## Consequences

### Positive

- **Scores are testable.** `tests/test_extraction_confidence.py` has
  81 unit tests that pin every band. A regression in confidence shows
  up immediately, not "next time someone glances at the badge."
- **PHI-safe.** Confidence computation runs on the already-extracted
  values, in the same process — nothing extra crosses the LLM
  boundary.
- **Cheap.** No extra tokens spent on per-field confidence reasoning.
  Saves ~20–30% on output tokens for the extraction prompt.
- **Stable across model swaps.** Same prompt → different model →
  different extraction quality, but confidence semantics stay
  identical. The eval harness measures *accuracy*; confidence measures
  *trustworthiness of the format*. Decoupling these is the whole
  point.

### Negative

- Validator coverage is binary by field. A "looks plausible" name like
  "Jolnh Smith" (typo) gets 0.85 because we have no validator for
  names. The reviewer still has to read it. We accept this — the
  alternative (an LLM second pass per field) is worse on every axis.
- Validator regexes are deliberately simple. A real ICD-10 like
  `I25.110` passes our regex but isn't actually a valid code (CMS code
  catalogs change quarterly). For v1, format validity is enough.
  Module 4's payer-rule RAG will catch real-code-but-wrong-code
  problems via the eligibility step.
- "Looks fine on screen, secretly wrong" failures (e.g., LLM swaps two
  patients' names but both pass `normalize_name`) score 0.85 and look
  green. Mitigation: the reviewer eyeballs the PDF on the left of the
  split view; the eval harness catches systemic versions of this.

## Alternatives considered

- **LLM-reported confidence.** Rejected for calibration + cost reasons
  above.
- **Hybrid (LLM-reported + validator override).** Considered. Added
  cost without obvious upside — if the validator passes we ignore the
  LLM number anyway; if it fails we override.
- **No confidence at all (just missing/present).** Considered. Loses
  the "validator failed" signal which is the most actionable category
  — an ICD-10 that doesn't match the regex is almost always wrong.

## How to revisit

If field-level validator coverage gets thin enough that "0.85 with no
validator" starts dominating the review experience, add per-field
validators rather than swapping to LLM self-report. The dispatch map is
in `confidence.py::_SCALAR_VALIDATORS` and `_ARRAY_ELEMENT_VALIDATORS`;
new validators are pure functions, no schema migration needed.
