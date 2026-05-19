# Suture — Evaluation Strategy

> Stub. Detail lands in Module 2 (`feat/extraction-review` branch).

## Why we eval

Every Claude-touching feature in Suture ships with an evaluation harness. The audit trail (`eval_runs` table) lets us compare prompt versions, model versions, and refactors over time.

If a prompt change drops accuracy on the eval set, CI blocks the merge.

## Eval categories (planned)

| Category | Module | Test set |
|---|---|---|
| Classification | Module 1 | Ground-truth document type for 30+ synthetic PDFs |
| Extraction | Module 2 | Ground-truth field set for 30 referrals + 20 discharges |
| Retrieval (RAG) | Module 4 | Hand-curated payer-rules Q&A pairs |
| Workflow | Module 3a | Status-transition correctness on canned inputs |
| Voice | Module 6 | Transcript-aligned dialogue scoring |

## Schema (`eval_runs` table)

- `eval_type` enum: `extraction` / `retrieval` / `voice` / `workflow`
- `test_set_version` — bumped when test cases change
- `metrics` JSONB — per-field precision/recall/F1
- `num_samples`
- `run_duration_seconds`
- `prompt_version`
- `model`
- `notes`
- `run_by`

## How to run (planned)

```bash
/eval                          # via Claude Code slash command
make eval                      # CLI shortcut
uv run python -m ai.evals.run  # direct invocation
```

## How to add a case (planned)

```bash
/new-extraction-case
```

Walks through the ground-truth field set, writes the case to `ai/evals/extraction/test_set_vN.json`, bumps version.

Until Module 2 ships, this file is a placeholder.
