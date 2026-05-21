"""Field-value normalizers shared by the comparator.

These return either a normalized string or None when the input cannot be
parsed. Both sides of a comparison are normalized before equality is
tested, so casing / punctuation / formatting differences don't count as
errors.
"""

from __future__ import annotations

import re
from datetime import date

from app.services.extraction.validators import normalize_phone as _normalize_phone

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = _PUNCT_RE.sub(" ", value).lower().strip()
    cleaned = _WS_RE.sub(" ", cleaned)
    return cleaned or None


def normalize_phone(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _normalize_phone(value)


def normalize_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.upper().replace(" ", "").replace("\t", "") or None


def normalize_date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def normalize_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, int | float | bool):
        return str(value)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
