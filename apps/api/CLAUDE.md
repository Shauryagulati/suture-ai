# Suture — Backend (apps/api)

> Backend patterns expanded in **Gate B1** (when the tenant guard, audit listener, and core models land).
> For project-wide rules, see the repo root `CLAUDE.md`.

## Gate 0 stub

Filled in Gate B1 with the operational patterns below:

- **Adding a new PHI-bearing model** — inherit from `ClinicScopedBase`, register with the audit listener registry (`app/utils/audit.py::AUDITED_MODELS`), declare encrypted columns via `EncryptedString` from `app/utils/encryption.py`.
- **Adding a new router** — create `app/routers/<name>.py`, register in `app/main.py`, depend on `get_db` and `get_current_user`. GET endpoints that return PHI must call `track_view()` to emit an audit log.
- **Dependency composition** — `get_current_user` parses the JWT and sets `current_clinic_id` and `current_user_id` ContextVars. `get_db` yields a session against the engine with the tenant-guard event listener attached. Combine them: `Depends(get_current_user), Depends(get_db)` — order matters because ContextVars must be set before the session runs queries.
- **Writing migrations** — use the `migration-skill` (see `ai/skills/migration-skill/SKILL.md`).
- **Naming** — `*_at` for `TIMESTAMPTZ`, `*_date` for `Date`.

## What you can rely on from day 1

- **Python 3.12**, `uv` for dependency management.
- **mypy strict** — no untyped functions, no untyped `Any` returns.
- **ruff** for lint + format.
- **All datetimes are `TIMESTAMPTZ`** — `from sqlalchemy import DateTime; mapped_column(DateTime(timezone=True), ...)`. Naive `DateTime` is forbidden.
- **Every database query goes through `ClinicScopedSession`.** No raw `text()` in app code (only in migrations).
- **Every Claude API call writes a row to `ai_invocations`.** This is non-negotiable from Module 2 onward.

This file expands when Gate B1 ships.
