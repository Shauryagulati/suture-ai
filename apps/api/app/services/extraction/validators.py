"""Pure validators for extracted fields. No DB, no I/O.

These are used by ``confidence.py`` to score per-field extraction quality
deterministically — see decision #4 in the Module 2 plan.
"""

from __future__ import annotations

import re
from datetime import datetime

_ICD10_RE = re.compile(r"^[A-Z]\d{2}(\.\d{1,4})?$")
_CPT_RE = re.compile(r"^\d{5}$")
_ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")

# Canonical US states + DC. The extractor emits either the USPS two-letter
# code ("PA") or the full name ("Pennsylvania"); both are valid.
_US_STATES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}
_STATE_ABBREVS: frozenset[str] = frozenset(_US_STATES)
_STATE_NAMES: frozenset[str] = frozenset(name.upper() for name in _US_STATES.values())


def is_valid_icd10(code: str) -> bool:
    if not isinstance(code, str):
        return False
    return bool(_ICD10_RE.match(code.strip()))


def is_valid_cpt(code: str) -> bool:
    if not isinstance(code, str):
        return False
    return bool(_CPT_RE.match(code.strip()))


def is_valid_npi(npi: str) -> bool:
    """Validate a 10-digit National Provider Identifier via Luhn-mod-10.

    NPIs use the standard Luhn algorithm with the issuer prefix ``80840``
    prepended before checksumming (HIPAA Standard Unique Health Identifier
    spec). The 10th digit is the check digit.
    """
    if not isinstance(npi, str):
        return False
    npi = npi.strip()
    if len(npi) != 10 or not npi.isdigit():
        return False
    # Prepend the NPI issuer prefix; the full 15-digit string (prefix + body
    # + check digit) must pass standard Luhn.
    digits = [int(c) for c in "80840" + npi]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d >= 10:
                d -= 9
        total += d
    return total % 10 == 0


def normalize_phone(phone: str) -> str | None:
    """Strip non-digits; return E.164-ish ``+1XXXXXXXXXX`` or None if not parseable."""
    if not isinstance(phone, str):
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def is_valid_phone(phone: str) -> bool:
    return normalize_phone(phone) is not None


def is_valid_zip(zip_str: str) -> bool:
    if not isinstance(zip_str, str):
        return False
    return bool(_ZIP_RE.match(zip_str.strip()))


def is_valid_date(s: str) -> bool:
    if not isinstance(s, str):
        return False
    try:
        datetime.fromisoformat(s)
        return True
    except ValueError:
        return False


def is_valid_state(s: str) -> bool:
    """Accept a real USPS two-letter code ("PA") or a full state name
    ("Pennsylvania"), case-insensitively. Rejects bogus two-letter strings
    like "ZZ" that the old length/uppercase-only check let through.
    """
    if not isinstance(s, str):
        return False
    candidate = s.strip()
    return candidate.upper() in _STATE_ABBREVS or candidate.upper() in _STATE_NAMES
