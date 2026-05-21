"""Shared reportlab styles for prior-auth PDFs.

Copied from seeds/scripts/_pdf.py rather than imported across the
seeds → apps boundary. The seeds package is a sibling of apps/ and is
allowed to depend on it but not the other way around.
"""

from __future__ import annotations

from typing import Any

from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.styles import (  # type: ignore[import-untyped]
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.lib.units import inch  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    Paragraph,
    Table,
    TableStyle,
)


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontSize=14,
            spaceAfter=6,
            textColor=colors.HexColor("#0b3954"),
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontSize=11,
            spaceAfter=4,
            textColor=colors.HexColor("#0b3954"),
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontSize=10,
            leading=13,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.grey,
        ),
        "quote": ParagraphStyle(
            "Quote",
            parent=base["BodyText"],
            fontSize=9,
            leading=12,
            leftIndent=12,
            textColor=colors.HexColor("#333333"),
            spaceAfter=4,
        ),
    }


def two_col_table(rows: list[tuple[str, str]]) -> Table:
    """Compact label/value table used for patient + insurance blocks."""
    s = styles()
    data: list[list[Any]] = [
        [Paragraph(f"<b>{k}</b>", s["body"]), Paragraph(v or "<i>—</i>", s["body"])]
        for k, v in rows
    ]
    tbl = Table(data, colWidths=[1.6 * inch, 4.4 * inch])
    tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return tbl
