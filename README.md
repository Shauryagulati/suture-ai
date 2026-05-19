# Suture

**AI command center for cardiology practices.** Closes the loop from inbound referral/discharge fax → AI extraction → human review → workflow → multi-channel patient outreach → prior-auth packet → confirmation fax-back to the discharging hospital. Built for independent cardiology practices in Western Pennsylvania.

> ⚠️ Pre-alpha. Local development only.

## Quickstart

```bash
# 1. Install toolchain (one-time)
#    - Node 22+ (see .nvmrc), pnpm 10+
#    - Python 3.12 (see .python-version), uv 0.11+
#    - Docker Desktop

# 2. Install dependencies
pnpm install                 # root + workspace
cd apps/api && uv sync       # backend deps
cd ../web && pnpm install    # frontend deps

# 3. Generate local secrets (one-time)
make gen-phi-key             # PHI_ENCRYPTION_KEY → apps/api/.env
make gen-jwt-keys            # JWT_SECRET → apps/api/.env

# 4. Start infra
make infra-up                # Postgres + Redis

# 5. Run migrations + seed (after Gate C ships)
make migrate
make seed

# 6. Run the apps
make dev                     # api on :8000, web on :3000
```

## Tech stack

- **Frontend** — Next.js 15 (App Router) + TypeScript strict, Tailwind, shadcn/ui
- **Backend** — FastAPI (Python 3.12), SQLAlchemy 2.0 async, asyncpg
- **Database** — Postgres 16 + pgvector + pgcrypto
- **Queue** — Celery + Redis
- **AI** — Claude API (Sonnet/Opus/Haiku), Docling OCR, sentence-transformers, pgvector RAG
- **Voice (Module 6)** — LiveKit Agents + Whisper.cpp + Piper + Claude Haiku
- **Observability** — structlog, OpenTelemetry → Jaeger, Prometheus + Grafana

## Project state

Foundation (Phase 1) is built in five gates:

| Gate | Status | Description |
|---|---|---|
| 0 | ✅ | Claude Code project context |
| A | 🔄 | Scaffold + infra + CI |
| B1 | ⏳ | Tenant guard + audit + encryption + core models |
| B2 | ⏳ | Auth flow (NextAuth + FastAPI JWT) |
| C | ⏳ | Full schema + seeds + observability |

After foundation: modules 1–7 ship as separate branches per the build plan.

## Documentation

- [`CLAUDE.md`](./CLAUDE.md) — architectural rules, anti-patterns (loaded by every Claude Code session)
- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)
- [`docs/SECURITY.md`](./docs/SECURITY.md)
- [`docs/EVAL.md`](./docs/EVAL.md)
- [`docs/DECISIONS/`](./docs/DECISIONS) — ADRs

## License

UNLICENSED — proprietary work-in-progress.
