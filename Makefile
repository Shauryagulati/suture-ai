.PHONY: help infra-up infra-down obs-up obs-down voice-up voice-down voice-agent gen-livekit-keys migrate migrate-down seed seed-synthetic verify-synthetic ingest-payer-rules api web dev worker beat test lint typecheck gen-phi-key gen-jwt-keys precommit-install verify-gate-0 verify-gate-a verify-gate-b1 verify-gate-b2 verify-gate-c verify-gate-module2 verify-gate-outreach verify-gate-voice eval-extraction eval-voice

# Use bash for recipe lines (consistent shell semantics)
SHELL := /bin/bash

# Default target: print help
help:
	@echo "Suture — available targets:"
	@echo ""
	@echo "  Infra"
	@echo "    infra-up        Start Postgres + Redis"
	@echo "    infra-down      Stop Postgres + Redis"
	@echo "    obs-up          Start Jaeger + Prometheus + Grafana"
	@echo "    obs-down        Stop observability stack"
	@echo "    voice-up        Start LiveKit server (Module 6 / Ember)"
	@echo "    voice-down      Stop LiveKit server"
	@echo "    voice-agent     Run Ember worker (foreground, auto-reload)"
	@echo ""
	@echo "  Database"
	@echo "    migrate         alembic upgrade head"
	@echo "    migrate-down    alembic downgrade base"
	@echo "    seed            Populate dev data"
	@echo ""
	@echo "  Synthetic eval corpus"
	@echo "    seed-synthetic       Generate 30 referrals + 20 discharges + ground truth"
	@echo "    verify-synthetic     Run structural verification on committed corpus"
	@echo "    ingest-payer-rules   Embed + load payer rules (5 payers × 5 CPTs)"
	@echo ""
	@echo "  Dev servers"
	@echo "    api             Run FastAPI (uvicorn auto-reload) on :8000"
	@echo "    web             Run Next.js dev server on :3000"
	@echo "    dev             Run api + web in parallel"
	@echo "    worker          Run Celery worker"
	@echo "    beat            Run Celery beat scheduler"
	@echo ""
	@echo "  Quality"
	@echo "    test            Run pytest"
	@echo "    lint            ruff + biome"
	@echo "    typecheck       mypy + tsc"
	@echo ""
	@echo "  Secrets (local dev only — never commit)"
	@echo "    gen-phi-key       Append a Fernet PHI_ENCRYPTION_KEY to apps/api/.env"
	@echo "    gen-jwt-keys      Append a JWT_SECRET to apps/api/.env"
	@echo "    gen-livekit-keys  Append LIVEKIT_API_KEY/SECRET to apps/api/.env"
	@echo ""
	@echo "  Tooling"
	@echo "    precommit-install   Install pre-commit hooks (opt-in)"
	@echo ""
	@echo "  Gate verification"
	@echo "    verify-gate-0   Claude Code context files present + valid"
	@echo "    verify-gate-a   Scaffold + infra + CI smoke"
	@echo "    verify-gate-b1  Tenant guard + audit + encryption tests"
	@echo "    verify-gate-b2  Auth E2E"
	@echo "    verify-gate-c   Full schema + seed + observability"
	@echo "    verify-gate-outreach  Patient outreach module (cadence, sends, scheduling, backfill, tenant isolation)"
	@echo "    verify-gate-voice     Module 6 (Ember voice agent) — migration + tests + types + lint + livekit running"
	@echo ""
	@echo "  Eval"
	@echo "    eval-extraction Run extraction eval harness"
	@echo "    eval-voice      Run slow voice integration tests (Whisper + Piper roundtrips)"

# ─── Infra ─────────────────────────────────────────────────────────────

infra-up:
	docker compose -f infra/docker-compose.yml up -d
	@echo "Waiting for Postgres to accept connections..."
	@for i in $$(seq 1 30); do \
		if pg_isready -h localhost -p 5432 -U suture >/dev/null 2>&1; then \
			echo "Postgres ready."; exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "Postgres did not become ready in 30s"; exit 1

infra-down:
	docker compose -f infra/docker-compose.yml down

obs-up:
	docker compose -f infra/docker-compose.obs.yml up -d

obs-down:
	docker compose -f infra/docker-compose.obs.yml down

# ─── Voice (Module 6 / Ember) ──────────────────────────────────────────

voice-up:
	docker compose -f infra/docker-compose.yml up -d livekit
	@echo "Waiting for LiveKit to accept connections..."
	@for i in $$(seq 1 30); do \
		if curl -fsS http://localhost:7880 >/dev/null 2>&1; then \
			echo "LiveKit ready."; exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "LiveKit did not become ready in 30s"; exit 1

voice-down:
	docker compose -f infra/docker-compose.yml stop livekit

voice-agent:
	cd services/voice-agent && uv run python -m ember dev

# ─── Database ──────────────────────────────────────────────────────────

migrate:
	cd apps/api && uv run alembic upgrade head

migrate-down:
	cd apps/api && uv run alembic downgrade base

seed:
	PYTHONPATH=apps/api uv --project apps/api run python -m seeds.scripts.seed_dev

# Push synthetic PDFs through the real API pipeline (upload -> classify ->
# extract -> approve -> workflow) so the inbox, review queue, tasks, outreach,
# and analytics are populated. Requires the API + Ollama running.
seed-documents:
	PYTHONPATH=apps/api uv --project apps/api run python -m seeds.scripts.seed_documents

# Run structured-extraction eval against the synthetic corpus.
eval-extraction:
	PYTHONPATH=apps/api:. uv --project apps/api run python -m ai.evals.eval_extraction --limit 50

# Slow voice integration tests — actual Whisper transcription + Piper
# synthesis. First run downloads ~210MB of model weights into
# settings.voice_model_cache_dir.
eval-voice:
	cd apps/api && uv run pytest -v -m slow tests/test_whisper_integration.py tests/test_piper_integration.py

# Embed payer-rules markdown + load structured JSON into payer_rules.
# Idempotent — clears each payer's rows first, then re-inserts 5 per payer.
# Requires Ollama running locally with `bge-m3` pulled (or a BYOK provider
# configured via EMBEDDING_PROVIDER / OPENAI_API_KEY).
ingest-payer-rules:
	cd apps/api && uv run python -m scripts.ingest_payer_rules

# Generate the synthetic eval corpus: 30 referral PDFs, 20 discharge PDFs,
# 20 patient JSON, 10 referring-practice JSON, 5 payer rule sets, plus
# parallel ground-truth JSON for every PDF. Idempotent — re-runs read
# committed LLM fixtures and produce byte-identical output.
seed-synthetic:
	uv --project apps/api run python -m seeds.scripts.generate_all --seed 42

# Run the 7-check structural verification on the committed synthetic corpus.
verify-synthetic:
	@bash scripts/verify_synthetic.sh

# ─── Dev servers ───────────────────────────────────────────────────────

api:
	cd apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web:
	pnpm --filter @suture/web dev

dev:
	@echo "Starting api + web in parallel. Ctrl-C to stop both."
	@(trap 'kill 0' INT; \
	  $(MAKE) api & \
	  $(MAKE) web & \
	  wait)

worker:
	cd apps/api && PYTHONPATH=../.. uv run celery -A services.workers.app worker --loglevel=info

beat:
	cd apps/api && PYTHONPATH=../.. uv run celery -A services.workers.app beat --loglevel=info

# ─── Quality ───────────────────────────────────────────────────────────

test:
	cd apps/api && uv run pytest -v

lint:
	cd apps/api && uv run ruff check app tests
	pnpm --filter @suture/web exec biome check .

typecheck:
	cd apps/api && uv run mypy app
	pnpm --filter @suture/web exec tsc --noEmit

# ─── Secrets ───────────────────────────────────────────────────────────

gen-phi-key:
	@if ! grep -q '^PHI_ENCRYPTION_KEY=' apps/api/.env 2>/dev/null; then \
		key=$$(uv --project apps/api run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'); \
		echo "PHI_ENCRYPTION_KEY=$$key" >> apps/api/.env; \
		echo "Generated PHI_ENCRYPTION_KEY into apps/api/.env"; \
	else \
		echo "PHI_ENCRYPTION_KEY already set in apps/api/.env (skipping)"; \
	fi

gen-jwt-keys:
	@if ! grep -q '^JWT_SECRET=' apps/api/.env 2>/dev/null; then \
		secret=$$(openssl rand -hex 32); \
		echo "JWT_SECRET=$$secret" >> apps/api/.env; \
		echo "Generated JWT_SECRET into apps/api/.env"; \
	else \
		echo "JWT_SECRET already set in apps/api/.env (skipping)"; \
	fi

# LiveKit dev keys. The yaml in infra/livekit.yaml already declares
# devkey/devsecret — this target writes the matching pair into the API
# .env so token mint works without manual edits. Rotate before any
# non-local use.
gen-livekit-keys:
	@if ! grep -q '^LIVEKIT_API_KEY=' apps/api/.env 2>/dev/null; then \
		echo "LIVEKIT_API_KEY=devkey" >> apps/api/.env; \
		echo "LIVEKIT_API_SECRET=devsecret" >> apps/api/.env; \
		echo "LIVEKIT_URL=ws://localhost:7880" >> apps/api/.env; \
		echo "Wrote LiveKit dev keys to apps/api/.env"; \
	else \
		echo "LIVEKIT_API_KEY already set in apps/api/.env (skipping)"; \
	fi

# ─── Tooling ───────────────────────────────────────────────────────────

precommit-install:
	pip install pre-commit && pre-commit install

# ─── Gate verification ─────────────────────────────────────────────────

verify-gate-0:
	@bash scripts/verify_gate_0.sh

verify-gate-a:
	@bash scripts/verify_gate_a.sh

verify-gate-b1:
	cd apps/api && uv run pytest -v tests/test_logging_phi_safe.py tests/test_phi_encryption.py tests/test_tenant_isolation.py tests/test_audit_log.py

verify-gate-b2:
	cd apps/api && uv run pytest -v tests/test_auth.py tests/test_auth_tenant_binding.py

verify-gate-c:
	@bash scripts/verify_gate_c.sh

# Module 2 — extraction pipeline + review + eval harness.
verify-gate-module2:
	@echo "→ alembic upgrade head"
	cd apps/api && uv run alembic upgrade head
	@echo "\n→ pytest"
	cd apps/api && uv run pytest -v
	@echo "\n→ mypy apps/api"
	cd apps/api && uv run mypy app
	@echo "\n→ ruff apps/api"
	cd apps/api && uv run ruff check app tests
	@echo "\n→ tsc apps/web"
	cd apps/web && pnpm typecheck
	@echo "\n→ biome apps/web"
	cd apps/web && pnpm lint
	@echo "\n→ eval-extraction smoke (--limit 5)"
	PYTHONPATH=apps/api:. uv --project apps/api run python -m ai.evals.eval_extraction --limit 5
	@echo "\nModule 2 gate: PASS"

verify-gate-outreach:
	cd apps/api && uv run pytest -v \
	    tests/test_outreach_cadence.py \
	    tests/test_outreach_provider_stub.py \
	    tests/test_outreach_templates.py \
	    tests/test_outreach_sms.py \
	    tests/test_outreach_email.py \
	    tests/test_outreach_voice.py \
	    tests/test_outreach_sequence.py \
	    tests/test_outreach_worker.py \
	    tests/test_state_machine_outreach_hooks.py \
	    tests/test_outreach_endpoints.py \
	    tests/test_outreach_patient_history.py \
	    tests/test_scheduling_service.py \
	    tests/test_scheduling_token.py \
	    tests/test_scheduling_link.py \
	    tests/test_waitlist_backfill.py \
	    tests/test_timeline_outreach.py \
	    tests/test_outreach_tenant_isolation.py

# Module 6 — Ember voice agent. Runs the full test suite (default
# `pytest` skips -m slow), the migration head, mypy + ruff for both the
# API and the voice-agent worker package, frontend tsc + biome, and a
# liveness check on the LiveKit container.
verify-gate-voice:
	@echo "→ alembic upgrade head"
	cd apps/api && uv run alembic upgrade head
	@echo "\n→ pytest (api)"
	cd apps/api && uv run pytest
	@echo "\n→ mypy apps/api"
	cd apps/api && uv run mypy app
	@echo "\n→ ruff apps/api"
	cd apps/api && uv run ruff check app tests
	@echo "\n→ mypy services/voice-agent"
	cd services/voice-agent && uv run mypy ember
	@echo "\n→ ruff services/voice-agent"
	cd services/voice-agent && uv run ruff check ember
	@echo "\n→ tsc apps/web"
	cd apps/web && pnpm typecheck
	@echo "\n→ biome apps/web"
	cd apps/web && pnpm lint
	@echo "\n→ livekit container running"
	@docker ps --filter name=suture-livekit --format '{{.Status}}' | grep -qi "up" \
	    || (echo "livekit container is not running — \`make voice-up\`" && exit 1)
	@echo "\nVoice gate: PASS"
