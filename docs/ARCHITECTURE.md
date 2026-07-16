# Suture — Architecture

> Tracks the as-built system, not the aspirational one.

## System diagram

```
                            ┌────────────────────────────┐
                            │      Browser (clinic staff)│
                            └────────────┬───────────────┘
                                         │  http://localhost:3000
                                         ▼
                    ┌────────────────────────────────────────┐
                    │   Next.js 15 (apps/web)                 │
                    │   - App Router, shadcn/ui + Tailwind    │
                    │   - NextAuth Credentials → FastAPI JWT  │
                    │   - inbox · review · tasks · prior-auth │
                    │     · discharges · voice · analytics    │
                    └────────────┬───────────────────────────┘
                                 │ Bearer JWT (HS256)
                                 ▼
        ┌────────────────────────────────────────────────────┐
        │   FastAPI (apps/api)                                │
        │   Middleware sets ContextVars (user/clinic/ip)      │
        │                                                     │
        │   ┌─────────────────────────────────────────────┐  │
        │   │ ClinicScopedSession                         │  │
        │   │   do_orm_execute → with_loader_criteria(cid)│  │
        │   │   after_insert/update/delete → audit_logs   │  │
        │   └─────────────────────────────────────────────┘  │
        │                                                     │
        │   Services: classification · extraction · workflow │
        │   state machine · outreach orchestrator · prior-   │
        │   auth RAG · analytics · discharge confirmation    │
        └───┬───────────────┬───────────────┬────────────────┘
            │ asyncpg        │ provider iface │ Celery (Redis broker)
            ▼                ▼                ▼
 ┌────────────────────┐ ┌──────────────┐ ┌────────────────────────┐
 │ Postgres 16        │ │ LLM / embed  │ │ services/workers       │
 │  pgvector          │ │ get_*_       │ │  overdue / SLA scan    │
 │  pgcrypto, uuid    │ │ provider()   │ │  outreach beat tasks   │
 │                    │ │              │ └────────────────────────┘
 │ Fernet-encrypted:  │ │ default:     │ ┌────────────────────────┐
 │  patients.dob,     │ │  Ollama      │ │ services/voice-agent    │
 │  phone, ssn;       │ │  medgemma1.5 │ │  (Ember) LiveKit room:  │
 │  insurance.        │ │  bge-m3      │ │  Whisper STT → LLM →    │
 │  member_id         │ │ BYOK: Claude │ │  Piper TTS, live        │
 │                    │ │  / OpenAI    │ │  transcript bus         │
 └────────────────────┘ └──────────────┘ └────────────────────────┘

        ┌────────────────────────────────────────────────────┐
        │ Observability: structlog · OpenTelemetry → Jaeger  │
        │ · Prometheus + Grafana                              │
        └────────────────────────────────────────────────────┘
```

## Layer ownership

| Layer | Owns | Files |
|---|---|---|
| Browser | Auth UI, inbox, review, tasks, prior-auth, discharges, voice, analytics | `apps/web/` |
| API | Data plane, AI orchestration, auth, workflow, RAG | `apps/api/` |
| Workers | SLA/overdue scans, outreach beat tasks; voice agent | `services/workers/`, `services/voice-agent/` |
| Data | Multi-tenant Postgres, embeddings, audit trail | `infra/`, `apps/api/alembic/` |
| AI | Prompts, eval harness, RAG ingestion | `ai/` |

## Data flow (as built)

```
Inbound fax/PDF arrives
    ↓ upload + OCR (Docling → pypdf fallback)
Documents (status=uploaded → classified)
    ↓ classify, then extract via get_llm_provider()  [FastAPI BackgroundTask, ADR 008]
DocumentExtractions (per-field, deterministic confidences — ADR 009)
    ↓ human review + approve
Referrals / DischargeSummaries  (+ Patient, Provider, InsurancePolicy)
    ↓ workflow state machine (apply_*_transition)
ReferralTasks (SLA-tracked) + OutreachAttempts (cadence)
    ↓ outreach: SMS → email → voice  [stub providers in v1, ADR 010]
Appointments (tokenized patient self-scheduling)
    ↓ discharge confirmation
Faxes (confirmation-fax-back to discharging hospital)  [stub provider in v1]

Prior auth (parallel): payer-rules RAG (hybrid structured + pgvector) →
  auth-required check → packet generation → appeals.
Analytics: leakage · payer friction · referral quality · ROI.
Voice (Ember): LiveKit room, Whisper STT → LLM → Piper TTS, transcript bus.
```

Every step writes to `ai_invocations` (if it called an LLM), `audit_logs` (if it
touched PHI), and `workflow_runs` (if it ran as a Celery task).

## What's stubbed in v1 (local-only)

External delivery — SMS, email, voice, and fax — runs through **stub providers** that
record an auditable attempt but send nothing off-machine (ADR 010). The voice agent uses a
browser test-caller, not PSTN. Swapping in real vendors is a provider-interface change, not
a rearchitecture.

## Architectural conventions

See `CLAUDE.md` (repo root) for the load-bearing patterns:

- **Tenant isolation** at the SQLAlchemy session layer (event listener), fail-closed. ADR 002.
- **PHI encryption** is Fernet via `TypeDecorator`, not pgcrypto. ADR 003.
- **All datetimes** are `TIMESTAMPTZ`. ADR 004.
- **Users are global**; clinic access via `clinic_memberships`. ADR 005.
- **LLM/embeddings** go through `get_llm_provider()` / `get_embedding_provider()`; local
  Ollama default, BYOK Claude/OpenAI. ADR 007.
- **Every LLM call** logs to `ai_invocations` — model, tokens, latency, cost, no PHI.
