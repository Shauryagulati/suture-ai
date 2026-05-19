# ADR 005 — User identity: globally unique email + clinic_memberships join

**Status:** Accepted (2026-05-18)
**Author:** Shaurya

## Context

The original BIGC brief modeled users as belonging to exactly one clinic (`users.clinic_id` FK). This is brittle:

- A real referral coordinator may work for 2+ practices (a small but real cohort in Western PA).
- A vendor / sysadmin user may need access across clinics.
- Future SSO (Clerk, WorkOS) will return one identity per email and expect to provision multi-tenant access on top.

Two paths were considered:

1. **Composite uniqueness:** `UNIQUE(clinic_id, email)` — same email can exist in multiple clinics as separate users.
2. **Global identity + memberships:** `users.email` globally unique; `clinic_memberships(user_id, clinic_id, role, is_default)` joins users to clinics.

## Decision

Option 2 — global identity + `clinic_memberships`.

- `users.email` is globally unique (Postgres `citext` for case-insensitive comparison).
- `users` has no `clinic_id`. Uses `GlobalBase` (skips tenant guard).
- `clinic_memberships(user_id, clinic_id, role, is_default)` joins. Unique `(user_id, clinic_id)`. At most one `is_default=true` per user (partial unique index).
- JWT carries `clinic_id` (the active membership) — the tenant guard reads it from the ContextVar.
- Clinic switching is a future endpoint (Module 1 era). Foundation: login defaults to the user's default membership.

## Consequences

### Positive
- One identity per human, even across clinics.
- SSO migration path is clean: external IdP returns email, we look up users.
- A user losing access to a clinic = revoke one membership row, not delete-and-recreate.
- The tenant guard still works unchanged — it reads `clinic_id` from the JWT, which the login flow validates against memberships.

### Negative
- Login is slightly more complex: validate password, load memberships, pick the default, mint JWT.
- Clinic switching requires a new endpoint that re-mints the JWT with a different `clinic_id` (Module 1+).
- A bug in the membership check at login could let a user mint a JWT for a clinic they don't belong to — covered by `test_auth_tenant_binding.py::test_jwt_with_unauthorized_clinic_rejected`.

## Revisit when

- We add SSO — the identity row becomes a "shadow" of the IdP user; verify the email-unique constraint still holds.
- We add a "vendor" user type that intentionally has access to all clinics — likely a special role with no memberships, plus a guard exception.
