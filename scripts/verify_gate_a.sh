#!/usr/bin/env bash
# Verify Gate A — Scaffold + Infra + CI smoke.
# Assumes `make infra-up` has been run.

set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
check() {
  local name="$1"
  local expr="$2"
  # Subshell isolation: a `cd` inside expr doesn't leak to subsequent checks.
  if (eval "$expr") >/dev/null 2>&1; then
    printf "  ✓ %s\n" "$name"
  else
    printf "  ✗ %s\n" "$name"
    fail=1
  fi
}

echo "── Gate A verification ──"

check "Root config files present" \
  "[ -s Makefile ] && [ -s pnpm-workspace.yaml ] && [ -s package.json ] && [ -s commitlint.config.js ]"

check "infra/docker-compose.yml + init.sql" \
  "[ -s infra/docker-compose.yml ] && [ -s infra/init.sql ]"

check "infra/docker-compose.obs.yml" \
  "[ -s infra/docker-compose.obs.yml ]"

check ".github/workflows/ci.yml" \
  "[ -s .github/workflows/ci.yml ]"

check "apps/api/pyproject.toml + alembic.ini" \
  "[ -s apps/api/pyproject.toml ] && [ -s apps/api/alembic.ini ]"

check "apps/api app skeleton" \
  "[ -s apps/api/app/main.py ] && [ -s apps/api/app/config.py ] && [ -s apps/api/app/utils/logging.py ] && [ -s apps/api/app/routers/health.py ]"

check "apps/api tests" \
  "[ -s apps/api/tests/conftest.py ] && [ -s apps/api/tests/test_health.py ]"

check "apps/web package.json + tsconfig + next.config" \
  "[ -s apps/web/package.json ] && [ -s apps/web/tsconfig.json ] && [ -s apps/web/next.config.ts ]"

check "apps/web pages (root + 6 stubs)" \
  "[ -s apps/web/app/page.tsx ] && [ -s apps/web/app/layout.tsx ] && [ -s apps/web/app/inbox/page.tsx ] && [ -s apps/web/app/patients/page.tsx ] && [ -s apps/web/app/tasks/page.tsx ] && [ -s apps/web/app/prior-auth/page.tsx ] && [ -s apps/web/app/analytics/page.tsx ] && [ -s apps/web/app/settings/page.tsx ]"

check "apps/web components" \
  "[ -s apps/web/components/Sidebar.tsx ] && [ -s apps/web/components/ui/button.tsx ] && [ -s apps/web/components/ui/card.tsx ] && [ -s apps/web/lib/utils.ts ]"

check "docs (ARCHITECTURE, SECURITY, EVAL, DEMO + 5 ADRs)" \
  "[ -s docs/ARCHITECTURE.md ] && [ -s docs/SECURITY.md ] && [ -s docs/EVAL.md ] && [ -s docs/DEMO.md ] && [ -s docs/DECISIONS/001-monorepo-pnpm-fastapi.md ] && [ -s docs/DECISIONS/002-tenant-isolation-session-guard.md ] && [ -s docs/DECISIONS/003-phi-encryption-fernet.md ] && [ -s docs/DECISIONS/004-schema-conventions.md ] && [ -s docs/DECISIONS/005-user-identity-model.md ]"

echo ""
echo "── Live checks ──"

check "Postgres ready on :5432" \
  "pg_isready -h localhost -p 5432 -U suture"

check "mypy strict passes on apps/api" \
  "cd apps/api && uv run mypy app"

check "ruff lint clean on apps/api" \
  "cd apps/api && uv run ruff check app tests"

check "pytest passes (test_health)" \
  "cd apps/api && uv run pytest -q tests/test_health.py"

check "pnpm install completed (apps/web/node_modules exists)" \
  "[ -d apps/web/node_modules ]"

check "tsc strict passes on apps/web" \
  "cd apps/web && pnpm exec tsc --noEmit"

if [ $fail -ne 0 ]; then
  echo ""
  echo "❌ Gate A verification FAILED"
  exit 1
fi
echo ""
echo "✅ Gate A verification passed"
