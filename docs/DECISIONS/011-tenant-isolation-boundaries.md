# ADR 011 — Tenant isolation: as-built guard, known boundaries, no-RLS posture

**Status:** Accepted (2026-06-10)
**Author:** Shaurya
**Amends:** ADR 002

## Context

ADR 002 chose a SQLAlchemy session-level guard for tenant isolation and described it as a `before_execute` listener that injects `WHERE clinic_id = ...` into compiled SQL. A post-build security review found that (a) the *as-built* mechanism differs from that description, (b) the guard has one narrow fail-open boundary that the description didn't capture, and (c) the "add RLS later" posture was never recorded as an explicit, accepted risk. This ADR records the reality so the next person doesn't introduce a real leak from a wrong mental model.

## Decision

### As-built mechanism (corrects ADR 002's prose)

The guard is a **`do_orm_execute`** event listener on `Session` (`app/database.py`), not a `before_execute`/compiled-SQL interceptor. For any statement touching a `ClinicScopedBase` subclass it injects:

```python
with_loader_criteria(ClinicScopedBase, lambda cls: cls.clinic_id == current_clinic_id.get(), include_aliases=True)
```

This is materially stronger than a SELECT-string rewrite: it correctly scopes **column-only selects** (`select(Patient.first_name)`), **`session.get(Patient, id)`**, and **aggregate `count(Model.id)`** — all verified by regression tests in `tests/test_tenant_guard_bypass.py`. The codebase also forbids ORM `relationship()` (all FKs are plain UUIDs joined explicitly), which removes lazy/eager relationship-load leak vectors by construction.

### Known boundary (accepted)

`with_loader_criteria` applies its predicate to entities that are *loaded* (their columns/identity are in the result). A bare **`count(*)` over `select_from(Entity)`** loads no entity columns, so the predicate is **not** injected and the count spans clinics — a fail-open. This is **not exploitable today**: app code never uses that form; every count is `count(Model.id)` (verified by grep across the routers). The gap is pinned by an `xfail` test (`test_bare_count_star_should_be_clinic_scoped`) that flips to XPASS if a future change closes it.

**Rule:** clinic-scoped counts MUST use `count(Model.id)`, never `count(*).select_from(Model)`.

### App-layer-only (no Postgres RLS) — accepted risk

Isolation is enforced solely in the application (the `do_orm_execute` guard). There is no Postgres Row-Level Security. Any raw `psql` session, a future Core-based query, or a second service talking to the same DB would see all clinics. This is an accepted v1 trade-off (simplicity, single-backend, solo-maintained) — consistent with ADR 002's "good enough" reasoning — now recorded explicitly rather than left as an unstated assumption.

### NULL-clinic audit rows

`AuditLog` allows a NULL `clinic_id` for system events and bypasses the INSERT guard, but **reads are clinic-scoped** like any other model (the guard's `clinic_id == cid` excludes NULL). NULL-clinic rows are therefore written but not readable via the ORM under a clinic context — safe (fails closed), and a future admin audit-review needs an explicit bypass path. (Previously mis-documented as "the guard treats NULL as visible"; corrected in the model docstring + `test_null_clinic_audit_row_not_visible_under_clinic_context`.)

### PHI in `PriorAuthEvent.details`

Payer `denial_reason` free-text is persisted into `PriorAuthEvent.details` (JSONB). Unlike `audit_logs.details` (IDs/column-names only), this domain-event log may contain patient-identifying text. It is tenant-scoped (`ClinicScopedBase`), so it does not cross clinics, but it is a conscious PHI-in-JSONB sink, recorded here rather than left accidental.

## Consequences

- The mechanism description in CLAUDE.md and the AuditLog docstring now match the code.
- The bare-`count(*)` boundary is documented + test-pinned; the convention (`count(Model.id)`) is stated.
- The no-RLS posture is an explicit decision with a clear "revisit when" trigger.

## Revisit when

- A second backend service/language talks to the same DB, OR app code needs a raw/Core query path → add Postgres RLS (`SET app.current_clinic_id` GUC + per-table policies) as defense in depth. `clinic_id` is already indexed on every scoped table, so RLS is cheap.
- An admin cross-clinic audit-review feature is built → add an explicit, audited guard-bypass read path for NULL-clinic rows.
