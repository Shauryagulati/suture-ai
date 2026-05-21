"""On-disk PDF storage for uploaded documents.

PDFs land at `{document_storage_path}/{clinic_id}/{uuid4}.pdf`. Filenames are
UUID-derived, never the user-supplied name — this is the primary defense
against path traversal and collisions. The original filename is preserved
in `documents.file_name` for display, but not on disk.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import aiofiles

from app.config import get_settings


async def save_pdf(*, clinic_id: UUID, content: bytes) -> tuple[Path, int]:
    """Persist a PDF for the given clinic. Returns the absolute path and byte count.

    The clinic directory is created on demand. The filename is a fresh uuid4
    plus ``.pdf`` so concurrent uploads cannot collide and a malicious
    ``file.filename`` cannot escape the storage root.
    """
    settings = get_settings()
    clinic_dir = settings.document_storage_path / str(clinic_id)
    clinic_dir.mkdir(parents=True, exist_ok=True)

    target = (clinic_dir / f"{uuid4()}.pdf").resolve()
    async with aiofiles.open(target, "wb") as f:
        await f.write(content)
    return target, len(content)
