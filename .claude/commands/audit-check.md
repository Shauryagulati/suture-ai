---
description: Verify a newly-added PHI endpoint correctly logs to audit_logs with no PHI leaked
---

# /audit-check — Audit logging conformance

Use this when you've added a new PHI-bearing model or a new GET endpoint that returns PHI, to make sure audit logging is wired and not leaking values.

## What to check

### For a new PHI-bearing model
1. The model inherits `ClinicScopedBase`.
2. It is appended to `app/utils/audit.py::register_audited_models()` so the insert/update/delete listeners attach.
3. A pytest case asserts: creating one writes an `audit_logs` row with `action=create`, correct `resource_type` (table name), and `resource_id == new_row.id`.
4. A pytest case asserts: the `audit_logs.details` JSONB does NOT contain any PHI values from the row (assertion: serialized JSON does not contain the patient's first_name / phone / dob / etc.).

### For a new GET endpoint returning PHI
1. The handler calls `track_view()` from `app/utils/audit.py` after fetching the resource — there is no SQLAlchemy event for SELECT, so view actions are explicit.
2. A pytest case asserts a `view`-action audit row is written.

## Quick run

```bash
cd apps/api && uv run pytest -v tests/test_audit_log.py
```

This passes the two foundation tests:
- `test_patient_create_writes_audit_row`
- `test_audit_details_contains_no_phi`

## Where the listeners are wired

`app/utils/audit.py`:
- `register_audited_models()` — call at import time from `app/models/__init__.py`. Adds insert/update/delete listeners to each model.
- `_audit_after_insert/update/delete` — write the audit row via Core insert (bypasses ORM + the guard).
- `track_view()` — explicit helper for GET endpoints. Reads ContextVars for user_id, clinic_id, ip_address.

## Failure handling

A failing `test_audit_details_contains_no_phi` is a **HIPAA-class** finding (PHI leak path through the audit table). STOP and surface, do not auto-fix.
