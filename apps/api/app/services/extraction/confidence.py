"""Deterministic per-field confidence scoring (decision #4 of the Module 2 plan).

Rules:
- present + validator pass         → 0.95
- present + no validator           → 0.85
- present + validator fail         → 0.40
- missing (null or in missing_fields) → 0.0

`needs_review` = True when any score < 0.85 OR missing_fields is non-empty.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.extraction.validators import (
    is_valid_cpt,
    is_valid_date,
    is_valid_icd10,
    is_valid_npi,
    is_valid_phone,
    is_valid_state,
    is_valid_zip,
)

_PASS = 0.95
_NO_VALIDATOR = 0.85
_FAIL = 0.40
_MISSING = 0.0

_NEEDS_REVIEW_THRESHOLD = 0.85

# Validator dispatch by the last segment of the dot-path.
_SCALAR_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "dob": is_valid_date,
    "admit_date": is_valid_date,
    "discharge_date": is_valid_date,
    "phone": is_valid_phone,
    "practice_phone": is_valid_phone,
    "practice_fax": is_valid_phone,
    "zip_code": is_valid_zip,
    "npi": is_valid_npi,
    "state": is_valid_state,
    "cpt_code": is_valid_cpt,
}

# For arrays of primitives, validate every element.
_ARRAY_ELEMENT_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "diagnosis_codes": is_valid_icd10,
    "procedure_codes": is_valid_cpt,
}

# Reserved keys in the LLM payload that should not appear in confidences.
_RESERVED_KEYS = {"missing_fields"}


def _tail(path: str) -> str:
    return path.rsplit(".", 1)[-1] if "." in path else path


def _scalar_validator_for(path: str) -> Callable[[Any], bool] | None:
    return _SCALAR_VALIDATORS.get(_tail(path))


def _array_element_validator_for(path: str) -> Callable[[Any], bool] | None:
    return _ARRAY_ELEMENT_VALIDATORS.get(_tail(path))


def _score_field(path: str, value: Any, missing_set: set[str], out: dict[str, float]) -> None:
    if path in missing_set:
        out[path] = _MISSING
        return
    if value is None:
        out[path] = _MISSING
        return
    if isinstance(value, dict):
        for key, sub in value.items():
            _score_field(f"{path}.{key}", sub, missing_set, out)
        return
    if isinstance(value, list):
        elem_validator = _array_element_validator_for(path)
        if not value:
            out[path] = _MISSING
            return
        # Array of objects → score each element's fields, no top-level score.
        if isinstance(value[0], dict):
            for i, elem in enumerate(value):
                _score_field(f"{path}[{i}]", elem, missing_set, out)
            return
        # Array of primitives.
        if elem_validator is None:
            out[path] = _NO_VALIDATOR
            return
        out[path] = _PASS if all(elem_validator(v) for v in value) else _FAIL
        return
    # Scalar.
    validator = _scalar_validator_for(path)
    if validator is None:
        out[path] = _NO_VALIDATOR
    elif validator(value):
        out[path] = _PASS
    else:
        out[path] = _FAIL


def compute_field_confidences(
    extraction: dict[str, Any],
    missing_fields: list[str],
) -> tuple[dict[str, float], bool]:
    """Walk the extraction dict, return ``(confidences, needs_review)``.

    Whole-doc parse failures (caller passes ``{}``) collapse to no confidences
    and ``needs_review=True`` — see decision #4.
    """
    if not extraction:
        return {}, True

    missing_set = set(missing_fields or [])
    confidences: dict[str, float] = {}

    for key, value in extraction.items():
        if key in _RESERVED_KEYS:
            continue
        _score_field(key, value, missing_set, confidences)

    # Force-zero any explicitly-missing path that didn't surface in the tree
    # (e.g., the LLM lists `insurance.primary.group_number` as missing but
    # nests `null` so we already scored 0.0 — this is idempotent).
    for path in missing_set:
        confidences[path] = _MISSING

    needs_review = bool(missing_set) or any(
        score < _NEEDS_REVIEW_THRESHOLD for score in confidences.values()
    )
    return confidences, needs_review
