"""Unit tests for extraction validators + deterministic confidence scoring.

No DB, no LLM. Pure functions.
"""

from __future__ import annotations

import pytest

from app.services.extraction.confidence import compute_field_confidences
from app.services.extraction.validators import (
    is_plausible_name,
    is_valid_cpt,
    is_valid_date,
    is_valid_icd10,
    is_valid_npi,
    is_valid_phone,
    is_valid_state,
    is_valid_zip,
    normalize_phone,
)

# ---------------------------- validators ---------------------------------


@pytest.mark.parametrize(
    "code",
    ["I25.10", "R07.9", "I21.09", "Z00", "M54.5", "A00.0000"],
)
def test_icd10_accepts_canonical(code: str) -> None:
    assert is_valid_icd10(code) is True


@pytest.mark.parametrize(
    "code",
    ["", "i25.10", "I2510", "I25.", "12.34", "I25.10X", "I25.123456", None, 123],
)
def test_icd10_rejects_malformed(code: object) -> None:
    assert is_valid_icd10(code) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("code", ["93306", "93015", "00000", "99999"])
def test_cpt_accepts_five_digit(code: str) -> None:
    assert is_valid_cpt(code) is True


@pytest.mark.parametrize("code", ["", "9330", "933060", "9330A", None, 93306])
def test_cpt_rejects_malformed(code: object) -> None:
    assert is_valid_cpt(code) is False  # type: ignore[arg-type]


def test_npi_accepts_valid_luhn() -> None:
    # 1234567893 — canonical Luhn-passing NPI used widely as a test fixture.
    assert is_valid_npi("1234567893") is True


def test_npi_accepts_seeded_fixture() -> None:
    # From REF-001.ground-truth.json — these seeds should round-trip.
    assert is_valid_npi("2423884966") is True


@pytest.mark.parametrize(
    "npi",
    ["", "1234567890", "123456789", "12345678901", "abcdefghij", "1234567894", None],
)
def test_npi_rejects_invalid(npi: object) -> None:
    assert is_valid_npi(npi) is False  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("412-555-1234", "+14125551234"),
        ("(412) 555-1234", "+14125551234"),
        ("1-412-555-1234", "+14125551234"),
        ("4125551234", "+14125551234"),
        ("14125551234", "+14125551234"),
        ("+1 412 555 1234", "+14125551234"),
    ],
)
def test_normalize_phone_round_trip(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("phone", ["", "123", "555-1234", "999999999999", None])
def test_normalize_phone_rejects_garbage(phone: object) -> None:
    assert normalize_phone(phone) is None  # type: ignore[arg-type]


def test_is_valid_phone_proxies_normalize() -> None:
    assert is_valid_phone("412-555-1234") is True
    assert is_valid_phone("nope") is False


@pytest.mark.parametrize("zip_code", ["15222", "15222-1234", "00000"])
def test_zip_accepts_5_or_9(zip_code: str) -> None:
    assert is_valid_zip(zip_code) is True


@pytest.mark.parametrize("zip_code", ["", "1522", "152221", "ABCDE", "15222-12", None])
def test_zip_rejects_malformed(zip_code: object) -> None:
    assert is_valid_zip(zip_code) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("date", ["1966-03-13", "2024-12-31", "2024-01-01T00:00:00"])
def test_date_accepts_iso(date: str) -> None:
    assert is_valid_date(date) is True


@pytest.mark.parametrize("date", ["", "03/13/1966", "1966-13-03", "yesterday", None])
def test_date_rejects_non_iso(date: object) -> None:
    assert is_valid_date(date) is False  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "state",
    [
        "PA",
        "NY",
        "CA",
        "pa",  # case-insensitive abbreviation
        "Pennsylvania",  # full name
        "pennsylvania",  # full name, lowercase
        "New York",  # multi-word full name
        " PA ",  # surrounding whitespace
    ],
)
def test_state_accepts_codes_and_names(state: str) -> None:
    assert is_valid_state(state) is True


@pytest.mark.parametrize("state", ["ZZ", "XX", "PAA", "P", "Pennsylvanai", "", None, "P1"])
def test_state_rejects_non_canonical(state: object) -> None:
    # "ZZ"/"XX" are the regression the old length-only check let through.
    assert is_valid_state(state) is False  # type: ignore[arg-type]


# ---------------------------- confidence scorer --------------------------


def _ref_001_extraction() -> dict[str, object]:
    """A trimmed copy of REF-001 ground truth — used as the happy-path fixture."""
    return {
        "patient": {
            "first_name": "Amy",
            "last_name": "Robinson",
            "dob": "1966-03-13",
            "mrn": "MRN-654235",
            "phone": None,
            "address_line1": "33890 Jennifer Squares",
            "city": "Pittsburgh",
            "state": "PA",
            "zip_code": "15222",
        },
        "insurance": {
            "primary": {
                "payer": "Highmark BCBS PA",
                "member_id": "LBC104332181",
                "group_number": None,
            },
            "secondary": None,
        },
        "referring_provider": {
            "first_name": "Shawn",
            "last_name": "Flowers",
            "npi": "2423884966",
            "practice_name": "Greater Pittsburgh Primary Care Associates",
            "practice_phone": "878-555-6543",
            "practice_fax": "878-555-7517",
        },
        "diagnosis_codes": ["R07.9"],
        "procedure_codes": ["93015"],
        "urgency": "routine",
        "follow_up_window_days": 22,
        "referral_type": "stress_test",
        "clinical_notes_excerpt": "Mr. [Patient] is a 60-year-old male...",
    }


def test_confidence_happy_path_mostly_high() -> None:
    extraction = _ref_001_extraction()
    missing = ["patient.phone", "insurance.primary.group_number", "insurance.secondary"]

    confidences, needs_review = compute_field_confidences(extraction, missing)

    assert confidences["patient.dob"] == 0.95  # valid ISO date
    assert confidences["patient.state"] == 0.95  # valid 2-letter
    assert confidences["patient.zip_code"] == 0.95  # valid 5-digit
    assert confidences["patient.mrn"] == 0.85  # no validator
    assert confidences["referring_provider.npi"] == 0.95  # Luhn-valid
    assert confidences["referring_provider.practice_phone"] == 0.95  # 10 digits
    assert confidences["diagnosis_codes"] == 0.95  # all ICD-10 ok
    assert confidences["procedure_codes"] == 0.95  # all CPT ok
    assert confidences["urgency"] == 0.85  # no validator
    assert confidences["follow_up_window_days"] == 0.85

    # Missing-listed fields collapse to 0.
    assert confidences["patient.phone"] == 0.0
    assert confidences["insurance.primary.group_number"] == 0.0
    assert confidences["insurance.secondary"] == 0.0

    assert needs_review is True  # missing_fields non-empty


def test_confidence_validator_failure_gets_fail_score() -> None:
    extraction = _ref_001_extraction()
    extraction["referring_provider"]["npi"] = "9999999999"  # type: ignore[index]
    extraction["diagnosis_codes"] = ["NotACode"]
    extraction["patient"]["zip_code"] = "ABCDE"  # type: ignore[index]
    extraction["patient"]["dob"] = "13/03/1966"  # type: ignore[index]

    confidences, needs_review = compute_field_confidences(extraction, [])

    assert confidences["referring_provider.npi"] == 0.40
    assert confidences["diagnosis_codes"] == 0.40
    assert confidences["patient.zip_code"] == 0.40
    assert confidences["patient.dob"] == 0.40
    assert needs_review is True


def test_confidence_clean_doc_no_missing_no_review() -> None:
    extraction = _ref_001_extraction()
    # Backfill the optional nulls so nothing is missing.
    extraction["patient"]["phone"] = "412-555-9999"  # type: ignore[index]
    extraction["insurance"]["primary"]["group_number"] = "GRP-100"  # type: ignore[index]
    extraction["insurance"]["secondary"] = {
        "payer": "Medicare",
        "member_id": "1AA1-AA1-AA11",
        "group_number": None,
    }
    # The secondary group_number is null but we'll mark it as missing.
    confidences, needs_review = compute_field_confidences(
        extraction, ["insurance.secondary.group_number"]
    )

    # That one missing field still triggers review.
    assert needs_review is True
    assert confidences["insurance.secondary.group_number"] == 0.0

    # Drop the missing field too.
    extraction["insurance"]["secondary"]["group_number"] = "GRP-200"  # type: ignore[index]
    confidences, needs_review = compute_field_confidences(extraction, [])
    assert needs_review is False
    assert all(score >= 0.85 for score in confidences.values())


def test_confidence_parse_failure_returns_empty_and_review() -> None:
    confidences, needs_review = compute_field_confidences({}, ["__parse_failed__"])
    assert confidences == {}
    assert needs_review is True


def test_confidence_missing_field_overrides_inline_value() -> None:
    """If a field is in missing_fields, it must score 0.0 even if a value is present."""
    extraction = {"patient": {"first_name": "Amy", "mrn": "MRN-1"}}
    confidences, _ = compute_field_confidences(extraction, ["patient.mrn"])
    assert confidences["patient.mrn"] == 0.0
    assert confidences["patient.first_name"] == 0.95  # plausible name validates


def test_confidence_arrays_of_objects_score_per_element() -> None:
    extraction = {
        "procedures_performed": [
            {"cpt_code": "93306", "description": "Echocardiogram"},
            {"cpt_code": "BAD", "description": "Invalid"},
        ],
    }
    confidences, needs_review = compute_field_confidences(extraction, [])
    assert confidences["procedures_performed[0].cpt_code"] == 0.95
    assert confidences["procedures_performed[0].description"] == 0.85
    assert confidences["procedures_performed[1].cpt_code"] == 0.40
    assert confidences["procedures_performed[1].description"] == 0.85
    assert needs_review is True


def test_confidence_empty_array_scores_missing() -> None:
    extraction = {"diagnosis_codes": [], "urgent_flags": []}
    confidences, needs_review = compute_field_confidences(extraction, [])
    assert confidences["diagnosis_codes"] == 0.0
    assert confidences["urgent_flags"] == 0.0
    assert needs_review is True


@pytest.mark.parametrize(
    "name", ["Amy", "O'Brien", "Mary-Jane", "José", "St. Claire", "van der Berg"]
)
def test_name_accepts_real_names(name: str) -> None:
    assert is_plausible_name(name) is True


@pytest.mark.parametrize(
    "name", ["", "x", "J0hn", "12345", "N/A", "Unknown", "none", "patient", "###", None]
)
def test_name_rejects_garbage(name: object) -> None:
    assert is_plausible_name(name) is False  # type: ignore[arg-type]


def test_confidence_garbage_name_is_not_green() -> None:
    # A junk name must drop to the FAIL band so review flags it (not 0.85/0.95).
    extraction = {"patient": {"first_name": "J0hn", "last_name": "Smith"}}
    confidences, needs_review = compute_field_confidences(extraction, [])
    assert confidences["patient.first_name"] == 0.40
    assert confidences["patient.last_name"] == 0.95
    assert needs_review is True


def test_confidence_missing_fields_key_not_self_scored() -> None:
    """The literal `missing_fields` key in the LLM payload is not a field to score."""
    extraction = {"missing_fields": ["patient.phone"], "patient": {"first_name": "Amy"}}
    confidences, _ = compute_field_confidences(extraction, ["patient.phone"])
    assert "missing_fields" not in confidences
    assert confidences["patient.first_name"] == 0.95  # plausible name validates
