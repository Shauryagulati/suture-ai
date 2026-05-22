"""PDF text extraction with Docling primary + pypdf fallback.

Docling handles both native-text PDFs and rasterized fax scans (vision OCR);
pypdf catches the case where Docling fails for any reason (model not loaded,
conversion error, etc.). Both backends are sync libraries, so we wrap their
calls in ``asyncio.to_thread`` to keep the event loop responsive.

Docling is imported lazily inside ``_extract_with_docling`` so importing this
module at FastAPI boot does not trigger Docling's multi-GB model load — the
first real call pays that cost once, then ``_docling_converter`` caches the
instance for the process lifetime.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import structlog

logger = structlog.get_logger(__name__)

OcrEngine = Literal["docling", "pypdf"]


@lru_cache(maxsize=1)
def _docling_converter() -> Any:
    """Build a Docling converter pinned to CPU.

    Docling defaults to ``device='auto'``, which selects MPS on Apple
    Silicon. As of docling 2.94 / PyTorch 2.x the MPS path hits
    ``Cannot convert a MPS Tensor to float64 dtype`` on any document that
    triggers the layout/OCR models (i.e., every scanned PDF in our
    corpus). The pypdf fallback then yields empty text for those
    rasterized pages and extraction silently degrades to
    ``__parse_failed__``. CPU is slower but correct everywhere; override
    with ``SUTURE_OCR_DEVICE=mps`` (or ``cuda``) at your own risk.
    """
    import os

    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    device_name = os.getenv("SUTURE_OCR_DEVICE", "cpu").lower()
    try:
        device = AcceleratorDevice(device_name)
    except ValueError:
        device = AcceleratorDevice.CPU

    pdf_opts = PdfPipelineOptions()
    pdf_opts.accelerator_options = AcceleratorOptions(device=device)
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts)}
    )


def _extract_with_docling(pdf_path: Path) -> str:
    converter = _docling_converter()
    result = converter.convert(str(pdf_path))
    return str(result.document.export_to_markdown())


def _extract_with_pypdf(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text)
    return "\n\n".join(pages)


async def extract_text(pdf_path: Path) -> tuple[str, OcrEngine]:
    """Return ``(text, engine)``. Tries Docling first; falls back to pypdf on any failure."""
    try:
        text = await asyncio.to_thread(_extract_with_docling, pdf_path)
        return text, "docling"
    except Exception as exc:
        logger.warning(
            "ocr.docling_failed",
            pdf_path=str(pdf_path),
            error=str(exc),
            error_type=type(exc).__name__,
        )

    try:
        text = await asyncio.to_thread(_extract_with_pypdf, pdf_path)
    except Exception as exc:
        logger.warning(
            "ocr.pypdf_failed",
            pdf_path=str(pdf_path),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        text = ""
    return text, "pypdf"
