# Suture — Project Context for Claude Code

> This file is loaded automatically by every Claude Code session in this repo.
> Read it before you touch code. The rules here are load-bearing.

## Project overview

**Suture** is a multi-tenant AI command center for cardiology practices. It closes the loop from inbound referral / discharge fax → AI extraction → human review → workflow → multi-channel patient outreach → prior-auth packet → confirmation fax-back to the discharging hospital.

Built solo by Shaurya. Local-only in v1. The **only paid service is the Anthropic API**. Everything else (Postgres, Redis, observability, OCR, embeddings, voice STT/TTS) runs locally.

The product targets independent cardiology practices, starting in Western Pennsylvania. The codebase is also a portfolio artifact demonstrating senior-level engineering judgement on a HIPAA-class workload.

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 15 (App Router) + TypeScript strict, pnpm |
| UI | Tailwind CSS + shadcn/ui, TanStack Table, React Hook Form + Zod, react-pdf, TanStack Query, Zustand (only if needed) |
| Auth | NextAuth Credentials → FastAPI JWT (HS256) |
| Backend | FastAPI (Python 3.12) via `uv`, SQLAlchemy 2.0 async, asyncpg |
| Database | Postgres 16 + pgvector + pgcrypto + uuid-ossp |
| Migrations | Alembic |
| Background jobs | Celery + Redis |
| File storage | Local filesystem behind an S3-compatible interface |
| AI — LLM | Claude API: Sonnet for extraction, Opus for harder reasoning, Haiku for evals + voice |
| AI — OCR | Docling (IBM, open source), Tesseract fallback |
| AI — Embeddings | sentence-transformers `all-MiniLM-L6-v2` (local, 384-dim) |
| Voice | LiveKit Agents + Whisper.cpp (STT) + Piper (TTS) + Claude Haiku |
| Observability | structlog, OpenTelemetry → Jaeger, Prometheus + Grafana |

## Architecture patterns (load-bearing — do not deviate without an ADR)

### Multi-tenant isolation
- A SQLAlchemy `before_execute` event listener on the async engine inspects every compiled `SELECT`/`UPDATE`/`DELETE`. For any table whose model inherits `ClinicScopedBase`, it injects `WHERE clinic_id = :current_clinic_id` if not already present.
- `current_clinic_id` lives in a `ContextVar` in `app/utils/context.py`, set by the auth dependency from the JWT.
- `INSERT` is handled by a `before_insert` listener that sets `clinic_id` from the ContextVar if missing and rejects mismatches.
- If `current_clinic_id` is unset when a clinic-scoped query runs, the listener raises `TenantContextMissingError`. **Failing closed is the correct behavior.**
- Tables that legitimately span clinics (`clinics`, `users`, `clinic_memberships`) use a separate `GlobalBase` and skip the listener.

### Audit logging
- SQLAlchemy `after_insert` / `after_update` / `after_delete` event listeners write to `audit_logs` for every PHI-bearing model.
- View actions are emitted from an explicit `track_view()` helper called from GET routes (there is no SQLAlchemy event for SELECT).
- The audit row's `details` JSONB column contains **only IDs and column names changed** — never PHI values.
- PHI-bearing tables (kept in `app/utils/audit.py::AUDITED_MODELS`): `Patient`, `Document`, `DocumentExtraction`, `Referral`, `DischargeSummary`, `Appointment`, `OutreachAttempt`, `Call`, `CallTranscript`, `InsurancePolicy`.

### PHI encryption
- `EncryptedString` is a SQLAlchemy `TypeDecorator` wrapping `cryptography.fernet.Fernet`.
- Applied to: `patients.dob` (stored as `YYYY-MM-DD` ciphertext), `patients.phone`, `patients.ssn`, `insurance_policies.member_id`.
- Key comes from `settings.PHI_ENCRYPTION_KEY` (env). Generate locally with `make gen-phi-key`. **Never commit the key.**
- Encrypted columns are not searchable or indexable on value. Plan queries accordingly.
- Production path for key rotation is documented in `docs/SECURITY.md` (KMS).

### Authentication
- JWT carries: `sub` (user_id), `clinic_id` (active membership), `role`, `exp`, `iat`. Signed HS256 with `JWT_SECRET` from env.
- Users are global. Email is **globally unique**.
- `clinic_memberships(user_id, clinic_id, role, is_default)` joins users to clinics. At most one default per user.
- Clinic switching is a Module-1+ endpoint. Foundation only honors the user's default membership at login.

### ContextVars (`app/utils/context.py`)
- `current_clinic_id: ContextVar[UUID | None]`
- `current_user_id: ContextVar[UUID | None]`
- `current_ip_address: ContextVar[str | None]`

Set by the auth dependency (`get_current_user`) and request middleware. Read by the tenant guard and the audit listener.

### Time columns
- Every datetime column is `TIMESTAMPTZ`. No naive `DateTime` anywhere.
- Naming: `*_at` for instants (`appointment_at`, `scheduled_at`, `due_at`).
- Pure calendar dates (`dob`, `discharge_date`, `follow_up_deadline`) stay `Date`.

## Anti-patterns — DO NOT do these

- ❌ **Raw `text()` SQL in app code outside Alembic migrations.** Bypasses the tenant guard.
- ❌ **PHI in application logs or in `audit_logs.details`.** IDs and column names only.
- ❌ **`pgcrypto` column encryption.** Rejected in ADR 003.
- ❌ **Per-query manual `WHERE clinic_id = ...` filtering.** That's a regression — the session-level guard is the source of truth.
- ❌ **Commits without tests for new code paths.**
- ❌ **Claude API calls without inserting a row into `ai_invocations`.** Every call must be logged with model, tokens, latency, cost.
- ❌ **Naive `DateTime` columns.** `TIMESTAMPTZ` everywhere.
- ❌ **Frontend code that touches the FastAPI bearer token directly outside the NextAuth session callback path** (or the route-handler proxy if the Gate B2 fallback was engaged).
- ❌ **Skipping commitlint** via `--no-verify`. If a commit fails, fix the message.

## Build standards

- Conventional commits (enforced via commitlint + husky `commit-msg` hook)
- `mypy` strict on `apps/api/app`
- `tsc` strict on `apps/web`
- `ruff` (lint + format) clean
- `biome` (lint + format) clean
- All 25 foundation tests passing in CI before any feature branch merges to `main`
- Once Module 2 lands: every prompt-file change re-runs the eval harness; merges blocked if accuracy regresses

## Repo structure

```
suture/
├── apps/
│   ├── web/                     # Next.js 15 frontend (auth UI, inbox, review, dashboards)
│   └── api/                     # FastAPI backend (data plane + AI orchestration)
├── packages/
│   └── shared-types/            # TS types generated from FastAPI OpenAPI (Module 1+)
├── services/
│   ├── voice-agent/             # LiveKit Agents worker (Ember) — Module 6
│   └── workers/                 # Celery workers — Module 3a
├── ai/
│   ├── prompts/                 # Versioned prompt files (per-module subdirs)
│   ├── evals/                   # Eval harness, test sets, run results
│   ├── rag/                     # Payer-rules KB + ingestion scripts
│   └── skills/                  # Reusable Claude Code skills (migration, audit, eval)
├── seeds/
│   ├── scripts/                 # Data generation scripts
│   └── documents/               # Synthetic referral/discharge PDFs (gitignored)
├── infra/
│   ├── docker-compose.yml       # Local stack: Postgres + Redis
│   ├── docker-compose.obs.yml   # Observability: Jaeger + Prometheus + Grafana
│   └── init.sql                 # Postgres extensions
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SECURITY.md
│   ├── EVAL.md
│   ├── DEMO.md
│   └── DECISIONS/               # ADRs
├── .claude/
│   ├── settings.json            # Project Claude Code config
│   └── commands/                # Slash commands
└── .github/workflows/           # CI: lint + typecheck + test on PR
```

## Common commands (Makefile cheatsheet)

| Command | What it does |
|---|---|
| `make infra-up` | Start Postgres + Redis (Docker) |
| `make infra-down` | Stop Postgres + Redis |
| `make obs-up` | Start Jaeger + Prometheus + Grafana (Docker) |
| `make obs-down` | Stop observability stack |
| `make migrate` | `alembic upgrade head` |
| `make migrate-down` | `alembic downgrade base` |
| `make seed` | Populate dev data (2 clinics, 6 users, 20 patients, 10 providers) |
| `make api` | Run FastAPI with uvicorn auto-reload on :8000 |
| `make web` | Run Next.js dev server on :3000 |
| `make dev` | Run api + web in parallel |
| `make test` | Run pytest + (any) vitest |
| `make lint` | `ruff check` + `biome lint` |
| `make typecheck` | `mypy` + `tsc --noEmit` |
| `make gen-phi-key` | Generate a Fernet key into `apps/api/.env` (PHI_ENCRYPTION_KEY) |
| `make gen-jwt-keys` | Generate a JWT secret into `apps/api/.env` (JWT_SECRET) |
| `make verify-gate-{0,a,b1,b2,c}` | Run the verification suite for the given foundation gate |

## How we work (Plan-Gate-Verify-Commit)

Foundation and every subsequent feature are built in **gates**:

1. Plan the gate (what files, what tests, what verification).
2. Build the gate.
3. Run `make verify-gate-X`. If FAIL → STOP and surface the failure. Do not auto-fix past a failed gate.
4. If PASS → commit with the planned conventional commit message. Move to the next gate.

HIPAA-class test failures (tenant attack-path, audit-PHI-leak) are hard stops, not lint issues.
