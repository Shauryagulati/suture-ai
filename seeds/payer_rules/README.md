# Payer rule sets

Structured prior-authorization rules for the 5 commercial payers Suture
tracks in v1, scoped to the 5 cardiology procedures Module 2 extracts and
Module 4 (prior-auth) writes packets for.

## Payers covered

| Payer | Files |
|---|---|
| Highmark Blue Cross Blue Shield (PA) | `highmark.md`, `highmark.json` |
| UPMC Health Plan | `upmc.md`, `upmc.json` |
| Aetna | `aetna.md`, `aetna.json` |
| UnitedHealthcare | `uhc.md`, `uhc.json` |
| Cigna | `cigna.md`, `cigna.json` |

## Procedures covered

| CPT | Description |
|---|---|
| 93015 | Cardiovascular stress test, treadmill |
| 93306 | Transthoracic echocardiogram (TTE) |
| 93458 | Left heart catheterization with contrast |
| 93620 | Comprehensive electrophysiologic evaluation |
| 93224 | 48-hour Holter monitor |

## Why both `.md` and `.json`?

- **`.md`** — natural-language summary intended for embedding into the
  Module 4 RAG knowledge base. Sentences flow conversationally; the
  pgvector index over these chunks gets used when the assistant needs to
  reason about a specific payer/procedure combination.
- **`.json`** — structured filter view. Module 4 also runs explicit
  structured queries ("does payer X require PA for CPT Y?") that need
  predictable shape and machine-checkable booleans. Schema validation
  via `payer_rule.schema.json`.

The two MUST stay in sync — if a `.md` says "PA required" the `.json`
must say `"prior_auth_required": true`. There's no automated check for
narrative ↔ structured consistency yet; it's caught at human review.

## Why hand-written and not Claude-generated?

The eval corpus uses Claude Haiku for clinical narratives because
variety improves the signal. Payer rules are the OPPOSITE problem:
they need to be CORRECT, not varied. A hallucinated turnaround time
or a wrong CPT requirement here would poison Module 4's RAG and the
prior-auth packet output. Hand-written from public payer policy
documents is the conservative choice and was faster than verifying
AI output for 5 × 5 = 25 (payer, procedure) cells.

## Schema

`payer_rule.schema.json` validates each payer's JSON. To verify all
five at once:

```bash
uv --project apps/api run python -c "
import json, jsonschema, pathlib
schema = json.loads(pathlib.Path('seeds/payer_rules/payer_rule.schema.json').read_text())
for p in pathlib.Path('seeds/payer_rules').glob('*.json'):
    if p.name == 'payer_rule.schema.json': continue
    jsonschema.validate(json.loads(p.read_text()), schema)
    print('OK', p.name)
"
```

## Disclaimer

**These are SIMULATED policy summaries.** They are NOT a substitute for
the live payer portals. Any production use of Suture against a real
patient must consult the payer's current policy at order time. The
structured fields here drive Module 4's RAG and packet-generation
behavior in dev/test environments only.
