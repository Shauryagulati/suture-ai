# Suture — Evaluation Strategy

Every LLM-touching feature in Suture ships with an evaluation harness. The audit trail
(`eval_runs` table) lets us compare prompt versions, model versions, and refactors over time.
Per-field accuracy is recorded per run so prompt and model changes can be diffed for
regressions. (Automating this as a CI merge-gate is a planned next step — the harness needs a
local Ollama that CI does not yet provide.)

## Extraction eval (shipped)

The extraction harness lives in [`ai/evals/`](../ai/evals) and runs the **real** extraction
pipeline (the same `get_llm_provider()` path used in production) over a synthetic
ground-truth corpus, then scores each predicted field against the ground truth.

```bash
make eval-extraction          # run the harness over the synthetic corpus
```

Pipeline:

1. `eval_extraction.py` loads each ground-truth document + expected field set.
2. It runs extraction through the live provider (local Ollama by default; BYOK Claude/OpenAI).
3. `flatten.py` flattens nested objects to dotted paths (`patient.dob`, `diagnosis_codes[0]`)
   and `normalizers.py` canonicalizes values (dates, phones, codes) before comparison.
4. `compare.py` computes per-field **accuracy, precision, recall, F1**, plus corpus-level
   **exact-match rate** and **macro-F1**.

### Latest results

Synthetic corpus, 50 documents (30 referrals + 20 discharges), local `medgemma1.5`:

| Metric | Value |
|---|---|
| Exact-match rate | 0.669 |
| Macro-F1 | 0.736 |

Per-field breakdowns are written per run; re-run `make eval-extraction` to reproduce. Results
are model-dependent — BYOK Claude Sonnet scores materially higher than the local 4B model.

## Confidence scoring (deterministic, not LLM self-report)

Per-field confidence is computed by validators + a missing-fields check, **not** by asking the
model how sure it is (ADR 009). Format-valid-but-semantically-wrong values can still score
high — the side-by-side review UI and this eval set are the mitigations.

## `eval_runs` schema

- `eval_type` enum: `extraction` / `retrieval` / `voice` / `workflow`
- `test_set_version` — bumped when test cases change
- `metrics` JSONB — per-field precision/recall/F1 + corpus rollups
- `num_samples`, `run_duration_seconds`, `prompt_version`, `model`, `notes`, `run_by`

## Running and comparing

```bash
make eval-extraction                 # CLI shortcut
uv run python -m ai.evals.eval_extraction   # direct invocation
```

Use `ai/evals/compare.py` to diff two runs and confirm a prompt change didn't regress.

## Adding a ground-truth case

```bash
/new-extraction-case          # Claude Code skill — guided ground-truth entry
```

Walks through the expected field set, writes the case into the extraction test set, and bumps
the test-set version.

## Planned categories

| Category | Module | Status |
|---|---|---|
| Extraction | Module 2 | ✅ shipped (above) |
| Classification | Module 1 | planned |
| Retrieval (RAG) | Module 4 | planned — payer-rules Q&A pairs |
| Workflow | Module 3a | planned — status-transition correctness |
| Voice | Module 6 | planned — transcript-aligned dialogue scoring |
