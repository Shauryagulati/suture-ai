# Suture — Frontend (apps/web)

> Frontend-specific patterns will be filled in when **Module 1: Document Inbox** lands.
> For project-wide rules (auth, tenant model, anti-patterns), see the repo root `CLAUDE.md`.

## Gate 0 stub

This file is intentionally minimal. The frontend scaffold (Next.js 15 + Tailwind + shadcn) lands in Gate A. Real frontend patterns (data fetching with TanStack Query, route protection, PDF viewer wiring, form patterns, design tokens) are added when the first business-logic page is built.

## What you can rely on from day 1

- **Strict TypeScript** — no `any` without an explanatory comment.
- **App Router** — all routes under `app/`.
- **NextAuth Credentials provider** proxying to FastAPI `/api/auth/login`. Bearer token lives in the NextAuth session (or in a route-handler proxy if the Gate B2 fallback was engaged — check ADR 006).
- **Biome** for lint + format. No Prettier.
- **No direct fetches to the FastAPI bearer token outside the NextAuth session callback path** (see root `CLAUDE.md` anti-patterns).

When Module 1 lands, this file gets sections on: data fetching conventions, route protection, error/empty/loading state patterns, the design system, and PDF viewer integration.
