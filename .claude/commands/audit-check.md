---
description: Verify a newly-added PHI endpoint correctly logs to audit_logs with no PHI leaked
---

# /audit-check — Audit logging conformance

**Status: stub — implemented in Gate B1.**

Will exercise a newly-added PHI-touching endpoint and assert:

1. An `audit_logs` row was written with the right `user_id`, `clinic_id`, `resource_type`, `resource_id`, and `action` (`view`/`create`/`update`/`delete`).
2. The `details` JSONB column contains **no PHI** — only column names and IDs. (Assertion: serialized JSON does not contain known PHI values from the request.)
3. The `ip_address` was captured from the request middleware.

Run this after adding a new PHI-bearing model or a new GET endpoint that returns PHI.

For GET endpoints: the endpoint must call `track_view()` explicitly — there is no SQLAlchemy event for SELECT.

For mutation endpoints: the event listener handles `after_insert`/`after_update`/`after_delete` automatically, but the model must be registered in `app/utils/audit.py::AUDITED_MODELS`.

Until Gate B1 lands, this command should report: "Audit listener not yet implemented — lands in Gate B1."
