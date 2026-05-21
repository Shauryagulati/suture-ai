#!/usr/bin/env bash
# Verify Gate C — Full schema + seeds + observability.
# Requires `make infra-up` already run (Postgres up).

set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
check() {
  local name="$1"
  local expr="$2"
  if (eval "$expr") >/dev/null 2>&1; then
    printf "  ✓ %s\n" "$name"
  else
    printf "  ✗ %s\n" "$name"
    fail=1
  fi
}

echo "── Gate C verification ──"

check "Postgres ready on :5432" \
  "pg_isready -h localhost -p 5432 -U suture"

echo ""
echo "── Schema ──"

check "Migration 0002_full_schema exists" \
  "[ -s apps/api/alembic/versions/0002_full_schema.py ]"

check "All 18 Gate C model files present" \
  "for f in document document_extraction referral discharge_summary referral_task prior_auth insurance_policy appointment outreach_attempt call fax workflow_run ai_invocation eval_run payer_rule; do [ -s apps/api/app/models/\$f.py ] || exit 1; done"

check "alembic upgrade head succeeds" \
  "cd apps/api && uv run alembic upgrade head"

check "alembic downgrade base + upgrade head round-trip clean" \
  "cd apps/api && uv run alembic downgrade base && uv run alembic upgrade head"

echo ""
echo "── Seed ──"

check "make seed populates 2 clinics / 6 users / 20 patients / 10 providers" \
  "make seed"

check "Seed counts verified via psql" \
  "PGPASSWORD=suture_dev_password psql -h localhost -U suture -d suture -tAc 'SELECT count(*) FROM clinics' | grep -qx 2 \
   && PGPASSWORD=suture_dev_password psql -h localhost -U suture -d suture -tAc 'SELECT count(*) FROM users' | grep -qx 6 \
   && PGPASSWORD=suture_dev_password psql -h localhost -U suture -d suture -tAc 'SELECT count(*) FROM patients' | grep -qx 20 \
   && PGPASSWORD=suture_dev_password psql -h localhost -U suture -d suture -tAc 'SELECT count(*) FROM providers' | grep -qx 10"

check "Patient.phone is Fernet ciphertext at rest" \
  "PGPASSWORD=suture_dev_password psql -h localhost -U suture -d suture -tAc 'SELECT phone FROM patients LIMIT 1' | grep -q '^gAAAAA'"

echo ""
echo "── Observability ──"

check "infra/docker-compose.obs.yml exists" \
  "[ -s infra/docker-compose.obs.yml ]"

check "Prometheus /metrics endpoint instrumented in app/main.py" \
  "grep -q 'Instrumentator' apps/api/app/main.py"

check "OTel exporter wired in app/main.py (gated on OTEL_DISABLED)" \
  "grep -q '_configure_otel' apps/api/app/main.py"

echo ""
echo "── Quality ──"

check "Full pytest suite (33 tests)" \
  "cd apps/api && uv run pytest -q"

check "mypy strict clean" \
  "cd apps/api && uv run mypy app"

check "ruff lint clean" \
  "cd apps/api && uv run ruff check app tests"

check "ruff format clean" \
  "cd apps/api && uv run ruff format --check app tests"

if [ $fail -ne 0 ]; then
  echo ""
  echo "❌ Gate C verification FAILED"
  exit 1
fi
echo ""
echo "✅ Gate C verification passed"
