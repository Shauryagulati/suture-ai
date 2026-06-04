# ADR 008 — Inline (synchronous) post-classification extraction

**Status:** Superseded by the 2026-06-03 amendment below (was: Accepted 2026-05-21)
**Author:** Shaurya

> ## Amendment (2026-06-03): moved to a FastAPI BackgroundTask
>
> The original decision ran OCR → classify → extract **inline** in the upload
> request. On the local default model that blocked the upload ~25s with no
> feedback — a real throughput problem for a coordinator processing a fax stack.
>
> **New decision:** the upload route now persists the document at
> `status=uploaded`, returns `201` immediately, and hands OCR/classify/extract to
> a `BackgroundTask` (`_process_document` in `app/routers/documents.py`). The task
> owns its own session and re-establishes the tenant/user ContextVars (it runs
> outside the request scope). The inbox shows the document advancing through
> `classifying → classified → extracting → extracted` and auto-refreshes while
> anything is in flight.
>
> **Why BackgroundTask, not Celery (yet):** no extra worker process to run for a
> local/demo deployment. The original "drop into Celery" rollback plan below
> still holds for multi-worker production — the only change is that the task body
> already exists as `_process_document` and would move into a `@shared_task`.
>
> **Trade-off accepted:** the upload *response* no longer carries the
> classification/extraction result (it reflects the just-saved document); callers
> read the processed state from the document detail / list once the pipeline
> completes.

## Context

Module 2 turns "this is a referral, 92% confident" into "here are 15
structured fields with per-field confidence scores." We needed to choose
where the extraction step runs in the request lifecycle.

Two real options:

1. **Inline, after classification, inside the upload route.** The
   FastAPI handler awaits `extract_document` between
   `doc.status = classified` and the final `db.commit()`. One HTTP
   request → one fully-processed document.
2. **Celery task fired from the upload route.** The route returns 201
   immediately at `classified`, a worker picks the document up, sets
   `extracting`, calls the LLM, lands the row, sets `extracted`. The
   frontend polls or subscribes.

Constraints:

- v1 is solo + local-only. The infra is already running Celery
  (Module 3a workflow tasks), so the worker exists.
- LLM calls against local Ollama (medgemma1.5 4B) take ~5–15s. Cloud
  calls (Sonnet) are ~2–5s.
- Demo narrative wants "upload a fax, watch the structured data appear
  in the review queue" without an explicit refresh.
- The portfolio audience is technical — they'll forgive a 10–20s
  upload spinner if the trade-off is honest, but they won't forgive
  silent failures.

## Decision

**Inline.** Wired in `apps/api/app/routers/documents.py`: after
classification lands, if the verdict is `referral` or
`discharge_summary`, the route flips status to `extracting`, awaits
`extract_document`, and flips to `extracted` on success.

Failure handling is non-fatal:

- Any uncaught exception inside `extract_document` is logged as
  `documents.extraction_failed` and rolls the document status back to
  `classified`. The upload still returns 201. A future Celery job or a
  manual re-run can retry.
- A graceful parse failure (LLM returns non-JSON) lands a
  `DocumentExtraction` row with `extraction_data={}`,
  `missing_fields=["__parse_failed__"]`, and
  `human_review_required=True`. The doc still moves to `extracted` so
  the operator sees it in the review queue.

The service interface (`async extract_document(*, document_id, db) ->
DocumentExtraction`) is intentionally Celery-shaped: the caller passes
the document id and a session, the function does its own LLM call and
DB writes, and never raises for "normal" failures. Migrating to a
Celery task is a 20-line change — wrap the function call in
`@shared_task`, dispatch from the route instead of awaiting.

## Consequences

### Positive

- One commit chain: upload → OCR → classify → extract → review queue.
  No polling, no race between "doc exists" and "extraction exists."
- The review-queue badge is consistent immediately after upload.
- Tests are simpler: integration tests can mock the LLM and assert the
  full pipeline ran in a single HTTP request.

### Negative

- The upload endpoint blocks for ~10–20s with local Ollama. The Module
  1 upload UI already shows a spinner so this is not a regression —
  just slower.
- A misbehaving LLM provider (e.g., Ollama hung) ties up an HTTP
  worker until the timeout fires. Acceptable for v1; mitigated by the
  120s httpx timeout on `OllamaProvider`.
- The extraction service shares the request's DB session, so a single
  upload can produce two `AiInvocation` rows (classification +
  extraction) under one transaction. If extraction fails mid-flush,
  classification still commits — desirable, but worth noting.

## Rollback plan

The service is already structured to drop into Celery:

1. Add `@shared_task(name="extraction.extract_document")` wrapper in
   `services/workers/extraction_tasks.py`.
2. In the upload route, replace the inline `await extract_document(...)`
   with `extraction_tasks.delay(document_id=doc.id)` and skip the
   `extracting → extracted` flips (the task does them).
3. Frontend keeps the existing review queue — no change needed.

Estimated effort: <1 day.
