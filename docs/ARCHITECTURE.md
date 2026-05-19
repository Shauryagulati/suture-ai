# Suture — Architecture

> Updated each gate. This document tracks the as-built system, not the aspirational one.

## System diagram (foundation)

```
                            ┌────────────────────────────┐
                            │      Browser (admin)       │
                            └────────────┬───────────────┘
                                         │  https://localhost:3000
                                         ▼
                    ┌────────────────────────────────────────┐
                    │   Next.js 15 (apps/web)                │
                    │   - App Router                          │
                    │   - NextAuth Credentials → FastAPI JWT  │
                    │   - shadcn/ui + Tailwind                │
                    └────────────┬───────────────────────────┘
                                 │ Bearer JWT (HS256)
                                 ▼
        ┌────────────────────────────────────────────────────┐
        │   FastAPI (apps/api)                                │
        │                                                     │
        │   Request middleware sets ContextVars:              │
        │     - current_user_id                               │
        │     - current_clinic_id   ← from JWT claim          │
        │     - current_ip_address                            │
        │                                                     │
        │   ┌─────────────────────────────────────────────┐  │
        │   │ SQLAlchemy ClinicScopedSession              │  │
        │   │   before_execute event listener injects     │  │
        │   │   WHERE clinic_id = :current_clinic_id      │  │
        │   │ after_insert/update/delete listeners write  │  │
        │   │   to audit_logs                             │  │
        │   └─────────────────────────────────────────────┘  │
        └──────────────────────────┬──────────────────────────┘
                                   │ asyncpg
                                   ▼
        ┌────────────────────────────────────────────────────┐
        │   Postgres 16 (pgvector, pgcrypto, uuid-ossp)      │
        │                                                     │
        │   Encrypted columns (Fernet at ORM layer):          │
        │     patients.dob, patients.phone, patients.ssn,     │
        │     insurance_policies.member_id                    │
        └────────────────────────────────────────────────────┘

        ┌────────────────────────┐    ┌──────────────────────┐
        │ Redis (Celery broker)  │    │ Observability stack  │
        │                        │    │  Jaeger              │
        │ (Workers join Module   │    │  Prometheus          │
        │  3a)                   │    │  Grafana             │
        └────────────────────────┘    └──────────────────────┘
```

## Layer ownership

| Layer | Owns | Files |
|---|---|---|
| Browser | Auth UI, inbox, review, dashboards | `apps/web/` |
| API | Data plane, AI orchestration, auth | `apps/api/` |
| Workers | Long-running document pipelines, voice callbacks | `services/workers/`, `services/voice-agent/` (Module 6) |
| Data | Multi-tenant Postgres, embeddings, audit trail | `infra/`, `apps/api/alembic/` |
| AI | Prompts, eval harness, RAG | `ai/` |

## Data flow (target, post-foundation)

```
Inbound fax/PDF arrives
    ↓ upload
Documents (status=uploaded)
    ↓ classify (Claude Sonnet)
Documents (status=classified, classification, urgency)
    ↓ extract (Claude Sonnet, tool use)
DocumentExtractions (per-field, with confidences)
    ↓ human review
Referrals / DischargeSummaries
    ↓ workflow engine (Celery)
ReferralTasks (call patient, verify eligibility, prep auth, schedule)
    ↓ outreach (SMS → email → voice)
Appointments
    ↓ confirmation
Faxes (confirmation-fax-back to discharging hospital)
```

Every step writes to `ai_invocations` (if it called Claude), `audit_logs` (if it touched PHI), and `workflow_runs` (if it's a Celery task).

## Architectural conventions

See `CLAUDE.md` (repo root) for the load-bearing patterns. The most important:

- **Tenant isolation** is enforced at the SQLAlchemy session layer (event listener), not by convention. ADR 002.
- **PHI encryption** is Fernet via `TypeDecorator`, not pgcrypto. ADR 003.
- **All datetimes** are `TIMESTAMPTZ`. ADR 004.
- **Users are global**; clinic access is via the `clinic_memberships` join table. ADR 005.
- **Every Claude API call** logs to `ai_invocations` — model, tokens, latency, cost, no PHI.
