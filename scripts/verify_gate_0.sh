#!/usr/bin/env bash
# Verify Gate 0 — Claude Code project context.
# Exits 0 on pass, 1 on fail. STOP signals if anything fails.

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

echo "── Gate 0 verification ──"

check "CLAUDE.md exists and non-empty" "[ -s CLAUDE.md ]"
check ".claude/settings.json is valid JSON" "jq . .claude/settings.json"

for f in eval migrate verify-tenant audit-check new-extraction-case; do
  check ".claude/commands/$f.md present" "[ -s .claude/commands/$f.md ]"
done

for skill in extraction-prompt-skill migration-skill audit-logging-skill eval-case-skill; do
  check "ai/skills/$skill/SKILL.md present" "[ -s ai/skills/$skill/SKILL.md ]"
done

check "migration-skill is substantive (>50 lines)" \
  "[ \$(wc -l < ai/skills/migration-skill/SKILL.md) -gt 50 ]"

check "Sub-app stubs present" \
  "[ -s apps/web/CLAUDE.md ] && [ -s apps/api/CLAUDE.md ] && [ -s services/voice-agent/CLAUDE.md ]"

if [ $fail -ne 0 ]; then
  echo ""
  echo "❌ Gate 0 verification FAILED"
  exit 1
fi
echo ""
echo "✅ Gate 0 verification passed"
