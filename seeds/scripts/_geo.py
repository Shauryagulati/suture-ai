"""Western-PA geographic constraints for synthetic-data generation.

The user-confirmed v1 footprint is exactly these 7 cities. Do not introduce
others without an explicit decision — the patient/practice addresses are
asserted against this footprint and the eval corpus is designed around it.
"""

from __future__ import annotations

import random
from typing import TypedDict

from faker import Faker

# 7-city footprint with realistic ZIP prefixes per USPS data.
# Each tuple: (city_name, list of plausible 5-digit ZIPs for that municipality).
WESTERN_PA_CITIES: list[tuple[str, list[str]]] = [
    (
        "Pittsburgh",
        # City of Pittsburgh proper, sampling across neighborhoods
        ["15201", "15206", "15208", "15213", "15217", "15219", "15222", "15232", "15237"],
    ),
    ("Monroeville", ["15146"]),
    ("Cranberry Twp", ["16066"]),
    ("Greensburg", ["15601"]),
    ("Washington", ["15301"]),
    ("Butler", ["16001"]),
    ("Beaver", ["15009"]),
]

# Pittsburgh-area landline area codes — all synthetic phones use one of these
# with the NANP-reserved-fictional `555` exchange.
PITTSBURGH_AREA_CODES = ("412", "724", "878")


class Address(TypedDict):
    address_line1: str
    city: str
    state: str
    zip_code: str


def western_pa_address(fake: Faker, rng: random.Random) -> Address:
    """Return a synthetic Western-PA address.

    Street numbers and street names come from Faker (no real Pittsburgh
    addresses ever produced). City + ZIP come from the constrained list.
    """
    city, zips = rng.choice(WESTERN_PA_CITIES)
    # Faker normally returns "<num> <street>\n<city>, <state> <zip>"; we only
    # want the street line.
    street_line = fake.street_address()
    return Address(
        address_line1=street_line,
        city=city,
        state="PA",
        zip_code=rng.choice(zips),
    )


def western_pa_phone(rng: random.Random) -> str:
    """Return a Pittsburgh-area phone with the 555 fictional exchange."""
    area = rng.choice(PITTSBURGH_AREA_CODES)
    last_four = f"{rng.randint(0, 9999):04d}"
    return f"{area}-555-{last_four}"
