"""Flatten nested extraction dicts to dot-notation paths.

Code arrays (``diagnosis_codes``, ``procedure_codes``, ``urgent_flags``)
are kept as lists so the comparator can do set-equality. Object arrays
(``procedures_performed[0].cpt_code``) are expanded with bracket indices.
Scalar paths point directly to their primitive value.
"""

from __future__ import annotations

from typing import Any

# Paths whose array value stays whole — the comparator scores them by
# set equality (precision/recall over the elements), not per-element
# exact match.
_SET_ARRAY_PATHS: frozenset[str] = frozenset(
    {"diagnosis_codes", "procedure_codes", "urgent_flags"}
)

# Top-level keys that aren't real extracted fields.
_RESERVED_KEYS: frozenset[str] = frozenset(
    {
        "missing_fields",
        "classification",
        "document_external_id",
        "is_degraded",
    }
)


def flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten ``d`` into a dot-notation map.

    Nested dicts recurse. List-of-objects expand with ``[i]``. List-of-
    primitives stay as lists when the leaf key is in ``_SET_ARRAY_PATHS``;
    otherwise they too expand with ``[i]``.
    """
    out: dict[str, Any] = {}
    for key, value in d.items():
        if key in _RESERVED_KEYS and prefix == "":
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, prefix=path))
            continue
        if isinstance(value, list):
            if key in _SET_ARRAY_PATHS:
                out[path] = value
                continue
            for i, elem in enumerate(value):
                child = f"{path}[{i}]"
                if isinstance(elem, dict):
                    out.update(flatten(elem, prefix=child))
                else:
                    out[child] = elem
            continue
        out[path] = value
    return out
