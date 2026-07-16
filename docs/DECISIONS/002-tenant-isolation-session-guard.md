# ADR 002 — Multi-tenant isolation via SQLAlchemy session-level guard

**Status:** Accepted (2026-05-18) — **amended by [ADR 011](./011-tenant-isolation-boundaries.md)**
**Author:** Shaurya

> **Read ADR 011 first.** The decision below (a session-level guard, fail-closed,
> app-layer not RLS) still stands, but the mechanism described in this ADR's prose —
> a `before_execute` listener injecting `WHERE clinic_id = ...` into compiled SQL —
> is **not** what was built. The as-built guard is a `do_orm_execute` listener using
> `with_loader_criteria`. This ADR is left unedited as the historical record of the
> decision; ADR 011 records the as-built mechanism, its one known boundary, and the
> accepted no-RLS posture.

## Context

Suture is a multi-tenant SaaS where each clinic's PHI must be strictly isolated. A single missing `WHERE clinic_id = ...` in a query could leak clinic A's patients to clinic B — a HIPAA-class breach.

Three patterns were considered:

1. **Convention only:** every query must include `clinic_id` in its predicate. Caught by code review.
2. **Postgres Row-Level Security (RLS):** native policies on every table; set `app.clinic_id` via `SET LOCAL` per connection.
3. **SQLAlchemy session-level guard:** a `before_execute` event listener inspects every compiled statement and injects `WHERE clinic_id = :current_clinic_id` if absent.

## Decision

Option 3 — SQLAlchemy session-level guard.

- `current_clinic_id: ContextVar[UUID | None]` lives in `app/utils/context.py`.
- Set by the auth dependency from the JWT claim `clinic_id` before any query runs.
- A `before_execute` listener on the async engine walks compiled `Select`/`Update`/`Delete` statements; for any table whose ORM class inherits `ClinicScopedBase`, it injects the predicate if it isn't already present.
- A `before_insert` listener on `ClinicScopedBase` sets `clinic_id` from the ContextVar if missing and rejects mismatches.
- If `current_clinic_id` is unset when a clinic-scoped query runs, the listener raises `TenantContextMissingError` — fail closed.

Tables that legitimately span clinics (`clinics`, `users`, `clinic_memberships`) use a separate `GlobalBase` and skip the listener via `_skip_tenant_guard = True`.

## Consequences

### Positive
- Tenancy is enforced at a single, testable layer — not 50 query sites.
- Adding a new model is one line (`class Foo(ClinicScopedBase): ...`); the guard is automatic.
- The "attack path" test (`test_select_by_id_in_other_clinic_returns_empty`) verifies the guard live.
- Failing closed on missing context means a bug that "forgets to set the ContextVar" raises loudly rather than silently leaking data.

### Negative
- **Raw `text()` SQL bypasses the guard.** Forbidden in app code (only allowed in migrations).
- ORM-only access path — no escape hatch to write a clever raw query.
- Adds ~1-2ms latency per query for the statement rewriting (acceptable).
- Async support for event listeners has some sharp edges (must use `do_orm_execute` for SELECT visibility).

### Compared to RLS
- RLS is the strongest defense: even a buggy app can't violate the policy. But it complicates connection pooling (`SET LOCAL` per connection / pgbouncer in transaction mode), requires PG-specific policies for every table, and is harder to test in isolation.
- The session-level guard is "good enough" for a solo-built app and far simpler to maintain. If we add a second backend language (Go worker?), the guard wouldn't protect it — at that point we'd add RLS as defense in depth.

### Rejected: convention only
- HIPAA-class controls cannot rely on "every developer remembers." Even the only developer.

## Revisit when

- We add a second backend language or service that talks to the same DB → add Postgres RLS as defense in depth.
- We add raw SQL escape hatches for performance → must wrap them in a `ClinicScopedRawQuery` helper that injects the predicate.
- We onboard a second engineer → re-validate that the convention is teachable.
