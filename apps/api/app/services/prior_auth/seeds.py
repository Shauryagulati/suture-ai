"""Parse one payer's seed `.json` into typed rows for ingestion.

Pure parsing — no DB writes. The `payer_rule.schema.json` validator is
applied on load so malformed seeds blow up at ingestion time, not at
query time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]

_SCHEMA_PATH_HINT = "seeds/payer_rules/payer_rule.schema.json"


@dataclass(slots=True, frozen=True)
class PayerProcedureRow:
    """One (payer, procedure) cell as parsed from the structured JSON."""

    payer_name: str
    cpt_code: str
    description: str
    auth_required: bool
    required_documents: list[str]
    common_denial_reasons: list[str]
    typical_turnaround_days: int | None
    notes: str


@dataclass(slots=True, frozen=True)
class PayerSeedFile:
    """The full parsed contents of one payer's structured JSON."""

    payer_name: str
    effective_date: str
    source_note: str
    procedures: list[PayerProcedureRow]


def _turnaround_to_int(raw: int | list[int]) -> int | None:
    """Schema allows either an int (0 = no PA) or a [min, max] pair.

    We collapse to a single representative integer — the max, since clinics
    care about the worst-case wait. `0` becomes None to signal "no PA / no
    turnaround applies."
    """
    if isinstance(raw, list):
        return max(raw)
    if raw == 0:
        return None
    return raw


def load_payer_json(json_path: Path, schema_path: Path | None = None) -> PayerSeedFile:
    """Read and validate one payer's `.json`, returning typed rows.

    `schema_path` defaults to `<json_path>.parent / payer_rule.schema.json` so
    a caller that points at `seeds/payer_rules/highmark.json` gets the schema
    from the same directory for free.
    """
    if schema_path is None:
        schema_path = json_path.parent / "payer_rule.schema.json"
    if not schema_path.exists():
        raise FileNotFoundError(
            f"payer rule schema not found at {schema_path} — expected {_SCHEMA_PATH_HINT}"
        )

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)

    procedures = [
        PayerProcedureRow(
            payer_name=payload["payer"],
            cpt_code=proc["cpt_code"],
            description=proc["description"],
            auth_required=proc["prior_auth_required"],
            required_documents=list(proc["required_documents"]),
            common_denial_reasons=list(proc["common_denial_reasons"]),
            typical_turnaround_days=_turnaround_to_int(proc["typical_turnaround_business_days"]),
            notes=proc["notes"],
        )
        for proc in payload["procedures"]
    ]
    return PayerSeedFile(
        payer_name=payload["payer"],
        effective_date=payload["effective_date"],
        source_note=payload["source_note"],
        procedures=procedures,
    )
