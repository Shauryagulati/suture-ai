---
name: extraction-prompt-skill
description: Use when writing or modifying a Claude extraction prompt for referrals, discharge summaries, labs, or imaging. Stub — filled in Module 2.
---

# Extraction prompt skill

**Status: stub — fully written in Module 2 (`feat/extraction-review` branch).**

Will document:
- The tool-use schema for structured field extraction (patient demographics, DOB, phone, address, insurance, referring provider, diagnoses ICD-10, procedures CPT, urgency, follow-up window, missing fields).
- The per-field confidence-score convention (0.0–1.0, with a calibration test against ground truth).
- The prompt versioning protocol (semver-style, file path `ai/prompts/extraction/v<major>.<minor>.md`, the eval harness gates on regressions).
- The audit + `ai_invocations` requirements: every extraction logs prompt/response summaries (PHI-stripped), tokens, latency, cost, model.
- How to add a new document type (extends classifier enum, adds extraction prompt variant, adds eval cases).

Until Module 2 lands, anyone touching extraction prompts should pause and align on this design with Shaurya first.
