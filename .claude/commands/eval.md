---
description: Run the AI eval harness and report per-field accuracy/precision/recall metrics
---

# /eval — Run the eval harness

**Status: stub — implemented in Module 2.**

Will run the extraction eval harness against the current prompt version using the ground-truth test set in `ai/evals/`, compute per-field accuracy/precision/recall/F1, write a row to `eval_runs`, and report a summary table to the console.

Until Module 2 lands, this command should report: "Eval harness not yet implemented — lands in Module 2 (`feat/extraction-review` branch)."

## Future behavior (Module 2+)

1. Load the latest test set version from `ai/evals/extraction/test_set_vN.json`.
2. Run extractions against each document (with `OTEL_DISABLED=0` to capture trace).
3. Compare to ground truth, compute metrics per field.
4. Insert one `eval_runs` row with `eval_type=extraction`, full metrics JSON, model + prompt version.
5. If accuracy regresses vs. the previous run, exit non-zero so CI can block the PR.
6. Print a markdown table grouped by field with current vs. previous deltas.
