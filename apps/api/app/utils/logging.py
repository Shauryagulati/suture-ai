"""Structured logging with PHI scrubbing.

The deny-list processor drops keys known to carry PHI before structlog renders
the event. This is a defense-in-depth control: app code should never log PHI in
the first place, but if it accidentally does, the processor catches it.

Tested in Gate B1 (tests/test_logging_phi_safe.py).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

# Keys that may carry PHI. Dropped at the processor layer.
# Conservative — better to drop a benign field than to leak a sensitive one.
PHI_DENY_LIST: frozenset[str] = frozenset(
    {
        "first_name",
        "last_name",
        "full_name",
        "name",
        "dob",
        "date_of_birth",
        "phone",
        "phone_number",
        "email",
        "ssn",
        "social_security_number",
        "mrn",
        "medical_record_number",
        "address",
        "address_line1",
        "address_line2",
        "street",
        "member_id",
        "insurance_member_id",
    }
)


def scrub_phi(_logger: WrappedLogger, _name: str, event_dict: EventDict) -> EventDict:
    """Drop PHI-laden keys from the event dict before rendering.

    Recurses one level into dict values (sufficient for our log shapes).
    """
    scrubbed: EventDict = {}
    for key, value in event_dict.items():
        if key in PHI_DENY_LIST:
            continue
        if isinstance(value, dict):
            scrubbed[key] = {k: v for k, v in value.items() if k not in PHI_DENY_LIST}
        else:
            scrubbed[key] = value
    return scrubbed


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib logging with PHI scrubbing.

    Called once at app startup from lifespan.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Plain stdlib config for libraries that bypass structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            scrub_phi,
            # Render tracebacks WITHOUT frame locals: locals can carry PHI
            # (OCR'd document text, prompts) that scrub_phi cannot reach —
            # it runs earlier and scrubs by key name only.
            structlog.processors.ExceptionRenderer(
                structlog.tracebacks.ExceptionDictTransformer(show_locals=False)
            ),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a structlog logger. Wrapper for typing convenience."""
    return structlog.get_logger(name)
