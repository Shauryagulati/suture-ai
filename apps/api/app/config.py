"""Application configuration via pydantic-settings.

Reads from environment + .env. Validates types at startup so we fail fast on
misconfiguration rather than at first request.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/.env, resolved relative to this file so it works regardless of cwd
# (seed script runs from repo root, uvicorn from apps/api, tests from anywhere).
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Suture API runtime settings."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service identity
    service_name: str = "suture-api"
    version: str = "0.1.0"

    # Database
    database_url: str = "postgresql+asyncpg://suture:suture_dev_password@localhost:5432/suture"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_always_eager: bool = False

    # Auth — empty by default; Gate B2 populates this from .env
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_seconds: int = 3600
    jwt_refresh_token_ttl_seconds: int = 2_592_000  # 30 days

    # Scheduling links — public patient-facing token TTL (7 days default)
    scheduling_token_ttl_seconds: int = 7 * 24 * 3600
    web_base_url: str = "http://localhost:3000"

    # PHI encryption — empty by default; Gate B1 enforces presence in tests
    phi_encryption_key: str = ""

    # Observability
    otel_disabled: bool = Field(default=True)
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "suture-api"

    # Anthropic (Module 2+)
    anthropic_api_key: str = ""

    # Logging
    log_level: str = "INFO"

    # Document storage — uploaded PDFs land here as
    # {document_storage_path}/{clinic_id}/{uuid4}.pdf.
    document_storage_path: Path = Path("./data/documents")
    max_upload_bytes: int = 25 * 1024 * 1024  # 25 MB
    allowed_mime_types: tuple[str, ...] = ("application/pdf",)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings. Singleton for the process lifetime."""
    return Settings()
