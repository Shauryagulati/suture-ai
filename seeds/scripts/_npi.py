"""Checksum-valid NPI generator.

The National Provider Identifier (NPI) is 10 digits where the 10th digit is a
Luhn check digit computed over the issuer prefix `80840` + the first 9 digits.

This is enough fidelity for development data — every generated NPI passes
the standard NPI verification algorithm used by clearinghouses.
"""

from __future__ import annotations

import random

# Prefix per CMS NPI registry: "80840" is prepended before the Luhn checksum.
_PREFIX = "80840"


def _luhn_checksum(digits: str) -> int:
    total = 0
    # Iterate right-to-left.
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:  # double every second digit from the right
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - (total % 10)) % 10


def generate_npi(rng: random.Random | None = None) -> str:
    """Return a 10-digit NPI that passes the standard NPI Luhn check."""
    rng = rng or random.Random()
    body = "".join(str(rng.randint(0, 9)) for _ in range(9))
    # Avoid leading 0 to keep it canonical 10 digits.
    if body[0] == "0":
        body = str(rng.randint(1, 9)) + body[1:]
    check = _luhn_checksum(_PREFIX + body)
    return body + str(check)


def is_valid_npi(npi: str) -> bool:
    if len(npi) != 10 or not npi.isdigit():
        return False
    return _luhn_checksum(_PREFIX + npi[:9]) == int(npi[9])
