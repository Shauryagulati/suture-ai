---
name: audit-logging-skill
description: Use when adding a PHI-bearing model or a PHI-returning endpoint. Documents the audit listener registry, the audit_logs row shape, and how to write track_view() correctly.
---

# Audit logging skill

This skill is the reference for wiring audit on a new PHI-bearing model or a new GET endpoint that returns PHI. Failures in this layer are HIPAA-class — read carefully.

## How audit gets emitted

Two paths:

### 1. SQLAlchemy event listeners (mutations)

`app/utils/audit.py::register_audited_models()` attaches `after_insert` / `after_update` / `after_delete` listeners on every class in `AUDITED_MODELS`. They fire on `Session.commit()` and write a row to `audit_logs` via a Core insert (bypasses the ORM, so the tenant guard doesn't apply).

The row shape:

| Column | Source |
|---|---|
| `id` | new UUID |
| `clinic_id` | `target.clinic_id` (or NULL for system events) |
| `user_id` | `current_user_id.get()` from ContextVar |
| `action` | `create` / `update` / `delete` |
| `resource_type` | `target.__tablename__` |
| `resource_id` | `target.id` |
| `details` | JSONB — IDs and column names only, **never PHI values** |
| `ip_address` | `current_ip_address.get()` from ContextVar |
| `timestamp` | server `now()` |

### 2. Explicit `track_view()` (reads)

SQLAlchemy has no `after_select` event for ORM reads. GET endpoints that return PHI must call `track_view()` from the handler:

```python
from app.utils.audit import track_view

@router.get("/patients/{patient_id}")
async def get_patient(
    patient_id: UUID,
    user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PatientResponse:
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404)
    # Audit the read.
    await db.connection().run_sync(
        lambda conn: track_view(
            conn,
            resource_type="patients",
            resource_id=patient_id,
        )
    )
    return PatientResponse.model_validate(patient)
```

## Adding a new audited model

1. Define the model inheriting `ClinicScopedBase`.
2. Add it to `app/utils/audit.py::register_audited_models()`:

```python
def register_audited_models() -> None:
    from app.models import Patient, Document  # ← add new model here

    AUDITED_MODELS.clear()
    AUDITED_MODELS.extend([Patient, Document])
    ...
```

3. Add a pytest case (style: `tests/test_audit_log.py`) asserting:
   - Insert writes a row with the right `action`, `resource_type`, `resource_id`.
   - `details` JSON contains no PHI from the inserted row.

## The PHI-in-details rule (load-bearing)

`audit_logs.details` is JSONB and must NEVER contain PHI values. Only:
- IDs (UUIDs)
- Column NAMES that changed (not their values)
- Action-specific flags like `{"created": true}`, `{"changed_columns": ["status", "notes"]}`

The test `test_audit_details_contains_no_phi` enforces this. If you add a new column to `details`, audit it against that test.

## Anti-patterns

- ❌ Logging full row values to `details` ("for debugging"). Use a separate dev log channel; never the audit table.
- ❌ Manually inserting audit rows from a router instead of using the listener — guarantees gaps when developers forget.
- ❌ Marking a PHI model `_audit_exempt = True` without an ADR. The only legitimate audit-exempt table is `audit_logs` itself.
- ❌ Skipping `track_view()` on a GET endpoint because "we're rate-limited so audit isn't that important." Compliance says otherwise.

## Verification

`/audit-check` slash command runs the two foundation tests on demand:

```bash
cd apps/api && uv run pytest -v tests/test_audit_log.py
```
