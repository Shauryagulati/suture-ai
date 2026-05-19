---
name: eval-case-skill
description: Use when adding a ground-truth document to the extraction eval set. Stub — filled in Module 2.
---

# Eval case skill

**Status: stub — fully written in Module 2 (`feat/extraction-review` branch).**

Will document:
- Where eval test sets live (`ai/evals/extraction/test_set_v<N>.json`) and the JSON schema for a case.
- The ground-truth field set (mirrors the extraction tool schema): patient demographics, DOB, phone, address, insurance, referring provider, diagnoses, procedures, urgency, follow-up window, missing fields.
- How to bump the test set version when adding cases (semver-style; the harness records `test_set_version` in `eval_runs`).
- The `/new-extraction-case` slash command that walks you through adding a case interactively.
- The regression-gate convention: a PR that touches a prompt file must run `/eval` and not regress the previous best metric on the current test set.

Until Module 2 lands, anyone adding eval cases should pause and align on this design with Shaurya first.
