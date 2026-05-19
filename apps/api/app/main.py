"""FastAPI application entry point.

Gate A scope: minimal — just /health, structured logging, lifespan.
Gate B1: adds tenant guard event listeners, audit middleware, models.
Gate B2: adds auth router.
Gate C: adds OpenTelemetry instrumentation + Prometheus /metrics + remaining routers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.config import get_settings
from app.routers import auth, health
from app.utils.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level)
    log = get_logger(__name__)
    log.info(
        "api.startup",
        service=settings.service_name,
        version=__version__,
        otel_disabled=settings.otel_disabled,
    )
    yield
    log.info("api.shutdown")


app = FastAPI(
    title="Suture API",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.include_router(health.router)
app.include_router(auth.router)
