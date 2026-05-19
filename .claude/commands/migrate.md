---
description: Create a new Alembic migration following Suture conventions (TIMESTAMPTZ, ClinicScopedBase, encrypted columns)
---

# /migrate — New Alembic migration

Create a new Alembic revision that follows the conventions documented in `ai/skills/migration-skill/SKILL.md`.

## Conventions to enforce in every migration

1. **All datetime columns are `TIMESTAMPTZ`.** Use `sa.DateTime(timezone=True)`. Never plain `sa.DateTime()`.
2. **Naming:** `*_at` for instants; `*_date` for `sa.Date` calendar values.
3. **Every clinic-scoped table has `clinic_id: UUID NOT NULL` with an FK to `clinics(id)` and an index.**
4. **`created_at TIMESTAMPTZ` with `server_default=sa.func.now()`.**
5. **`updated_at TIMESTAMPTZ` with `onupdate=sa.func.now()`.**
6. **Encrypted columns** (DOB, phone, SSN, member_id) are declared as `sa.String` in the migration — the `EncryptedString` TypeDecorator only applies at the ORM layer. Add a comment `-- encrypted at app layer`.
7. **Downgrades are real.** Every `op.create_table` has a matching `op.drop_table` in `downgrade()`. Every enum created in upgrade is dropped in downgrade. Drop in **reverse FK dependency order**.
8. **Enums** created via `sa.Enum(..., name='snake_case_status')`. Drop with `op.execute('DROP TYPE snake_case_status')` in downgrade.
9. **Indexes named `ix_<table>_<columns>`.**

## How to invoke

1. `cd apps/api && uv run alembic revision -m "short_description"`
2. Edit the generated file in `apps/api/alembic/versions/`.
3. Run `make migrate` to apply; `make migrate-down && make migrate` to verify round-trip.
4. If adding a PHI-bearing model, register it with the audit listener (see `audit-logging-skill`).
