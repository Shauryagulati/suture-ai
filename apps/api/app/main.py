"""FastAPI application entry point.

- structlog (PHI-safe) configured in lifespan
- OpenTelemetry instrumentation (FastAPI + SQLAlchemy) when OTEL_DISABLED=0,
  exports OTLP gRPC to localhost:4317 (Jaeger)
- Prometheus /metrics endpoint via prometheus-fastapi-instrumentator
- Routers: /health, /api/auth/*
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app import __version__
from app.config import get_settings
from app.routers import auth, documents, health
from app.utils.logging import configure_logging, get_logger


def _configure_otel(app: FastAPI) -> None:
    """Wire OpenTelemetry + SQLAlchemy instrumentation.

    Imports are local so test runs with OTEL_DISABLED=1 don't try to
    open OTLP-gRPC connections at import time.
    """
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import (
        SQLAlchemyInstrumentor,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from app.database import engine

    settings = get_settings()
    resource = Resource.create(
        {"service.name": settings.otel_service_name, "service.version": __version__}
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    # The async engine wraps a sync engine; instrument that.
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level)
    log = get_logger(__name__)
    if not settings.otel_disabled:
        _configure_otel(application)
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

# Prometheus /metrics — safe to install at app construction time.
Instrumentator().instrument(app).expose(app, include_in_schema=False)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(documents.router)
