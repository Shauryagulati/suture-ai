"""Ground-truth validators and PDF text extraction.

Helpers used by the structural test suite in seeds/tests/. Kept in
`seeds/scripts/` (not under `tests/`) so they're importable from both
the test path and from ad-hoc scripts.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from seeds.scripts._utils import SCHEMAS_DIR


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))


_REFERRAL_SCHEMA = None
_DISCHARGE_SCHEMA = None
_PATIENT_SCHEMA = None
_PRACTICE_SCHEMA = None


def _referral_schema() -> dict:
    global _REFERRAL_SCHEMA
    if _REFERRAL_SCHEMA is None:
        _REFERRAL_SCHEMA = _load_schema("referral_ground_truth.schema.json")
    return _REFERRAL_SCHEMA


def _discharge_schema() -> dict:
    global _DISCHARGE_SCHEMA
    if _DISCHARGE_SCHEMA is None:
        _DISCHARGE_SCHEMA = _load_schema("discharge_ground_truth.schema.json")
    return _DISCHARGE_SCHEMA


def validate_referral_gt(path: Path) -> dict:
    """Parse + schema-validate a referral ground-truth JSON. Returns the parsed dict."""
    data = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.validate(data, _referral_schema())
    return data


def validate_discharge_gt(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.validate(data, _discharge_schema())
    return data


def parse_pdf_text(path: Path) -> str:
    """Extract text from a PDF via pypdf. Returns "" for image-only / degraded PDFs."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            # Degraded PDFs may have malformed text layers; treat as no text.
            parts.append("")
    return "\n".join(parts)
