#!/usr/bin/env bash
# 7-check structural verification for the committed synthetic-data corpus.
#
# This script is the verifier for the synthetic eval corpus. It does NOT
# regenerate anything — it just checks the committed bytes are well-formed.
# To regenerate, use `make seed-synthetic` (which is idempotent and reads
# committed LLM fixtures).

set -euo pipefail
cd "$(dirname "$0")/.."

pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; exit 1; }

echo "=== Suture synthetic-data verification ==="

# 1. 30 referral PDFs
n_ref_pdf=$(ls seeds/documents/referrals/REF-*.pdf 2>/dev/null | wc -l | tr -d ' ')
[ "$n_ref_pdf" -eq 30 ] || fail "expected 30 referral PDFs, found $n_ref_pdf"
pass "30 referral PDFs"

# 2. 30 referral ground-truth JSONs
n_ref_gt=$(ls seeds/documents/referrals/REF-*.ground-truth.json 2>/dev/null | wc -l | tr -d ' ')
[ "$n_ref_gt" -eq 30 ] || fail "expected 30 referral ground-truth JSONs, found $n_ref_gt"
pass "30 referral ground-truth JSONs"

# 3. 20 discharge PDFs
n_dis_pdf=$(ls seeds/documents/discharges/DIS-*.pdf 2>/dev/null | wc -l | tr -d ' ')
[ "$n_dis_pdf" -eq 20 ] || fail "expected 20 discharge PDFs, found $n_dis_pdf"
pass "20 discharge PDFs"

# 4. 20 discharge ground-truth JSONs
n_dis_gt=$(ls seeds/documents/discharges/DIS-*.ground-truth.json 2>/dev/null | wc -l | tr -d ' ')
[ "$n_dis_gt" -eq 20 ] || fail "expected 20 discharge ground-truth JSONs, found $n_dis_gt"
pass "20 discharge ground-truth JSONs"

# 5. patients.json + referring_practices.json present
[ -f seeds/data/patients.json ] || fail "seeds/data/patients.json missing"
[ -f seeds/data/referring_practices.json ] || fail "seeds/data/referring_practices.json missing"
pass "patients.json + referring_practices.json present"

# 6. 5 payer rule .md (excluding README) + 5 .json (excluding schema)
n_payer_md=$(ls seeds/payer_rules/*.md 2>/dev/null | grep -v README | wc -l | tr -d ' ')
n_payer_json=$(ls seeds/payer_rules/*.json 2>/dev/null | grep -v payer_rule.schema.json | wc -l | tr -d ' ')
[ "$n_payer_md" -eq 5 ] || fail "expected 5 payer .md files, found $n_payer_md"
[ "$n_payer_json" -eq 5 ] || fail "expected 5 payer .json files, found $n_payer_json"
pass "5 payer .md + 5 payer .json"

# 7. pytest seeds/tests/ — runs schema validation + cross-corpus invariants
echo "--- pytest seeds/tests/ ---"
uv --project apps/api run python -m pytest seeds/tests/ -v --no-header
pass "pytest seeds/tests/ passed"

echo
echo "All synthetic-data checks passed."
