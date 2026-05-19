---
description: Add a ground-truth document to the extraction eval set with a guided prompt
---

# /new-extraction-case — Add an eval ground-truth case

**Status: stub — implemented in Module 2.**

Will:

1. Prompt for the document type (referral / discharge_summary / lab / imaging / other).
2. Prompt for the source PDF path (or generate a synthetic one).
3. Walk the user through the ground-truth field set: patient demographics, DOB, phone, address, insurance (payer + member ID + group), referring provider/practice, diagnosis (ICD codes), procedures (CPT codes), urgency, follow-up window.
4. Write the case as a JSON record under `ai/evals/extraction/test_set_vN.json` (appending; bumping the test_set version).
5. Bump the version reference in `ai/evals/README.md`.
6. Trigger `/eval` to re-baseline.

Until Module 2 lands, this command should report: "Eval set not yet implemented — lands in Module 2 (`feat/extraction-review` branch)."
