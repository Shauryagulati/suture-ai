"""Verify the structlog PHI scrubber drops keys in the deny list."""

from __future__ import annotations

import json
import logging

import httpx
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


def test_exception_rendering_never_serializes_frame_locals(capsys: object) -> None:
    """Traceback locals must never reach log output (no-PHI-in-logs invariant).

    Regression: an httpx.ReadTimeout during extraction was rendered by
    dict_tracebacks with show_locals=True, dumping the frame-local OCR'd
    document text and prompt into the app log.
    """
    configure_logging(level="DEBUG")
    log = structlog.get_logger("test")
    sentinel = "PHI_SENTINEL_DISCHARGE_SUMMARY_XYZZY"

    def _extract(text: str) -> None:
        # Mirrors extract_document's frame shape: PHI-bearing locals.
        user_prompt = f"Extract the following document:\n\n{text}"
        raise httpx.ReadTimeout(f"timed out ({len(user_prompt)} chars)")

    try:
        _extract(sentinel)
    except httpx.ReadTimeout:
        log.exception("documents.extraction_failed", document_id="doc-1")

    captured = capsys.readouterr().out  # type: ignore[attr-defined]
    lines = [line for line in captured.splitlines() if line.strip()]
    assert lines, "expected a log line"
    parsed = json.loads(lines[-1])
    # The traceback must still render (we need the stack, just not the locals)...
    assert parsed.get("exception"), f"exception traceback missing from event: {parsed}"
    # ...but no frame-local value may appear anywhere in the raw output.
    assert sentinel not in captured, "frame locals leaked into log output"

    logging.getLogger().handlers.clear()
