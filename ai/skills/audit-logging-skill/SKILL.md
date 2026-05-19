---
name: audit-logging-skill
description: Use when adding a PHI-bearing model or a PHI-returning endpoint. Stub — filled in Gate B1.
---

# Audit logging skill

**Status: stub — fully written in Gate B1.**

Will document:
- How `app/utils/audit.py::AUDITED_MODELS` works — registering a new PHI-bearing model adds it to the event listener.
- The shape of an `audit_logs` row: `clinic_id`, `user_id`, `action` (`view`/`create`/`update`/`delete`/`export`/`ai_query`), `resource_type`, `resource_id`, `details` (JSONB — IDs and column names ONLY, never PHI values), `ip_address` (from `current_ip_address` ContextVar), `timestamp`.
- The `track_view()` helper for GET endpoints — there is no SQLAlchemy event for SELECT, so view actions must be emitted explicitly from the route.
- The PHI-deny-list for `details` serialization (`first_name`, `last_name`, `dob`, `phone`, `email`, `ssn`, `mrn`, etc.) — values in those columns are replaced with `<redacted>` in the audit row, only IDs and column-names-changed survive.
- How `/audit-check` verifies a new endpoint logs correctly.

Until Gate B1 lands, anyone adding a PHI model should pause and align on this design with Shaurya first.
