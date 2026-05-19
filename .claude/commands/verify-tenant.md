---
description: Quick check that the SQLAlchemy tenant guard is active and rejects cross-clinic reads
---

# /verify-tenant — Tenant isolation smoke check

Runs the four `test_tenant_isolation.py` cases plus the audit assertions to confirm the guard is wired and HIPAA-class controls are intact.

## What it runs

```bash
cd apps/api && uv run pytest -v \
  tests/test_tenant_isolation.py \
  tests/test_audit_log.py \
  tests/test_phi_encryption.py
```

## What the cases assert

| Test | Asserts |
|---|---|
| `test_select_filters_to_current_clinic` | Happy path — clinic A context returns only clinic A rows. |
| `test_select_by_id_in_other_clinic_returns_empty` | **Attack path** — fetching clinic B's specific row ID from clinic A context returns empty (the guard injects `WHERE clinic_id = clinic_a`). |
| `test_query_without_clinic_context_raises` | Missing context — query without ContextVar raises `TenantContextMissingError` (fail closed). |
| `test_insert_with_mismatched_clinic_id_rejected` | `target.clinic_id != current_clinic_id` on INSERT → `TenantContextMismatchError`. |
| `test_patient_create_writes_audit_row` | INSERT on PHI table emits an `audit_logs` row with correct shape. |
| `test_audit_details_contains_no_phi` | Audit `details` JSONB contains no PHI values. |
| `test_*_phi_encryption*` | Fernet columns round-trip plaintext↔ciphertext correctly. |

## When to run

- After touching anything in `app/database.py`, `app/utils/context.py`, `app/utils/audit.py`, `app/utils/encryption.py`.
- After adding a new model that inherits `ClinicScopedBase`.
- Before merging any branch that changes the data layer.

## Failure handling

Per project operational discipline, a failure here is a **HIPAA-class** finding. STOP, surface the full pytest output, do not auto-fix and proceed.
