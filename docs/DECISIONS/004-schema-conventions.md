# ADR 004 — Schema conventions: TIMESTAMPTZ, naming, encrypted columns

**Status:** Accepted (2026-05-18)
**Author:** Shaurya

## Context

The original BIGC project brief listed several schema details that needed normalization before becoming load-bearing:

- Mixed `Date` vs `DateTime` columns for time-bound values.
- Naive `DateTime` in some places.
- `appointment_date`, `scheduled_date`, `follow_up_date` — instants pretending to be dates.
- No explicit naming convention.

Healthcare timing is timezone-sensitive (appointment slots across time zones, daylight saving transitions, audit timestamps for compliance).

## Decision

Adopt these conventions, enforced by the `migration-skill` and tested by `test_migration.py`:

### 1. All datetime columns are `TIMESTAMPTZ`
SQLAlchemy: `mapped_column(DateTime(timezone=True), ...)`. Naive `DateTime` is forbidden. Postgres stores UTC + zone; the ORM hands the app `datetime.datetime` with `tzinfo` set.

### 2. Naming
- `*_at` for instants (`appointment_at`, `scheduled_at`, `created_at`, `updated_at`, `due_at`, `follow_up_at`).
- `*_date` for pure calendar dates without time or zone (`discharge_date`, `follow_up_deadline`). These stay `sa.Date`.

### 3. Renames from the original brief
- `appointments.appointment_date` → `appointment_at`
- `referrals.scheduled_date` → `scheduled_at`
- `prior_auths.follow_up_date` → `follow_up_at`
- `referral_tasks.due_date` → `due_at`

`patients.dob` and `discharge_summaries.discharge_date` stay `Date` (calendar values).

### 4. Encrypted columns are declared as `sa.String` in migrations
The `EncryptedString` `TypeDecorator` (ADR 003) operates at the ORM layer. Migrations see ciphertext as a normal `VARCHAR`. The migration file gets a `-- encrypted at app layer` comment for human readers.

### 5. Indexing rules
- Every clinic-scoped table has an index on `clinic_id`.
- Composite indexes for known query patterns (`documents(status, classification, urgency)`, `referrals(status, urgency)`, etc.) are explicit, not relied-upon-from-FK.
- `pgvector` columns use ivfflat with cosine ops.

### 6. Downgrades are real
Every `op.create_table` has a matching drop in reverse FK order. Every named enum (`sa.Enum(..., name='...')`) is dropped with `op.execute('DROP TYPE ...')`. Validated by `test_downgrade_to_base_then_upgrade_head_round_trip`.

## Consequences

### Positive
- One consistent rule across 24 tables; no per-column thought-tax.
- Round-trip migration test catches broken downgrades.
- Audit timestamps are unambiguous across timezones.

### Negative
- Migrating an existing repo to this convention requires a one-time rename pass (not relevant for greenfield).
- Encrypted columns being `sa.String` in migrations means `\d patients` in psql shows `dob VARCHAR` not `DATE` — slightly surprising to a reader.

## Revisit when

- We add a column whose semantics genuinely don't fit (`time_of_day` without a date — none planned).
- The `migration-skill` accumulates more conventions; this ADR may need to absorb them.
