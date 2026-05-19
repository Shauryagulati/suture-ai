"""Health endpoint. No PHI, no auth — used by load balancers and gate verification."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="suture-api", version=__version__)
