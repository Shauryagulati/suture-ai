# ADR 001 — Monorepo with pnpm workspace + FastAPI backend

**Status:** Accepted (2026-05-18)
**Author:** Shaurya

## Context

Suture has two distinct first-class apps (Next.js frontend, FastAPI backend) plus several long-running workers (Celery, voice agent), shared types (eventually), and AI assets (prompts, evals, RAG). Each could live in its own repo, or all could live together.

## Decision

Single monorepo:

- `apps/web` — Next.js 15 (pnpm package `@suture/web`)
- `apps/api` — FastAPI (`uv` project)
- `services/voice-agent`, `services/workers` — separate workers, not Next.js apps
- `packages/shared-types` — TS types generated from FastAPI OpenAPI (Module 1+)
- `ai/`, `seeds/`, `infra/`, `docs/` — shared assets

pnpm workspace for Node packages. `uv` for the Python project. They coexist at the root with a single `Makefile` for orchestration.

## Consequences

### Positive
- One source of truth for cross-cutting concerns (schema, ADRs, SECURITY.md).
- Easier coordination: a schema change + the frontend that consumes it + the eval that validates AI extraction land in one PR.
- Lower context-switching cost for a solo developer.
- Shared CI (single `.github/workflows/ci.yml`).

### Negative
- Bigger clone footprint.
- Tooling has to handle "this repo has both `pnpm-lock.yaml` and `uv.lock`" — usually fine but caused us to write a custom `.pre-commit-config.yaml` with mixed-language hooks.
- If we ever extract a public package, we'll need to break it out.

### Tooling decisions that follow
- `pnpm` (10.x) — strict, fast, disk-efficient.
- `uv` — fast Python dep manager, lockfile-driven, good with async stacks.
- `biome` over ESLint+Prettier — single tool for TS lint+format.
- `ruff` over flake8+isort+black — same logic for Python.

## Alternatives considered

- **Polyrepo (three repos):** rejected — too much overhead for a solo developer; PRs that touch both apps would need cross-repo coordination.
- **Turborepo / Nx:** rejected for now — useful at scale, premature for one frontend + one backend.
- **Poetry over uv:** uv wins on speed and lockfile robustness for async stacks.

## Revisit when

- If we extract `packages/shared-types` to npm.
- If the team grows past 3 engineers.
- If CI runtime exceeds 10 minutes.
