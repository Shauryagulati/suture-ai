"""Verify the structlog PHI scrubber drops keys in the deny list."""

from __future__ import annotations

import json
import logging

import structlog

from app.utils.logging import PHI_DENY_LIST, configure_logging


def test_phi_keys_dropped_from_log_event(
    caplog: object,  # type: ignore[unused-argument]
    capsys: object,
) -> None:
    """An event with PHI keys must have them stripped before render."""
    configure_logging(level="DEBUG")
    log = structlog.get_logger("test")
    # Log a PHI-laden context dict.
    log.info(
        "patient_access",
        patient_id="00000000-0000-0000-0000-000000000001",
        first_name="Jane",
        last_name="Doe",
        dob="1965-01-15",
        phone="555-867-5309",
        ssn="123-45-6789",
        mrn="MRN-12345",
        email="jane@example.com",
        address_line1="100 Main St",
        nested={"first_name": "Jane", "innocuous": "ok"},
    )

    captured = capsys.readouterr().out  # type: ignore[attr-defined]
    # Parse one JSON line at minimum.
    lines = [line for line in captured.splitlines() if line.strip()]
    assert lines, "expected at least one log line, got nothing"
    parsed = json.loads(lines[-1])

    # The deny-listed keys MUST be gone from the top-level event dict.
    for forbidden in (
        "first_name",
        "last_name",
        "dob",
        "phone",
        "ssn",
        "mrn",
        "email",
        "address_line1",
    ):
        assert forbidden in PHI_DENY_LIST  # sanity
        assert forbidden not in parsed, f"PHI key '{forbidden}' leaked into log output: {parsed}"

    # The non-PHI patient_id should survive.
    assert parsed.get("patient_id") == "00000000-0000-0000-0000-000000000001"

    # Nested dicts get the same treatment.
    assert "first_name" not in parsed.get("nested", {})
    assert parsed.get("nested", {}).get("innocuous") == "ok"

    # The JSON output must not contain "Jane" anywhere (PHI value).
    assert "Jane" not in json.dumps(parsed)

    # Reset stdlib logging so other tests aren't polluted.
    logging.getLogger().handlers.clear()
