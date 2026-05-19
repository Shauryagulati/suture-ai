"""Field-level PHI encryption via Fernet.

The `EncryptedString` TypeDecorator wraps `cryptography.fernet.Fernet` and
encrypts at the ORM boundary. Migrations see the column as a plain string;
the ciphertext is what's actually in the DB.

Key sourced from `settings.PHI_ENCRYPTION_KEY`. Generated locally via
`make gen-phi-key`. **Never commit the key.**

Trade-offs (see ADR 003):
- Encrypted columns are NOT searchable (`WHERE phone = '...'` won't work).
- Two rows with the same plaintext have different ciphertext (Fernet IV).
- Rotating the key requires a one-time re-encrypt migration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class PhiEncryptionKeyMissingError(RuntimeError):
    """Raised at first use when PHI_ENCRYPTION_KEY is not configured."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = get_settings().phi_encryption_key
    if not key:
        raise PhiEncryptionKeyMissingError(
            "PHI_ENCRYPTION_KEY is not set. Run `make gen-phi-key` to generate one."
        )
    return Fernet(key.encode("ascii"))


class EncryptedString(TypeDecorator[str]):
    """Symmetric-encrypted string column.

    Plaintext at the ORM boundary, Fernet ciphertext at rest.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, _dialect: Dialect) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        return _get_fernet().encrypt(value.encode("utf-8")).decode("ascii")

    def process_result_value(self, value: Any, _dialect: Dialect) -> str | None:
        if value is None:
            return None
        return _get_fernet().decrypt(value.encode("ascii")).decode("utf-8")
