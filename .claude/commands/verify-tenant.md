---
description: Quick check that the SQLAlchemy tenant guard is active and rejects cross-clinic reads
---

# /verify-tenant — Tenant isolation smoke check

**Status: stub — implemented in Gate B1.**

Will run the four cases in `apps/api/tests/test_tenant_isolation.py`:

1. **Happy path** — query with clinic-A context returns only clinic-A rows.
2. **Attack path** — query for a specific clinic-B row ID with clinic-A context returns empty (the guard injects the filter).
3. **Missing context** — query with no `current_clinic_id` set raises `TenantContextMissingError`.
4. **Insert mismatch** — inserting with `clinic_id=clinic_b_id` while context is clinic-A is rejected.

Plus a one-shot `SELECT 1 FROM patients` issued without setting the context, asserting the listener raises before SQL leaves the app.

Use this after touching anything in `app/database.py`, `app/models/`, or `app/utils/context.py` to confirm the guard is still active.

Until Gate B1 lands, this command should report: "Tenant guard not yet implemented — lands in Gate B1."
